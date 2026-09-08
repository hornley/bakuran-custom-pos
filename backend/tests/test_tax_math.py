from decimal import Decimal

import pytest

from app.tax import TaxValidationError, calculate_tax


def rule(rate="10", policy="exclusive"):
    return {"id": 1, "name": "VAT", "rate": rate, "policy": policy, "effective_from": "2020-01-01", "effective_to": None}


def test_exclusive_tax_rounds_half_up_at_cent():
    result = calculate_tax("0.05", rule(rate="10"))
    assert result["tax_amount"] == Decimal("0.01")
    assert result["total"] == Decimal("0.06")


def test_inclusive_tax_rounds_taxable_base_and_tax_half_up():
    result = calculate_tax("0.05", rule(rate="10", policy="inclusive"))
    assert result["taxable_subtotal"] == Decimal("0.05")
    assert result["tax_amount"] == Decimal("0.00")
    assert result["total"] == Decimal("0.05")


def test_exclusive_tax_uses_decimal_half_up_at_the_next_boundary():
    result = calculate_tax("0.15", rule(rate="10"))
    assert result["tax_amount"] == Decimal("0.02")
    assert result["total"] == Decimal("0.17")


def test_inclusive_tax_uses_decimal_half_up_for_a_small_total():
    result = calculate_tax("0.06", rule(rate="10", policy="inclusive"))
    assert result["taxable_subtotal"] == Decimal("0.05")
    assert result["tax_amount"] == Decimal("0.01")
    assert result["total"] == Decimal("0.06")


def test_tax_rejects_negative_subtotals():
    with pytest.raises(TaxValidationError, match="must not be negative"):
        calculate_tax("-0.01", rule())
