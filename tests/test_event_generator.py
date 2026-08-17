"""Tests for data_generation/event_generator.py."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from data_generation.event_generator import (
    CURRENCY_BY_COUNTRY,
    CustomerRecord,
    generate_events,
    read_customers,
    write_events_csv,
    write_ground_truth_csv,
)

START = datetime.fromisoformat("2026-01-01")
END = datetime.fromisoformat("2026-03-31")


def _sample_customers(n: int = 20) -> list[CustomerRecord]:
    return [
        CustomerRecord(
            customer_id=f"CUST{i:07d}",
            account_age_days=500,
            home_country="NL",
            normal_channel="mobile",
            normal_device=f"DEV-{i:012d}",
        )
        for i in range(1, n + 1)
    ]


def test_generate_events_is_deterministic():
    customers = _sample_customers()
    events_a, gt_a = generate_events(
        customers,
        seed=1,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.1,
    )
    events_b, gt_b = generate_events(
        customers,
        seed=1,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.1,
    )
    assert events_a == events_b
    assert gt_a == gt_b


def test_different_seeds_produce_different_output():
    customers = _sample_customers()
    events_a, _ = generate_events(
        customers,
        seed=1,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.1,
    )
    events_b, _ = generate_events(
        customers,
        seed=2,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.1,
    )
    assert events_a != events_b


def test_event_count_within_configured_range():
    customers = _sample_customers(n=10)
    events, _ = generate_events(
        customers,
        seed=1,
        events_min=3,
        events_max=3,
        start_date=START,
        end_date=END,
        anomaly_rate=0.0,
    )
    # events_min == events_max == 3, so exactly 3 events per customer.
    assert len(events) == 30


def test_every_event_id_is_unique():
    customers = _sample_customers()
    events, _ = generate_events(
        customers,
        seed=1,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.05,
    )
    ids = [e.event_id for e in events]
    assert len(ids) == len(set(ids))


def test_events_and_ground_truth_have_matching_event_ids():
    customers = _sample_customers()
    events, ground_truth = generate_events(
        customers,
        seed=1,
        events_min=5,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.1,
    )
    assert [e.event_id for e in events] == [g.event_id for g in ground_truth]


def test_anomaly_rate_is_approximately_respected():
    customers = _sample_customers(n=200)
    events, ground_truth = generate_events(
        customers,
        seed=1,
        events_min=20,
        events_max=20,
        start_date=START,
        end_date=END,
        anomaly_rate=0.10,
    )
    anomaly_count = sum(1 for g in ground_truth if g.is_synthetic_anomaly)
    rate = anomaly_count / len(events)
    assert 0.05 <= rate <= 0.15  # loose bound; rounding per-customer causes variance


def test_normal_events_use_customer_profile_fields():
    customers = _sample_customers(n=5)
    events, ground_truth = generate_events(
        customers,
        seed=7,
        events_min=15,
        events_max=15,
        start_date=START,
        end_date=END,
        anomaly_rate=0.0,
    )
    # anomaly_rate=0.0 -> every event must match the customer's normal profile.
    by_customer = {c.customer_id: c for c in customers}
    for event in events:
        customer = by_customer[event.customer_id]
        assert event.device_id == customer.normal_device
        assert event.channel == customer.normal_channel
        assert event.country == customer.home_country


def test_anomalous_events_deviate_from_profile():
    customers = _sample_customers(n=50)
    events, ground_truth = generate_events(
        customers,
        seed=3,
        events_min=30,
        events_max=30,
        start_date=START,
        end_date=END,
        anomaly_rate=0.5,
    )
    by_customer = {c.customer_id: c for c in customers}
    gt_by_id = {g.event_id: g for g in ground_truth}

    deviated = False
    for event in events:
        gt = gt_by_id[event.event_id]
        if not gt.is_synthetic_anomaly:
            continue
        customer = by_customer[event.customer_id]
        if gt.anomaly_type == "new_device":
            assert event.device_id != customer.normal_device
            deviated = True
        elif gt.anomaly_type == "geo_deviation":
            assert event.country != customer.home_country
            deviated = True
        elif gt.anomaly_type == "channel_deviation":
            assert event.channel != customer.normal_channel
            deviated = True
    assert deviated  # sanity: with 50% anomaly rate, at least one checkable type fired


def test_device_changed_events_never_get_new_device_anomaly():
    customers = _sample_customers(n=100)
    events, ground_truth = generate_events(
        customers,
        seed=11,
        events_min=40,
        events_max=40,
        start_date=START,
        end_date=END,
        anomaly_rate=0.5,
    )
    gt_by_id = {g.event_id: g for g in ground_truth}
    checked_any = False
    for event in events:
        if event.event_type != "device_changed":
            continue
        gt = gt_by_id[event.event_id]
        if gt.is_synthetic_anomaly:
            checked_any = True
            assert gt.anomaly_type != "new_device"
    assert checked_any  # sanity: with these settings, device_changed anomalies should occur


def test_new_device_anomaly_preferentially_lands_on_device_acting_event_types():
    customers = _sample_customers(n=300)
    events, ground_truth = generate_events(
        customers,
        seed=21,
        events_min=30,
        events_max=30,
        start_date=START,
        end_date=END,
        anomaly_rate=0.5,
    )
    gt_by_id = {g.event_id: g for g in ground_truth}

    preferred_types = {"login", "card_transaction", "payment"}
    new_device_in_preferred = 0
    new_device_in_other = 0
    total_preferred = 0
    total_other_eligible = 0  # excludes device_changed, which can't get new_device at all

    for event in events:
        gt = gt_by_id[event.event_id]
        if event.event_type in preferred_types:
            total_preferred += 1
        elif event.event_type != "device_changed":
            total_other_eligible += 1

        if gt.is_synthetic_anomaly and gt.anomaly_type == "new_device":
            if event.event_type in preferred_types:
                new_device_in_preferred += 1
            else:
                new_device_in_other += 1

    rate_preferred = new_device_in_preferred / total_preferred
    rate_other = new_device_in_other / total_other_eligible
    assert rate_preferred > rate_other


def test_monetary_fields_only_populated_for_monetary_event_types():
    customers = _sample_customers(n=30)
    events, _ = generate_events(
        customers,
        seed=5,
        events_min=20,
        events_max=20,
        start_date=START,
        end_date=END,
        anomaly_rate=0.0,
    )
    for event in events:
        if event.event_type in {"card_transaction", "payment", "transfer"}:
            assert event.amount > 0.0
        else:
            assert event.amount == 0.0
            assert event.merchant_category == ""


def test_currency_matches_country():
    customers = _sample_customers(n=5)
    events, _ = generate_events(
        customers,
        seed=1,
        events_min=10,
        events_max=10,
        start_date=START,
        end_date=END,
        anomaly_rate=0.3,
    )
    for event in events:
        assert event.currency == CURRENCY_BY_COUNTRY[event.country]


def test_invalid_event_range_raises():
    customers = _sample_customers(n=1)
    with pytest.raises(ValueError):
        generate_events(
            customers,
            seed=1,
            events_min=10,
            events_max=5,
            start_date=START,
            end_date=END,
            anomaly_rate=0.0,
        )


def test_invalid_anomaly_rate_raises():
    customers = _sample_customers(n=1)
    with pytest.raises(ValueError):
        generate_events(
            customers,
            seed=1,
            events_min=5,
            events_max=5,
            start_date=START,
            end_date=END,
            anomaly_rate=1.5,
        )


def test_end_before_start_raises():
    customers = _sample_customers(n=1)
    with pytest.raises(ValueError):
        generate_events(
            customers,
            seed=1,
            events_min=5,
            events_max=5,
            start_date=END,
            end_date=START,
            anomaly_rate=0.0,
        )


def test_read_customers_round_trip(tmp_path: Path):
    from data_generation.customer_generator import generate_customers, write_customers_csv

    customers = generate_customers(num_customers=10, seed=42)
    csv_path = tmp_path / "customers.csv"
    write_customers_csv(customers, csv_path)

    loaded = read_customers(csv_path)
    assert len(loaded) == 10
    assert loaded[0].customer_id == customers[0].customer_id
    assert loaded[0].home_country == customers[0].home_country


def test_read_customers_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_customers(tmp_path / "does_not_exist.csv")


def test_write_events_csv_creates_file_with_header(tmp_path: Path):
    customers = _sample_customers(n=2)
    events, ground_truth = generate_events(
        customers,
        seed=1,
        events_min=3,
        events_max=3,
        start_date=START,
        end_date=END,
        anomaly_rate=0.0,
    )
    out_path = tmp_path / "events.csv"
    write_events_csv(events, out_path)
    content = out_path.read_text(encoding="utf-8")
    assert "event_id" in content.splitlines()[0]
    assert len(content.splitlines()) == len(events) + 1  # header + rows


def test_write_ground_truth_csv_creates_file(tmp_path: Path):
    customers = _sample_customers(n=2)
    events, ground_truth = generate_events(
        customers,
        seed=1,
        events_min=3,
        events_max=3,
        start_date=START,
        end_date=END,
        anomaly_rate=0.0,
    )
    out_path = tmp_path / "gt.csv"
    write_ground_truth_csv(ground_truth, out_path)
    content = out_path.read_text(encoding="utf-8")
    assert "is_synthetic_anomaly" in content.splitlines()[0]
