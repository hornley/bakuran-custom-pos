from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import sqlite3
from typing import Any, Callable

from fastapi import HTTPException
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import record_event_in_connection
from .tax import calculate_tax, effective_rule

CENT = Decimal("0.01")
RATE_PRECISION = Decimal("0.0001")
ZERO = Decimal("0.00")
MAX_PROMOTION_VALUE = Decimal("9999999999.99")
MAX_USAGE_LIMIT = 1_000_000_000
MAX_CODE_LENGTH = 40
MAX_NAME_LENGTH = 120
MAX_IDEMPOTENCY_KEY_LENGTH = 160


class PromotionValidationError(ValueError):
    """Raised when a promotion definition or code is invalid."""


class PromotionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        min_length=1,
        max_length=MAX_CODE_LENGTH,
        validation_alias=AliasChoices("code", "promotion_code"),
    )
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    discount_type: str = Field(
        min_length=1,
        max_length=20,
        validation_alias=AliasChoices("discount_type", "type", "kind"),
    )
    value: Decimal = Field(validation_alias=AliasChoices("value", "amount", "discount_value"))
    starts_on: str = Field(
        validation_alias=AliasChoices("starts_on", "starts_at", "valid_from", "effective_from")
    )
    ends_on: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ends_on", "ends_at", "valid_to", "effective_to"),
    )
    usage_limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_USAGE_LIMIT,
        validation_alias=AliasChoices("usage_limit", "max_uses"),
    )
    active: bool = Field(default=True, validation_alias=AliasChoices("active", "is_active"))
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=MAX_IDEMPOTENCY_KEY_LENGTH, exclude=True)

    @field_validator("code", mode="before")
    @classmethod
    def code_normalized(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or len(value) > MAX_CODE_LENGTH or any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("code must be 1 to 40 visible characters")
        return value.upper()

    @field_validator("name", mode="before")
    @classmethod
    def name_normalized(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("name must not be blank or contain control characters")
        return value

    @field_validator("discount_type", mode="before")
    @classmethod
    def discount_type_normalized(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().lower()
        if value not in {"fixed", "percentage"}:
            raise ValueError("discount_type must be fixed or percentage")
        return value

    @field_validator("value")
    @classmethod
    def value_valid(cls, value: Decimal, info):
        if not value.is_finite() or value < ZERO or value > MAX_PROMOTION_VALUE:
            raise ValueError("value is outside the supported promotion range")
        discount_type = info.data.get("discount_type")
        precision = CENT if discount_type == "fixed" else RATE_PRECISION
        try:
            rounded = value.quantize(precision, rounding=ROUND_HALF_UP)
        except (DecimalException, InvalidOperation) as exc:
            raise ValueError("value is outside the supported promotion range") from exc
        if rounded != value:
            if discount_type == "fixed":
                raise ValueError("fixed promotion values must have at most two decimal places")
            raise ValueError("percentage promotion values must have at most four decimal places")
        if discount_type == "percentage" and value > Decimal("100"):
            raise ValueError("percentage promotion values must be between 0 and 100")
        return value

    @field_validator("starts_on", "ends_on", mode="before")
    @classmethod
    def dates_are_strings(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("starts_on")
    @classmethod
    def start_date_valid(cls, value):
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("starts_on must be an ISO date") from exc

    @field_validator("ends_on")
    @classmethod
    def end_date_valid(cls, value):
        if value is None:
            return value
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError) as exc:
            raise ValueError("ends_on must be an ISO date") from exc

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_normalized(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH or any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("idempotency_key must be visible and at most 160 characters")
        return value

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on must not be before starts_on")
        return self


class PromotionApplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE_LENGTH, validation_alias=AliasChoices("code", "promotion_code"))
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=MAX_IDEMPOTENCY_KEY_LENGTH, exclude=True)

    @field_validator("code", mode="before")
    @classmethod
    def code_normalized(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or len(value) > MAX_CODE_LENGTH or any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("code must be 1 to 40 visible characters")
        return value.upper()

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_normalized(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH or any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("idempotency_key must be visible and at most 160 characters")
        return value


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def actor_id(request) -> int | None:
    user = getattr(request.state, "auth_user", None)
    return user.get("id") if user else None


def normalize_idempotency_key(value: str | None, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise HTTPException(status_code=400, detail="A client idempotency key is required")
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH
        or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH
        or any(ord(character) < 33 or ord(character) == 127 for character in normalized)
    ):
        raise HTTPException(status_code=422, detail="Idempotency-Key must be visible and at most 160 characters")
    return normalized


def _money(value: Any, label: str = "Amount") -> Decimal:
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < ZERO or parsed > MAX_PROMOTION_VALUE:
            raise InvalidOperation
        return parsed.quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, DecimalException, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{label} is outside the supported monetary range") from exc


def _rate_text(value: Decimal) -> str:
    return format(value, "f")


def promotion_definition_payload(payload: PromotionCreateIn) -> dict[str, Any]:
    value = payload.value.quantize(CENT if payload.discount_type == "fixed" else RATE_PRECISION, rounding=ROUND_HALF_UP)
    return {
        "code": payload.code,
        "name": payload.name,
        "discount_type": payload.discount_type,
        "value": format(value, ".2f") if payload.discount_type == "fixed" else _rate_text(value).rstrip("0").rstrip(".") or "0",
        "starts_on": payload.starts_on,
        "ends_on": payload.ends_on,
        "usage_limit": payload.usage_limit,
        "active": bool(payload.active),
    }


def _promotion_status(row: sqlite3.Row | dict[str, Any], on_date: date | None = None) -> str:
    if not row["active"]:
        return "inactive"
    target = on_date or datetime.now(timezone.utc).date()
    start = date.fromisoformat(row["starts_on"])
    end = date.fromisoformat(row["ends_on"]) if row["ends_on"] else None
    if target < start:
        return "scheduled"
    if end and target > end:
        return "expired"
    if row["usage_limit"] is not None and row["usage_count"] >= row["usage_limit"]:
        return "exhausted"
    return "active"


def promotion_view(row: sqlite3.Row | dict[str, Any], on_date: date | None = None) -> dict[str, Any]:
    value = dict(row)
    value["active"] = bool(value["active"])
    value["status"] = _promotion_status(row, on_date)
    value["remaining_uses"] = (
        None if row["usage_limit"] is None else max(row["usage_limit"] - row["usage_count"], 0)
    )
    return value


def applied_promotion_view(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "promotion_id": row["promotion_id"],
        "code": row["code"],
        "name": row["name"],
        "discount_type": row["discount_type"],
        "value": row["value"],
        "discount_amount": row["discount_amount"],
        "original_subtotal": row["original_subtotal"],
        "discounted_subtotal": row["discounted_subtotal"],
        "applied_at": row["applied_at"],
        "applied_by_user_id": row["applied_by_user_id"],
    }


def current_applied_promotion(connection: sqlite3.Connection, order_id: int):
    return connection.execute(
        "SELECT * FROM applied_promotions WHERE order_id=?",
        (order_id,),
    ).fetchone()


def _order_original_subtotal(connection: sqlite3.Connection, order_id: int) -> Decimal:
    values = connection.execute(
        "SELECT line_total FROM restaurant_order_lines WHERE order_id=?",
        (order_id,),
    ).fetchall()
    try:
        total = sum((Decimal(str(row["line_total"])) for row in values), ZERO)
        if not total.is_finite():
            raise InvalidOperation
    except (DecimalException, InvalidOperation, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Order subtotal is outside the supported monetary range") from exc
    return _money(total, "Order subtotal")


def _refresh_applied_snapshot(
    connection: sqlite3.Connection,
    order_id: int,
    original: Decimal,
    discount: Decimal,
    discounted: Decimal,
) -> None:
    connection.execute(
        "UPDATE applied_promotions SET discount_amount=?,original_subtotal=?,discounted_subtotal=? WHERE order_id=?",
        (str(discount), str(original), str(discounted), order_id),
    )


def _discount_amount(applied: sqlite3.Row | dict[str, Any] | None, original: Decimal) -> Decimal:
    if applied is None:
        return ZERO
    value = Decimal(str(applied["value"]))
    if applied["discount_type"] == "fixed":
        return min(_money(value, "Promotion value"), original)
    try:
        return (original * value / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    except (DecimalException, InvalidOperation) as exc:
        raise HTTPException(status_code=422, detail="Promotion discount is outside the supported monetary range") from exc


def _snapshot_rule(order: sqlite3.Row | dict[str, Any]) -> dict[str, Any] | None:
    if order["tax_policy"] == "none" or order["tax_rule_id"] is None:
        return None
    return {
        "id": order["tax_rule_id"],
        "name": order["tax_name"],
        "rate": order["tax_rate"],
        "policy": order["tax_policy"],
        "effective_from": order["tax_effective_from"],
        "effective_to": order["tax_effective_to"],
    }


def _tax_rule_from_snapshot(order: sqlite3.Row | dict[str, Any]) -> dict[str, Any] | None:
    """Build the tax module's calculation shape from a stored order snapshot."""
    return _snapshot_rule(order)


def reprice_order(
    connection: sqlite3.Connection,
    order_id: int,
    *,
    snapshot_if_missing: bool = False,
    snapshot_at: str | None = None,
) -> dict[str, Any]:
    """Recompute promotion and tax amounts inside the caller's transaction.

    The order's line subtotal remains the original subtotal. A stored tax rule is
    reused by identity and effective dates; only its monetary calculation is
    rerun from the discounted subtotal.
    """
    order = connection.execute("SELECT * FROM restaurant_orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        raise HTTPException(status_code=404, detail="Restaurant order not found")
    original = _order_original_subtotal(connection, order_id)
    applied = current_applied_promotion(connection, order_id)
    discount = _discount_amount(applied, original)
    discounted = _money(original - discount, "Discounted subtotal")
    if applied:
        _refresh_applied_snapshot(connection, order_id, original, discount, discounted)

    snapshot_timestamp = order["tax_snapshot_at"]
    rule = _tax_rule_from_snapshot(order) if snapshot_timestamp else None
    should_snapshot = not snapshot_timestamp and snapshot_if_missing
    if should_snapshot:
        snapshot_timestamp = snapshot_at or now_iso()
        rule = effective_rule(connection, snapshot_timestamp[:10])

    if rule is None:
        calculation = {
            "taxable_subtotal": discounted,
            "tax_amount": ZERO,
            "total": discounted,
        }
    else:
        calculation = calculate_tax(discounted, rule)

    params: list[Any] = [
        str(original),
        str(original),
        str(discount),
        str(discounted),
        str(calculation["taxable_subtotal"]),
        str(calculation["tax_amount"]),
        str(calculation["total"]),
    ]
    assignments = [
        "subtotal=?",
        "original_subtotal=?",
        "discount_amount=?",
        "discounted_subtotal=?",
        "taxable_subtotal=?",
        "tax_amount=?",
        "total=?",
    ]
    if should_snapshot:
        assignments.extend(
            [
                "tax_rule_id=?",
                "tax_name=?",
                "tax_rate=?",
                "tax_policy=?",
                "tax_snapshot_at=?",
                "tax_effective_from=?",
                "tax_effective_to=?",
            ]
        )
        params.extend(
            [
                rule["id"] if rule else None,
                rule["name"] if rule else "",
                format(calculation.get("rate", ZERO), "f") if rule else "0.00",
                calculation.get("policy", "none"),
                snapshot_timestamp,
                rule["effective_from"] if rule else None,
                rule["effective_to"] if rule else None,
            ]
        )
    params.append(order_id)
    connection.execute(f"UPDATE restaurant_orders SET {', '.join(assignments)} WHERE id=?", params)
    return {
        "original_subtotal": format(original, "f"),
        "discount_amount": format(discount, "f"),
        "discounted_subtotal": format(discounted, "f"),
        "taxable_subtotal": format(calculation["taxable_subtotal"], "f"),
        "tax_amount": format(calculation["tax_amount"], "f"),
        "total": format(calculation["total"], "f"),
        "snapshot_at": snapshot_timestamp,
        "promotion": applied_promotion_view(applied),
    }


def order_pricing_view(connection: sqlite3.Connection, order: sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    original = order["original_subtotal"]
    discounted = order["discounted_subtotal"]
    discount = order["discount_amount"]
    # The deterministic seed order is inserted by seed.py after migrations and
    # therefore has migration defaults in these new columns. Preserve its old
    # pricing view until the next reset while keeping real zero-value orders safe.
    if Decimal(str(original)) == ZERO and Decimal(str(order["subtotal"])) != ZERO:
        original = order["subtotal"]
    if Decimal(str(discounted)) == ZERO and Decimal(str(original)) != ZERO and Decimal(str(discount)) == ZERO:
        discounted = original
    return {
        "original_subtotal": format(_money(original, "Order subtotal"), "f"),
        "discount_amount": format(_money(discount, "Discount amount"), "f"),
        "discounted_subtotal": format(_money(discounted, "Discounted subtotal"), "f"),
        "total": format(_money(order["total"], "Order total"), "f"),
    }


def promotion_idempotency_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def idempotency_replay(connection: sqlite3.Connection, operation: str, key: str | None, payload: dict[str, Any]):
    if not key:
        return None
    row = connection.execute(
        "SELECT operation,request_hash,response_json FROM idempotency_keys WHERE key=?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    if row["operation"] != operation or row["request_hash"] != promotion_idempotency_hash(payload):
        raise HTTPException(status_code=409, detail="Idempotency key was already used for a different request")
    return json.loads(row["response_json"])


def save_idempotent_response(
    connection: sqlite3.Connection,
    operation: str,
    key: str | None,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> None:
    if key:
        connection.execute(
            "INSERT INTO idempotency_keys(key,operation,request_hash,response_json,created_at) VALUES (?,?,?,?,?)",
            (key, operation, promotion_idempotency_hash(payload), json.dumps(response, sort_keys=True), now_iso()),
        )


def _promotion_for_code(connection: sqlite3.Connection, code: str):
    row = connection.execute("SELECT * FROM promotions WHERE code=?", (code,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return row


def create_promotion(
    connection: sqlite3.Connection,
    payload: PromotionCreateIn,
    *,
    actor_user_id: int | None,
    path: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    values = promotion_definition_payload(payload)
    key = normalize_idempotency_key(idempotency_key or payload.idempotency_key)
    request_payload = {"operation": "create", **values}
    replay = idempotency_replay(connection, "promotion.create", key, request_payload)
    if replay is not None:
        return replay
    try:
        cursor = connection.execute(
            """
            INSERT INTO promotions
                (code,name,discount_type,value,starts_on,ends_on,usage_limit,usage_count,active,created_at,created_by_user_id)
            VALUES (?,?,?,?,?,?,?,0,?,?,?)
            """,
            (
                values["code"],
                values["name"],
                values["discount_type"],
                values["value"],
                values["starts_on"],
                values["ends_on"],
                values["usage_limit"],
                1 if values["active"] else 0,
                now_iso(),
                actor_user_id,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Promotion code already exists") from exc
    row = connection.execute("SELECT * FROM promotions WHERE id=?", (cursor.lastrowid,)).fetchone()
    record_event_in_connection(
        connection,
        actor_user_id,
        "promotion.created",
        path,
        f"promotion_id={cursor.lastrowid};code={values['code']}",
    )
    result = promotion_view(row)
    save_idempotent_response(connection, "promotion.create", key, request_payload, result)
    return result


def apply_promotion(
    connection: sqlite3.Connection,
    order_id: int,
    code: str,
    *,
    actor_user_id: int | None,
    path: str,
    idempotency_key: str | None,
    response_builder: Callable[[sqlite3.Connection, int], dict[str, Any]],
) -> dict[str, Any]:
    key = normalize_idempotency_key(idempotency_key, required=True)
    normalized_code = code.strip().upper()
    request_payload = {"order_id": order_id, "code": normalized_code}
    operation = f"promotion.apply:{order_id}"
    replay = idempotency_replay(connection, operation, key, request_payload)
    if replay is not None:
        return replay

    order = connection.execute("SELECT * FROM restaurant_orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        raise HTTPException(status_code=404, detail="Restaurant order not found")
    if order["order_channel"] not in {"counter", "table", "delivery"}:
        raise HTTPException(status_code=409, detail="Promotions are available only for manual and delivery orders")
    if order["status"] not in {"open", "awaiting_payment"}:
        raise HTTPException(status_code=409, detail="Promotions can only be changed before payment")

    promotion = _promotion_for_code(connection, normalized_code)
    existing = current_applied_promotion(connection, order_id)
    if existing and existing["promotion_id"] == promotion["id"]:
        response = response_builder(connection, order_id)
        save_idempotent_response(connection, operation, key, request_payload, response)
        return response

    status = _promotion_status(promotion)
    if status != "active":
        raise HTTPException(status_code=409, detail=f"Promotion is {status}")

    if existing:
        connection.execute("DELETE FROM applied_promotions WHERE id=?", (existing["id"],))
        connection.execute(
            "UPDATE promotions SET usage_count=CASE WHEN usage_count > 0 THEN usage_count-1 ELSE 0 END WHERE id=?",
            (existing["promotion_id"],),
        )

    # BEGIN IMMEDIATE in the API handler serializes this check and increment.
    incremented = connection.execute(
        """
        UPDATE promotions
        SET usage_count=usage_count+1
        WHERE id=? AND active=1 AND (usage_limit IS NULL OR usage_count < usage_limit)
        """,
        (promotion["id"],),
    )
    if incremented.rowcount != 1:
        raise HTTPException(status_code=409, detail="Promotion usage limit has been reached")

    original = _order_original_subtotal(connection, order_id)
    provisional_applied = {
        "id": 0,
        "promotion_id": promotion["id"],
        "code": promotion["code"],
        "name": promotion["name"],
        "discount_type": promotion["discount_type"],
        "value": promotion["value"],
    }
    discount = _discount_amount(provisional_applied, original)
    discounted = _money(original - discount, "Discounted subtotal")
    stamp = now_iso()
    cursor = connection.execute(
        """
        INSERT INTO applied_promotions
            (order_id,promotion_id,code,name,discount_type,value,discount_amount,original_subtotal,discounted_subtotal,applied_at,applied_by_user_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            order_id,
            promotion["id"],
            promotion["code"],
            promotion["name"],
            promotion["discount_type"],
            promotion["value"],
            str(discount),
            str(original),
            str(discounted),
            stamp,
            actor_user_id,
        ),
    )
    reprice_order(connection, order_id)
    record_event_in_connection(
        connection,
        actor_user_id,
        "promotion.applied",
        path,
        f"order_id={order_id};promotion_id={promotion['id']};applied_id={cursor.lastrowid}",
    )
    response = response_builder(connection, order_id)
    save_idempotent_response(connection, operation, key, request_payload, response)
    return response


def remove_promotion(
    connection: sqlite3.Connection,
    order_id: int,
    applied_id: int,
    *,
    actor_user_id: int | None,
    path: str,
    idempotency_key: str | None,
    response_builder: Callable[[sqlite3.Connection, int], dict[str, Any]],
) -> dict[str, Any]:
    key = normalize_idempotency_key(idempotency_key, required=True)
    request_payload = {"order_id": order_id, "applied_id": applied_id}
    operation = f"promotion.remove:{order_id}"
    replay = idempotency_replay(connection, operation, key, request_payload)
    if replay is not None:
        return replay

    order = connection.execute("SELECT * FROM restaurant_orders WHERE id=?", (order_id,)).fetchone()
    if order is None:
        raise HTTPException(status_code=404, detail="Restaurant order not found")
    if order["order_channel"] not in {"counter", "table", "delivery"}:
        raise HTTPException(status_code=409, detail="Promotions are available only for manual and delivery orders")
    if order["status"] not in {"open", "awaiting_payment"}:
        raise HTTPException(status_code=409, detail="Promotions can only be changed before payment")
    applied = connection.execute(
        "SELECT * FROM applied_promotions WHERE id=? AND order_id=?",
        (applied_id, order_id),
    ).fetchone()
    if applied is None:
        raise HTTPException(status_code=404, detail="Applied promotion not found")

    connection.execute("DELETE FROM applied_promotions WHERE id=?", (applied_id,))
    connection.execute(
        "UPDATE promotions SET usage_count=CASE WHEN usage_count > 0 THEN usage_count-1 ELSE 0 END WHERE id=?",
        (applied["promotion_id"],),
    )
    reprice_order(connection, order_id)
    record_event_in_connection(
        connection,
        actor_user_id,
        "promotion.removed",
        path,
        f"order_id={order_id};applied_id={applied_id};promotion_id={applied['promotion_id']}",
    )
    response = response_builder(connection, order_id)
    save_idempotent_response(connection, operation, key, request_payload, response)
    return response


def receipt_promotion_values(connection: sqlite3.Connection, order_id: int) -> tuple[Any, ...]:
    applied = current_applied_promotion(connection, order_id)
    if applied is None:
        return (None, None, None, None, None, "0.00", None, None)
    return (
        applied["promotion_id"],
        applied["code"],
        applied["name"],
        applied["discount_type"],
        applied["value"],
        applied["discount_amount"],
        applied["original_subtotal"],
        applied["discounted_subtotal"],
    )
