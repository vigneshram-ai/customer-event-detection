"""Synthetic customer-event generator.

Reads the customer population produced by Milestone 2 (data_generation/customer_generator.py)
and generates a temporal stream of synthetic banking events per customer: mostly
"normal" events consistent with that customer's profile, plus a controlled minority
of anomalous events.

Ground truth for injected anomalies is written to a SEPARATE sidecar file
(events_ground_truth.csv), keyed by event_id. This is a deliberate architectural
choice: a real event-ingestion source would never carry a label column, and
downstream Bronze/Silver/Gold processing should treat events.csv exactly as an
unlabeled ingestion source. The sidecar exists purely so later milestones
(ML evaluation, monitoring) can score detection quality against known truth.

Determinism note: the time window defaults to a FIXED literal date range
(not "now") so that (customers_file, seed, date range) always produces identical
output, matching the reproducibility principle established in Milestone 2.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path

# --- Event type distribution -------------------------------------------------
EVENT_TYPE_WEIGHTS: dict[str, float] = {
    "card_transaction": 0.40,
    "login": 0.20,
    "payment": 0.15,
    "transfer": 0.10,
    "failed_login": 0.05,
    "beneficiary_added": 0.03,
    "device_changed": 0.03,
    "password_changed": 0.02,
    "profile_changed": 0.02,
}

# Event types that carry a meaningful monetary amount / merchant category.
MONETARY_EVENT_TYPES = {"card_transaction", "payment", "transfer"}

# Event types where authentication_status meaningfully varies.
AUTH_RELEVANT_EVENT_TYPES = {"login", "failed_login"}

MERCHANT_CATEGORIES: list[str] = [
    "groceries",
    "electronics",
    "travel",
    "restaurant",
    "utilities",
    "entertainment",
    "fuel",
    "online_retail",
    "subscription",
    "other",
]

# Simplified currency-by-country mapping (eurozone countries -> EUR).
CURRENCY_BY_COUNTRY: dict[str, str] = {
    "NL": "EUR",
    "BE": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "ES": "EUR",
    "IT": "EUR",
    "PL": "PLN",
    "GB": "GBP",
}

# All countries eligible to be picked for a geo_deviation anomaly (same pool
# customer_generator.py uses for home_country).
ALL_COUNTRIES: list[str] = list(CURRENCY_BY_COUNTRY.keys())
ALL_CHANNELS: list[str] = ["mobile", "web", "branch", "atm"]

ANOMALY_TYPES: list[str] = [
    "new_device",
    "geo_deviation",
    "channel_deviation",
    "amount_spike",
]

# Event types where a "new device" anomaly is realistic and should be
# preferentially selected: these are the events where a device is actually
# the acting agent (logging in, transacting). Other event types (e.g.
# beneficiary_added, profile_changed) can still receive a new_device anomaly,
# but at the base rate rather than a boosted one.
DEVICE_ANOMALY_PREFERRED_EVENT_TYPES = {"login", "card_transaction", "payment"}

# device_changed is the event where the customer LEGITIMATELY changes their
# registered device. Flagging that same event as a "new_device" anomaly would
# be self-contradictory (the event *is* the explanation), so it's excluded
# from that anomaly type entirely.
DEVICE_ANOMALY_EXCLUDED_EVENT_TYPES = {"device_changed"}

# An event whose event_type IS a legitimate device change cannot also be
# flagged as a "new_device" anomaly -- that would be self-contradictory
# (the device change is the expected, explained event).
NEW_DEVICE_IMMUNE_EVENT_TYPES = {"device_changed"}

# new_device anomalies are most meaningful (and most realistic to detect)
# on these event types -- an unrecognized device performing a login or
# moving money is the actual risk signal. Other event types can still get
# a new_device anomaly, just far less often.
NEW_DEVICE_PREFERRED_EVENT_TYPES = {"login", "card_transaction", "payment"}
NEW_DEVICE_PREFERRED_WEIGHT = 3.0
NEW_DEVICE_DEFAULT_WEIGHT = 1.0

DEFAULT_START_DATE = "2026-01-01"
DEFAULT_END_DATE = "2026-03-31"


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    account_age_days: int
    home_country: str
    normal_channel: str
    normal_device: str


@dataclass(frozen=True)
class Event:
    event_id: str
    customer_id: str
    event_timestamp: str
    event_type: str
    amount: float
    currency: str
    country: str
    channel: str
    device_id: str
    merchant_category: str
    authentication_status: str


@dataclass(frozen=True)
class GroundTruthRecord:
    event_id: str
    is_synthetic_anomaly: bool
    anomaly_type: str


def read_customers(path: Path) -> list[CustomerRecord]:
    """Read the Milestone 2 customer population from CSV."""
    if not path.exists():
        raise FileNotFoundError(
            f"Customers file not found: {path}. Run customer_generator.py first."
        )

    customers: list[CustomerRecord] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            customers.append(
                CustomerRecord(
                    customer_id=row["customer_id"],
                    account_age_days=int(row["account_age_days"]),
                    home_country=row["home_country"],
                    normal_channel=row["normal_channel"],
                    normal_device=row["normal_device"],
                )
            )
    if not customers:
        raise ValueError(f"Customers file {path} contained no rows.")
    return customers


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return rng.choices(keys, weights=vals, k=1)[0]


def _random_device_id(rng: random.Random) -> str:
    return "DEV-" + "".join(rng.choices("0123456789ABCDEF", k=12))


def _random_timestamp(rng: random.Random, start: datetime, end: datetime) -> datetime:
    total_seconds = int((end - start).total_seconds())
    offset = rng.randint(0, max(total_seconds, 0))
    return start + timedelta(seconds=offset)


def _baseline_amount_for_customer(rng: random.Random) -> float:
    """Each customer gets a fixed 'typical spend' baseline drawn once.

    Individual event amounts vary around this baseline. This is what makes
    amount_spike anomalies a deviation from THAT customer's own norm, not a
    deviation from some global average.
    """
    return round(rng.uniform(20.0, 500.0), 2)


def _generate_normal_event(
    rng: random.Random,
    event_id: str,
    customer: CustomerRecord,
    baseline_amount: float,
    timestamp: datetime,
) -> Event:
    event_type = _weighted_choice(rng, EVENT_TYPE_WEIGHTS)

    amount = 0.0
    merchant_category = ""
    if event_type in MONETARY_EVENT_TYPES:
        # Amount varies around the customer's own baseline (+/- ~40%).
        amount = round(baseline_amount * rng.uniform(0.6, 1.4), 2)
        merchant_category = rng.choice(MERCHANT_CATEGORIES)

    authentication_status = "success"
    if event_type in AUTH_RELEVANT_EVENT_TYPES:
        authentication_status = "failed" if event_type == "failed_login" else "success"

    country = customer.home_country
    return Event(
        event_id=event_id,
        customer_id=customer.customer_id,
        event_timestamp=timestamp.isoformat(),
        event_type=event_type,
        amount=amount,
        currency=CURRENCY_BY_COUNTRY[country],
        country=country,
        channel=customer.normal_channel,
        device_id=customer.normal_device,
        merchant_category=merchant_category,
        authentication_status=authentication_status,
    )


def _anomaly_type_weights_for_event(event_type: str) -> dict[str, float]:
    """Return anomaly-type selection weights appropriate for this event_type.

    - new_device is excluded entirely for device_changed events (self-contradictory).
    - new_device is boosted for login/card_transaction/payment (device is the
      actual acting agent for these).
    - amount_spike is excluded for event types that don't carry a real amount.
    """
    weights = {
        "new_device": 0.25,
        "geo_deviation": 0.25,
        "channel_deviation": 0.25,
        "amount_spike": 0.25,
    }

    if event_type in DEVICE_ANOMALY_EXCLUDED_EVENT_TYPES:
        weights["new_device"] = 0.0
    elif event_type in DEVICE_ANOMALY_PREFERRED_EVENT_TYPES:
        weights["new_device"] = 0.55

    if event_type not in MONETARY_EVENT_TYPES:
        weights["amount_spike"] = 0.0

    if sum(weights.values()) == 0.0:
        # Should not happen given current event types, but stay safe: fall
        # back to the two anomaly types that are always eligible.
        weights = {"geo_deviation": 0.5, "channel_deviation": 0.5}

    return weights


def _apply_anomaly(
    rng: random.Random,
    event: Event,
    customer: CustomerRecord,
    baseline_amount: float,
) -> tuple[Event, str]:
    """Mutate a normal event into an anomalous one. Returns (event, anomaly_type)."""
    weights = _anomaly_type_weights_for_event(event.event_type)
    anomaly_type = _weighted_choice(rng, weights)

    if anomaly_type == "new_device":
        new_device = _random_device_id(rng)
        # Ensure it actually differs from the customer's normal device.
        while new_device == customer.normal_device:
            new_device = _random_device_id(rng)
        event = _replace(event, device_id=new_device)

    elif anomaly_type == "geo_deviation":
        candidates = [c for c in ALL_COUNTRIES if c != customer.home_country]
        new_country = rng.choice(candidates)
        event = _replace(event, country=new_country, currency=CURRENCY_BY_COUNTRY[new_country])

    elif anomaly_type == "channel_deviation":
        candidates = [c for c in ALL_CHANNELS if c != customer.normal_channel]
        event = _replace(event, channel=rng.choice(candidates))

    elif anomaly_type == "amount_spike":
        # _anomaly_type_weights_for_event guarantees amount_spike is only
        # selectable for MONETARY_EVENT_TYPES, so no fallback needed here.
        spike_amount = round(baseline_amount * rng.uniform(5.0, 10.0), 2)
        event = _replace(event, amount=spike_amount)

    return event, anomaly_type


def _replace(event: Event, **changes) -> Event:
    data = asdict(event)
    data.update(changes)
    return Event(**data)


def generate_events(
    customers: list[CustomerRecord],
    seed: int,
    events_min: int,
    events_max: int,
    start_date: datetime,
    end_date: datetime,
    anomaly_rate: float,
) -> tuple[list[Event], list[GroundTruthRecord]]:
    if events_min <= 0 or events_max <= 0 or events_min > events_max:
        raise ValueError("events_min/events_max must be positive with events_min <= events_max")
    if not (0.0 <= anomaly_rate <= 1.0):
        raise ValueError("anomaly_rate must be between 0.0 and 1.0")
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    rng = random.Random(seed)
    events: list[Event] = []
    ground_truth: list[GroundTruthRecord] = []
    event_counter = 0

    for customer in customers:
        baseline_amount = _baseline_amount_for_customer(rng)
        num_events = rng.randint(events_min, events_max)

        # Generate timestamps first, then sort, so each customer's events are
        # chronological (matters for later velocity/rolling-window features).
        timestamps = sorted(_random_timestamp(rng, start_date, end_date) for _ in range(num_events))

        num_anomalies = round(num_events * anomaly_rate)
        anomaly_indices = set(rng.sample(range(num_events), k=min(num_anomalies, num_events)))

        for i, ts in enumerate(timestamps):
            event_counter += 1
            event_id = f"EVT{event_counter:09d}"
            event = _generate_normal_event(rng, event_id, customer, baseline_amount, ts)

            is_anomaly = i in anomaly_indices
            anomaly_type = ""
            if is_anomaly:
                event, anomaly_type = _apply_anomaly(rng, event, customer, baseline_amount)

            events.append(event)
            ground_truth.append(
                GroundTruthRecord(
                    event_id=event_id,
                    is_synthetic_anomaly=is_anomaly,
                    anomaly_type=anomaly_type,
                )
            )

    return events, ground_truth


def write_events_csv(events: list[Event], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(Event)]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in events:
            writer.writerow(asdict(e))


def write_ground_truth_csv(records: list[GroundTruthRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(GroundTruthRecord)]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic bank customer events.")
    parser.add_argument("--customers-file", type=Path, default=Path("data/raw/customers.csv"))
    parser.add_argument("--events-min", type=int, default=5)
    parser.add_argument("--events-max", type=int, default=50)
    parser.add_argument("--start-date", type=str, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=str, default=DEFAULT_END_DATE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--anomaly-rate", type=float, default=0.02)
    parser.add_argument("--output", type=Path, default=Path("data/raw/events.csv"))
    parser.add_argument(
        "--ground-truth-output",
        type=Path,
        default=Path("data/raw/events_ground_truth.csv"),
    )
    args = parser.parse_args()

    start_date = datetime.fromisoformat(args.start_date)
    end_date = datetime.fromisoformat(args.end_date)

    customers = read_customers(args.customers_file)
    events, ground_truth = generate_events(
        customers=customers,
        seed=args.seed,
        events_min=args.events_min,
        events_max=args.events_max,
        start_date=start_date,
        end_date=end_date,
        anomaly_rate=args.anomaly_rate,
    )

    write_events_csv(events, args.output)
    write_ground_truth_csv(ground_truth, args.ground_truth_output)

    anomaly_count = sum(1 for r in ground_truth if r.is_synthetic_anomaly)
    print(f"Generated {len(events)} events for {len(customers)} customers -> {args.output}")
    print(
        f"Injected {anomaly_count} anomalies "
        f"({anomaly_count / len(events):.2%}) -> {args.ground_truth_output}"
    )


if __name__ == "__main__":
    main()
