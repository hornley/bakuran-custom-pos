from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import sqlite3
from typing import Any

from .auth import _record_event

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_RATE = Decimal("100")
RATE_PRECISION = Decimal("0.0001")


class TaxValidationError(ValueError):
    """Raised when a tax rule or monetary value is invalid."""


class TaxRuleConflictError(TaxValidationError):
    """Raised when a new tax rule conflicts with an existing effective period."""


def quantize_cent(value: Decimal | str | int) -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise InvalidOperation
        if parsed < ZERO:
            raise TaxValidationError("Amount must not be negative")
        return parsed.quantize(CENT, rounding=ROUND_HALF_UP)
    except TaxValidationError:
        raise
    except (InvalidOperation, ValueError) as exc:
        raise TaxValidationError("Amount must be a valid decimal number") from exc


def parse_rate(value: Decimal | str | int) -> Decimal:
    try:
        raw = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TaxValidationError("Rate must be a valid decimal number") from exc
    if not raw.is_finite() or raw < ZERO or raw > MAX_RATE:
        raise TaxValidationError("Rate must be between 0 and 100 percent")
    try:
        if raw.quantize(RATE_PRECISION, rounding=ROUND_HALF_UP) != raw:
            raise TaxValidationError("Rate supports at most four decimal places")
    except InvalidOperation as exc:
        raise TaxValidationError("Rate supports at most four decimal places") from exc
    if raw == ZERO:
        return ZERO
    return raw


def parse_date(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TaxValidationError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise TaxValidationError(f"{field} must be an ISO date") from exc


def validate_rule(name: str, rate: Decimal | str | int, policy: str, effective_from: str, effective_to: str | None) -> dict[str, Any]:
    if not isinstance(name, str):
        raise TaxValidationError("Name is required and must be at most 80 characters")
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 80:
        raise TaxValidationError("Name is required and must be at most 80 characters")
    normalized_policy = policy.strip().lower() if isinstance(policy, str) else ""
    if normalized_policy not in {"exclusive", "inclusive"}:
        raise TaxValidationError("Policy must be exclusive or inclusive")
    normalized_from = parse_date(effective_from, "effective_from")
    normalized_to = parse_date(effective_to, "effective_to") if effective_to else None
    if normalized_to and normalized_to < normalized_from:
        raise TaxValidationError("effective_to must not be before effective_from")
    normalized_rate = parse_rate(rate)
    return {
        "name": normalized_name,
        "rate": format(normalized_rate, "f"),
        "policy": normalized_policy,
        "effective_from": normalized_from,
        "effective_to": normalized_to,
    }


def effective_rule(connection: sqlite3.Connection, on_date: str | None = None) -> sqlite3.Row | None:
    target = parse_date(on_date, "on_date") if on_date else datetime.now(timezone.utc).date().isoformat()
    return connection.execute(
        """
        SELECT * FROM tax_rules
        WHERE effective_from <= ? AND (effective_to IS NULL OR effective_to >= ?)
        ORDER BY effective_from DESC, id DESC LIMIT 1
        """,
        (target, target),
    ).fetchone()


def calculate_tax(subtotal: Decimal | str | int, rule: sqlite3.Row | dict[str, Any] | None) -> dict[str, Decimal | str | int | None]:
    base = quantize_cent(subtotal)
    if rule is None:
        return {"taxable_subtotal": base, "tax_amount": ZERO, "total": base, "policy": "none", "rate": ZERO, "rule_id": None}
    rate = parse_rate(rule["rate"])
    multiplier = Decimal("1") + (rate / Decimal("100"))
    policy = rule["policy"]
    if policy == "exclusive":
        tax = (base * rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        total = (base + tax).quantize(CENT, rounding=ROUND_HALF_UP)
        taxable = base
    elif policy == "inclusive":
        total = base
        taxable = (base / multiplier).quantize(CENT, rounding=ROUND_HALF_UP)
        tax = (base - taxable).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        raise TaxValidationError("Unsupported tax policy")
    return {"taxable_subtotal": taxable, "tax_amount": tax, "total": total, "policy": policy, "rate": rate, "rule_id": rule["id"]}


def tax_snapshot(connection: sqlite3.Connection, subtotal: Decimal | str | int, rule: sqlite3.Row | dict[str, Any] | None, snapshot_at: str) -> dict[str, Any]:
    del connection  # Kept in the signature for transaction-local callers.
    calculation = calculate_tax(subtotal, rule)
    return {
        **calculation,
        "name": rule["name"] if rule else "",
        "rate_text": format(calculation["rate"], "f"),
        "effective_from": rule["effective_from"] if rule else None,
        "effective_to": rule["effective_to"] if rule else None,
        "snapshot_at": snapshot_at,
    }


def order_tax_snapshot(connection: sqlite3.Connection, order: sqlite3.Row, snapshot_at: str) -> dict[str, Any]:
    if order["tax_snapshot_at"]:
        return {
            "taxable_subtotal": quantize_cent(order["taxable_subtotal"]),
            "tax_amount": quantize_cent(order["tax_amount"]),
            "total": quantize_cent(order["total"]),
            "policy": order["tax_policy"],
            "rate": parse_rate(order["tax_rate"]),
            "rule_id": order["tax_rule_id"],
            "name": order["tax_name"],
            "rate_text": order["tax_rate"],
            "effective_from": order["tax_effective_from"],
            "effective_to": order["tax_effective_to"],
            "snapshot_at": order["tax_snapshot_at"],
        }
    # Orders created before tax snapshots were introduced have the migration
    # defaults (policy=none, no snapshot). They are historical records and
    # must not acquire a rule merely because one is configured later.
    if order["tax_policy"] == "none" and order["status"] != "open":
        return tax_snapshot(connection, order["subtotal"], None, snapshot_at)
    rule = effective_rule(connection, snapshot_at[:10])
    return tax_snapshot(connection, order["subtotal"], rule, snapshot_at)


def snapshot_values(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        snapshot["rule_id"],
        snapshot["name"],
        snapshot["rate_text"],
        snapshot["policy"],
        str(snapshot["taxable_subtotal"]),
        str(snapshot["tax_amount"]),
        str(snapshot["total"]),
        snapshot["snapshot_at"],
        snapshot["effective_from"],
        snapshot["effective_to"],
    )


def create_rule(connection: sqlite3.Connection, payload: dict[str, Any], actor_user_id: int | None = None, path: str = "/api/tax/configuration") -> dict[str, Any]:
    rule = validate_rule(**payload)
    overlap = connection.execute(
        """
        SELECT 1 FROM tax_rules
        WHERE NOT (COALESCE(effective_to, '9999-12-31') < ? OR COALESCE(?, '9999-12-31') < effective_from)
        LIMIT 1
        """,
        (rule["effective_from"], rule["effective_to"]),
    ).fetchone()
    if overlap:
        raise TaxRuleConflictError("Effective dates overlap an existing tax rule")
    cursor = connection.execute(
        """
        INSERT INTO tax_rules(name, rate, policy, effective_from, effective_to, created_at, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (rule["name"], rule["rate"], rule["policy"], rule["effective_from"], rule["effective_to"], datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), actor_user_id),
    )
    _record_event(connection, actor_user_id, "tax.rule_created", path, f"tax_rule_id={cursor.lastrowid};policy={rule['policy']};rate={rule['rate']}")
    return dict(connection.execute("SELECT * FROM tax_rules WHERE id=?", (cursor.lastrowid,)).fetchone())
