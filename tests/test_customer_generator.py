import csv

import pytest

from data_generation.customer_generator import (
    Customer,
    generate_customers,
    write_customers_csv,
)


def test_generates_requested_count():
    customers = generate_customers(num_customers=500, seed=1)
    assert len(customers) == 500


def test_deterministic_with_same_seed():
    a = generate_customers(num_customers=200, seed=42)
    b = generate_customers(num_customers=200, seed=42)
    assert a == b


def test_different_seeds_produce_different_output():
    a = generate_customers(num_customers=200, seed=1)
    b = generate_customers(num_customers=200, seed=2)
    assert a != b


def test_customer_ids_are_unique():
    customers = generate_customers(num_customers=1000, seed=7)
    ids = [c.customer_id for c in customers]
    assert len(ids) == len(set(ids))


def test_rejects_non_positive_count():
    with pytest.raises(ValueError):
        generate_customers(num_customers=0, seed=1)
    with pytest.raises(ValueError):
        generate_customers(num_customers=-5, seed=1)


def test_country_distribution_roughly_matches_weights():
    # Statistical check, not exact — large N keeps this stable across seeds.
    customers = generate_customers(num_customers=20_000, seed=42)
    nl_share = sum(1 for c in customers if c.home_country == "NL") / len(customers)
    assert 0.65 <= nl_share <= 0.75  # target weight is 0.70


def test_write_customers_csv_round_trip(tmp_path):
    customers = generate_customers(num_customers=50, seed=42)
    output_path = tmp_path / "customers.csv"
    write_customers_csv(customers, output_path)

    with output_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 50
    assert set(rows[0].keys()) == {f.name for f in Customer.__dataclass_fields__.values()}
    assert rows[0]["customer_id"] == "CUST0000001"
