"""Synthetic customer generator.

Generates a deterministic, seeded population of synthetic bank customers.
This is reference/dimension data: later synthetic events (Milestone 3) will
reference these customers and their "normal" behaviour patterns.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# Weighted toward a single home country (NL) with a European long tail.
# This matters later: geographic-deviation features are only meaningful if
# most activity is concentrated in a "normal" country per customer.
COUNTRY_WEIGHTS: dict[str, float] = {
    "NL": 0.70,
    "BE": 0.10,
    "DE": 0.06,
    "FR": 0.04,
    "PL": 0.03,
    "ES": 0.03,
    "IT": 0.02,
    "GB": 0.02,
}

# Weighted toward mobile, reflecting realistic modern banking channel mix.
CHANNEL_WEIGHTS: dict[str, float] = {
    "mobile": 0.60,
    "web": 0.25,
    "branch": 0.10,
    "atm": 0.05,
}

# Tenure tiers: most of a realistic customer base is established, not brand new.
ACCOUNT_AGE_TIERS: dict[str, tuple[int, int]] = {
    "new": (1, 364),
    "established": (365, 1825),
    "veteran": (1826, 5475),
}
ACCOUNT_AGE_TIER_WEIGHTS: dict[str, float] = {
    "new": 0.25,
    "established": 0.45,
    "veteran": 0.30,
}


@dataclass(frozen=True)
class Customer:
    customer_id: str
    account_age_days: int
    home_country: str
    normal_channel: str
    normal_device: str


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = list(weights.values())
    return rng.choices(keys, weights=vals, k=1)[0]


def _generate_account_age_days(rng: random.Random) -> int:
    tier = _weighted_choice(rng, ACCOUNT_AGE_TIER_WEIGHTS)
    low, high = ACCOUNT_AGE_TIERS[tier]
    return rng.randint(low, high)


def _generate_device_id(rng: random.Random) -> str:
    return "DEV-" + "".join(rng.choices("0123456789ABCDEF", k=12))


def generate_customers(num_customers: int, seed: int) -> list[Customer]:
    """Generate a deterministic list of synthetic customers.

    Same (num_customers, seed) pair always produces identical output.
    """
    if num_customers <= 0:
        raise ValueError("num_customers must be a positive integer")

    rng = random.Random(seed)
    customers: list[Customer] = []
    for i in range(1, num_customers + 1):
        customers.append(
            Customer(
                customer_id=f"CUST{i:07d}",
                account_age_days=_generate_account_age_days(rng),
                home_country=_weighted_choice(rng, COUNTRY_WEIGHTS),
                normal_channel=_weighted_choice(rng, CHANNEL_WEIGHTS),
                normal_device=_generate_device_id(rng),
            )
        )
    return customers


def write_customers_csv(customers: list[Customer], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(Customer)]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in customers:
            writer.writerow(asdict(c))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic bank customers.")
    parser.add_argument("--num-customers", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/raw/customers.csv"))
    args = parser.parse_args()

    customers = generate_customers(args.num_customers, args.seed)
    write_customers_csv(customers, args.output)
    print(f"Generated {len(customers)} customers -> {args.output}")


if __name__ == "__main__":
    main()
