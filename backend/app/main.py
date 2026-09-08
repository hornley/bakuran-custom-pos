from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from .db import connect, initialize
from .auth import (
    AUTH_ALLOWED_ORIGINS,
    AuthMiddleware,
    initialize_auth,
    record_event_in_connection,
    router as auth_router,
)

try:
    from .generated_metadata import EXPORT_STATUS, FRONTEND_TEMPLATE, PROJECT_NAME, TARGET_STACK
except ImportError:
    PROJECT_NAME, TARGET_STACK, FRONTEND_TEMPLATE, EXPORT_STATUS = "Restaurant Management", "react_fastapi_sqlite", "operational_desk", "generated"

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

@asynccontextmanager
async def lifespan(_):
    initialize()
    initialize_auth()
    yield

app = FastAPI(title=PROJECT_NAME, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=AUTH_ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(AuthMiddleware)
app.include_router(auth_router)

class LineIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(gt=0)
class PaymentIn(BaseModel):
    amount: float = Field(gt=0)
    method: str
    @field_validator("method")
    @classmethod
    def method_valid(cls, value):
        value = value.strip().lower()
        if value not in {"cash", "test_card", "bank_transfer"}:
            raise ValueError("method must be cash, test_card, or bank_transfer")
        return value

class OrderConfirmIn(BaseModel):
    customer_name: str = Field(min_length=1, max_length=80)

class OrderStartIn(BaseModel):
    customer_name: str = Field(default="", max_length=80)
    order_channel: str = Field(default="table", max_length=20)

    @field_validator("order_channel")
    @classmethod
    def order_channel_valid(cls, value):
        value = value.strip().lower()
        if value not in {"table", "qr", "counter", "delivery"}:
            raise ValueError("order_channel must be table, qr, counter, or delivery")
        return value


class DeliveryMetadataIn(BaseModel):
    address: str = Field(min_length=5, max_length=240)
    contact: str = Field(min_length=7, max_length=40)
    contact_name: str = Field(default="", max_length=80)

    @field_validator("address")
    @classmethod
    def address_normalized(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError("value is too short")
        return value

    @field_validator("contact")
    @classmethod
    def contact_normalized(cls, value):
        value = value.strip()
        if len(value) < 7:
            raise ValueError("value is too short")
        return value

    @field_validator("contact")
    @classmethod
    def contact_valid(cls, value):
        if not any(character.isdigit() for character in value) or not all(character.isdigit() or character in "+- ()" for character in value):
            raise ValueError("contact must contain a phone number")
        return value

    @field_validator("contact_name")
    @classmethod
    def contact_name_normalized(cls, value):
        return value.strip()


class DeliveryAssignmentIn(BaseModel):
    driver_id: int = Field(gt=0)


class DeliveryTransitionIn(BaseModel):
    reason: str = Field(default="", max_length=240)

    @field_validator("reason")
    @classmethod
    def reason_normalized(cls, value):
        return value.strip()


class DeliveryCallbackIn(DeliveryTransitionIn):
    status: str = Field(min_length=1, max_length=32)
    callback_id: str = Field(min_length=1, max_length=160)

    @field_validator("status")
    @classmethod
    def callback_status_valid(cls, value):
        value = value.strip().lower()
        if value not in {"out_for_delivery", "delivered", "failed", "cancelled"}:
            raise ValueError("callback status must be out_for_delivery, delivered, failed, or cancelled")
        return value

    @field_validator("callback_id")
    @classmethod
    def callback_id_normalized(cls, value):
        return value.strip()

def rows(c, sql, params=()): return [dict(x) for x in c.execute(sql, params).fetchall()]
def fail(message, status=400): raise HTTPException(status_code=status, detail=message)
def get(c, table, ident):
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (ident,)).fetchone()
    if not row: fail(f"{table.replace('_',' ').title()} not found", 404)
    return row


def _actor_user_id(request: Request) -> int | None:
    user = getattr(request.state, "auth_user", None)
    return user.get("id") if user else None


def _delivery_audit(c, request: Request, event_type: str, detail: str = "") -> None:
    record_event_in_connection(c, _actor_user_id(request), event_type, request.url.path, detail)


def _delivery_record(c, delivery_id: int):
    row = c.execute(
        """
        SELECT d.*, o.order_number, o.customer_name, o.total AS order_total,
               o.status AS order_status, o.order_channel
        FROM delivery_orders d
        JOIN restaurant_orders o ON o.id = d.order_id
        WHERE d.id = ?
        """,
        (delivery_id,),
    ).fetchone()
    if not row:
        fail("Delivery order not found", 404)
    delivery = dict(row)
    driver = c.execute(
        "SELECT id, code, name, contact, active FROM delivery_drivers WHERE id = ?",
        (delivery["driver_id"],),
    ).fetchone() if delivery["driver_id"] else None
    delivery["driver"] = dict(driver) if driver else None
    delivery["assignments"] = rows(
        c,
        """
        SELECT a.id, a.delivery_id, a.driver_id, a.status, a.assigned_at,
               a.unassigned_at, d.code AS driver_code, d.name AS driver_name,
               d.contact AS driver_contact
        FROM delivery_assignments a
        JOIN delivery_drivers d ON d.id = a.driver_id
        WHERE a.delivery_id = ?
        ORDER BY a.id
        """,
        (delivery_id,),
    )
    return delivery


def delivery_view(c, delivery_id: int):
    return {"delivery": _delivery_record(c, delivery_id)}


def _delivery_for_order(c, order_id: int):
    row = c.execute("SELECT id FROM delivery_orders WHERE order_id = ?", (order_id,)).fetchone()
    return _delivery_record(c, row["id"]) if row else None


def _idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 160:
        fail("Idempotency-Key is too long", 422)
    return value


def _request_hash(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _idempotency_replay(c, delivery_id: int, operation: str, key: str | None, request_hash: str):
    if not key:
        return None
    row = c.execute(
        """
        SELECT request_hash, response_json
        FROM delivery_idempotency_keys
        WHERE delivery_id = ? AND operation = ? AND idempotency_key = ?
        """,
        (delivery_id, operation, key),
    ).fetchone()
    if not row:
        return None
    if row["request_hash"] != request_hash:
        fail("Idempotency-Key was already used with a different request", 409)
    return json.loads(row["response_json"])


def _idempotency_store(c, delivery_id: int, operation: str, key: str | None, request_hash: str, response: dict) -> None:
    if not key:
        return
    c.execute(
        """
        INSERT INTO delivery_idempotency_keys
            (delivery_id, operation, idempotency_key, request_hash, response_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (delivery_id, operation, key, request_hash, json.dumps(response, sort_keys=True), now_iso()),
    )


def _delivery_payment_required(c, delivery_id: int):
    delivery = get(c, "delivery_orders", delivery_id)
    order = get(c, "restaurant_orders", delivery["order_id"])
    if order["order_channel"] != "delivery":
        fail("Delivery metadata belongs to a non-delivery order", 409)
    if order["status"] != "paid":
        fail("Cash payment is required before delivery assignment", 409)
    if not c.execute("SELECT 1 FROM payments WHERE order_id = ? AND status = 'paid'", (order["id"],)).fetchone():
        fail("Paid delivery order has no payment", 409)
    return delivery, order
def order_view(c, oid):
    o = get(c, "restaurant_orders", oid)
    return {
        "order": dict(o),
        "lines": rows(c, "SELECT * FROM restaurant_order_lines WHERE order_id=? ORDER BY id", (oid,)),
        "ticket": next(iter(rows(c, "SELECT * FROM kitchen_tickets WHERE order_id=?", (oid,))), None),
        "payment": next(iter(rows(c, "SELECT * FROM payments WHERE order_id=?", (oid,))), None),
        "receipt": next(iter(rows(c, "SELECT * FROM receipts WHERE order_id=?", (oid,))), None),
        "delivery": _delivery_for_order(c, oid),
    }
def table_view(c, table_id):
    t = dict(get(c, "dining_tables", table_id)); s = c.execute("SELECT * FROM table_sessions WHERE table_id=? AND status='open'", (table_id,)).fetchone(); t["session"] = dict(s) if s else None
    if s: t["order"] = next(iter(rows(c, "SELECT * FROM restaurant_orders WHERE session_id=? AND status!='closed'", (s["id"],))), None)
    return t

def create_ticket(c, order_id, stamp=None):
    existing = c.execute("SELECT * FROM kitchen_tickets WHERE order_id=?", (order_id,)).fetchone()
    if existing:
        return dict(existing)
    stamp = stamp or now_iso()
    n = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM kitchen_tickets").fetchone()[0]
    c.execute("INSERT INTO kitchen_tickets VALUES(?,?,?,'queued','main',?,?,NULL,NULL)", (n, f"KIT-{n:04d}", order_id, stamp, None))
    return dict(get(c, "kitchen_tickets", n))

def transition(ticket_id, expected, target, column):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE"); t = get(c, "kitchen_tickets", ticket_id)
        if t["status"] == target: c.commit(); return dict(t)
        if t["status"] != expected: fail(f"Kitchen ticket {t['ticket_number']} must be {expected} before {target}; current status is {t['status']}", 409)
        c.execute(f"UPDATE kitchen_tickets SET status=?,{column}=? WHERE id=?", (target, now_iso(), ticket_id)); c.commit(); return dict(get(c, "kitchen_tickets", ticket_id))
    except HTTPException: c.rollback(); raise
    finally: c.close()

@app.get("/api/health")
def health():
    try:
        with connect() as c:
            required = {
                "schema_migrations", "dining_tables", "menu_items", "table_sessions", "restaurant_orders", "receipts",
                "audit_events", "delivery_drivers", "delivery_orders", "delivery_assignments", "delivery_idempotency_keys",
            }
            available = {row["name"] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(required - available)
            if missing:
                raise RuntimeError(f"missing tables: {', '.join(missing)}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database is not ready: {exc}") from exc
    return {"status":"ok", "database_ready":True, "project_name":PROJECT_NAME, "target_stack":TARGET_STACK, "frontend_template":FRONTEND_TEMPLATE, "export_status":EXPORT_STATUS}
@app.get("/api/tables")
def tables():
    with connect() as c: return [table_view(c, r["id"]) for r in c.execute("SELECT id FROM dining_tables ORDER BY id")]
@app.get("/api/menu")
def menu():
    with connect() as c: return rows(c, "SELECT m.*, c.code category_code, c.name category_name FROM menu_items m JOIN menu_categories c ON c.id=m.category_id WHERE m.active=1 AND c.active=1 ORDER BY c.id,m.id")
@app.get("/api/orders")
def orders():
    with connect() as c:
        values = rows(c, "SELECT o.*,t.id table_id,t.code table_code FROM restaurant_orders o JOIN table_sessions s ON s.id=o.session_id JOIN dining_tables t ON t.id=s.table_id ORDER BY o.id DESC")
        for value in values:
            value["lines"] = rows(c, "SELECT * FROM restaurant_order_lines WHERE order_id=? ORDER BY id", (value["id"],))
        return values
@app.get("/api/orders/{oid}")
def order_detail(oid: int):
    with connect() as c: return order_view(c, oid)


@app.post("/api/orders/{oid}/delivery")
def save_delivery_metadata(oid: int, x: DeliveryMetadataIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        order = get(c, "restaurant_orders", oid)
        if order["order_channel"] != "delivery":
            fail("Only delivery orders can have delivery metadata", 409)
        if order["status"] not in {"open", "awaiting_payment"}:
            fail("Delivery metadata cannot be changed after payment", 409)
        existing = c.execute("SELECT id FROM delivery_orders WHERE order_id = ?", (oid,)).fetchone()
        stamp = now_iso()
        if existing:
            delivery_id = existing["id"]
            c.execute(
                """
                UPDATE delivery_orders
                SET address = ?, contact = ?, contact_name = ?, updated_at = ?
                WHERE id = ? AND order_id = ?
                """,
                (x.address, x.contact, x.contact_name, stamp, delivery_id, oid),
            )
            _delivery_audit(c, request, "delivery.metadata_updated", f"delivery_id={delivery_id} order_id={oid}")
        else:
            cursor = c.execute(
                """
                INSERT INTO delivery_orders
                    (order_id, address, contact, contact_name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (oid, x.address, x.contact, x.contact_name, stamp, stamp),
            )
            delivery_id = cursor.lastrowid
            _delivery_audit(c, request, "delivery.created", f"delivery_id={delivery_id} order_id={oid}")
        c.commit()
        return order_view(c, oid)
    except HTTPException:
        c.rollback()
        raise
    except sqlite3.IntegrityError as error:
        c.rollback()
        fail(f"Delivery metadata could not be saved: {error}", 409)
    finally:
        c.close()


@app.get("/api/delivery/drivers")
def delivery_drivers():
    with connect() as c:
        return rows(
            c,
            """
            SELECT id, code, name, contact, active, created_at
            FROM delivery_drivers
            WHERE active = 1
            ORDER BY name, id
            """,
        )


@app.get("/api/delivery")
def delivery_board(status: str | None = Query(default=None)):
    if status is not None and status not in {"pending", "assigned", "out_for_delivery", "delivered", "failed", "cancelled"}:
        fail("Unknown delivery status", 422)
    with connect() as c:
        if status is None:
            delivery_ids = rows(
                c,
                """
                SELECT d.id
                FROM delivery_orders d
                JOIN restaurant_orders o ON o.id = d.order_id
                WHERE EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.id AND p.status = 'paid')
                ORDER BY d.updated_at DESC, d.id DESC
                """,
            )
        else:
            delivery_ids = rows(
                c,
                """
                SELECT d.id
                FROM delivery_orders d
                JOIN restaurant_orders o ON o.id = d.order_id
                WHERE d.status = ?
                  AND EXISTS (SELECT 1 FROM payments p WHERE p.order_id = o.id AND p.status = 'paid')
                ORDER BY d.updated_at DESC, d.id DESC
                """,
                (status,),
            )
        return [_delivery_record(c, value["id"]) for value in delivery_ids]


@app.get("/api/delivery/{delivery_id}")
def delivery_detail(delivery_id: int):
    with connect() as c:
        return delivery_view(c, delivery_id)


@app.post("/api/delivery/{delivery_id}/assign")
def assign_delivery(
    delivery_id: int,
    x: DeliveryAssignmentIn,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        delivery = get(c, "delivery_orders", delivery_id)
        key = _idempotency_key(idempotency_key)
        request_hash = _request_hash({"driver_id": x.driver_id})
        replay = _idempotency_replay(c, delivery_id, "assign", key, request_hash)
        if replay is not None:
            c.commit()
            return replay
        delivery, _order = _delivery_payment_required(c, delivery_id)
        if delivery["status"] not in {"pending", "assigned"}:
            fail(f"Delivery cannot be assigned from {delivery['status']}", 409)
        driver = c.execute("SELECT * FROM delivery_drivers WHERE id = ? AND active = 1", (x.driver_id,)).fetchone()
        if not driver:
            fail("Active delivery driver not found", 404)
        active_assignment = c.execute(
            "SELECT * FROM delivery_assignments WHERE delivery_id = ? AND status = 'active'",
            (delivery_id,),
        ).fetchone()
        if delivery["status"] == "assigned" and delivery["driver_id"] == x.driver_id and active_assignment:
            response = delivery_view(c, delivery_id)
            _idempotency_store(c, delivery_id, "assign", key, request_hash, response)
            c.commit()
            return response

        stamp = now_iso()
        previous_driver_id = active_assignment["driver_id"] if active_assignment else delivery["driver_id"]
        if active_assignment:
            c.execute(
                "UPDATE delivery_assignments SET status = 'reassigned', unassigned_at = ? WHERE id = ? AND status = 'active'",
                (stamp, active_assignment["id"]),
            )
        c.execute(
            "INSERT INTO delivery_assignments(delivery_id, driver_id, status, assigned_at) VALUES (?, ?, 'active', ?)",
            (delivery_id, x.driver_id, stamp),
        )
        c.execute(
            """
            UPDATE delivery_orders
            SET status = 'assigned', driver_id = ?, assigned_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (x.driver_id, stamp, stamp, delivery_id),
        )
        event_type = "delivery.reassigned" if previous_driver_id and previous_driver_id != x.driver_id else "delivery.assigned"
        _delivery_audit(c, request, event_type, f"delivery_id={delivery_id} driver_id={x.driver_id}")
        response = delivery_view(c, delivery_id)
        _idempotency_store(c, delivery_id, "assign", key, request_hash, response)
        c.commit()
        return response
    except HTTPException:
        c.rollback()
        raise
    except sqlite3.IntegrityError as error:
        c.rollback()
        fail(f"Delivery assignment conflict: {error}", 409)
    finally:
        c.close()


def _transition_delivery(
    delivery_id: int,
    target: str,
    request: Request,
    *,
    reason: str = "",
    operation: str,
    idempotency_key: str | None = None,
    request_payload: dict | None = None,
):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        delivery = get(c, "delivery_orders", delivery_id)
        key = _idempotency_key(idempotency_key)
        request_hash = _request_hash(request_payload or {"status": target, "reason": reason})
        replay = _idempotency_replay(c, delivery_id, operation, key, request_hash)
        if replay is not None:
            c.commit()
            return replay
        delivery, _order = _delivery_payment_required(c, delivery_id)
        current = delivery["status"]
        if target in {"out_for_delivery", "delivered"} and current == target:
            response = delivery_view(c, delivery_id)
            _idempotency_store(c, delivery_id, operation, key, request_hash, response)
            c.commit()
            return response
        if target in {"failed", "cancelled"} and not reason:
            fail(f"A reason is required to mark a delivery {target}", 422)
        allowed = {
            "out_for_delivery": {"assigned"},
            "delivered": {"out_for_delivery"},
            "failed": {"pending", "assigned", "out_for_delivery"},
            "cancelled": {"pending", "assigned", "out_for_delivery"},
        }[target]
        if current not in allowed:
            fail(f"Delivery must be {', '.join(sorted(allowed))} before {target}; current status is {current}", 409)
        if target in {"out_for_delivery", "delivered"} and not c.execute(
            "SELECT 1 FROM delivery_assignments WHERE delivery_id = ? AND status = 'active'", (delivery_id,)
        ).fetchone():
            fail("Delivery has no active driver assignment", 409)

        stamp = now_iso()
        updates = ["status = ?", "updated_at = ?"]
        params: list = [target, stamp]
        event_type = f"delivery.{target}"
        if target == "out_for_delivery":
            updates.append("out_for_delivery_at = ?")
            params.append(stamp)
        elif target == "delivered":
            updates.append("delivered_at = ?")
            params.append(stamp)
        elif target == "failed":
            updates.append("failure_reason = ?")
            params.append(reason)
            updates.append("failed_at = ?")
            params.append(stamp)
        else:
            updates.append("cancellation_reason = ?")
            params.append(reason)
            updates.append("cancelled_at = ?")
            params.append(stamp)
        params.append(delivery_id)
        c.execute(f"UPDATE delivery_orders SET {', '.join(updates)} WHERE id = ?", params)
        assignment_status = {"delivered": "completed", "failed": "failed", "cancelled": "cancelled"}.get(target)
        if assignment_status:
            c.execute(
                "UPDATE delivery_assignments SET status = ?, unassigned_at = ? WHERE delivery_id = ? AND status = 'active'",
                (assignment_status, stamp, delivery_id),
            )
        detail = f"delivery_id={delivery_id}"
        if reason:
            detail += f" reason={reason}"
        _delivery_audit(c, request, event_type, detail)
        response = delivery_view(c, delivery_id)
        _idempotency_store(c, delivery_id, operation, key, request_hash, response)
        c.commit()
        return response
    except HTTPException:
        c.rollback()
        raise
    except sqlite3.IntegrityError as error:
        c.rollback()
        fail(f"Delivery transition conflict: {error}", 409)
    finally:
        c.close()


@app.post("/api/delivery/{delivery_id}/out-for-delivery")
def out_for_delivery(
    delivery_id: int,
    request: Request,
    x: DeliveryTransitionIn | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _transition_delivery(
        delivery_id,
        "out_for_delivery",
        request,
        operation="out_for_delivery",
        idempotency_key=idempotency_key,
        request_payload={"status": "out_for_delivery"},
    )


@app.post("/api/delivery/{delivery_id}/delivered")
def delivered(
    delivery_id: int,
    request: Request,
    x: DeliveryTransitionIn | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return _transition_delivery(
        delivery_id,
        "delivered",
        request,
        operation="delivered",
        idempotency_key=idempotency_key,
        request_payload={"status": "delivered"},
    )


@app.post("/api/delivery/{delivery_id}/failed")
def failed(
    delivery_id: int,
    request: Request,
    x: DeliveryTransitionIn | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    reason = x.reason if x else ""
    return _transition_delivery(
        delivery_id,
        "failed",
        request,
        reason=reason,
        operation="failed",
        idempotency_key=idempotency_key,
        request_payload={"status": "failed", "reason": reason},
    )


@app.post("/api/delivery/{delivery_id}/cancel")
def cancel_delivery(
    delivery_id: int,
    request: Request,
    x: DeliveryTransitionIn | None = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    reason = x.reason if x else ""
    return _transition_delivery(
        delivery_id,
        "cancelled",
        request,
        reason=reason,
        operation="cancelled",
        idempotency_key=idempotency_key,
        request_payload={"status": "cancelled", "reason": reason},
    )


@app.post("/api/delivery/{delivery_id}/callback")
def delivery_callback(delivery_id: int, x: DeliveryCallbackIn, request: Request):
    return _transition_delivery(
        delivery_id,
        x.status,
        request,
        reason=x.reason,
        operation="callback",
        idempotency_key=x.callback_id,
        request_payload={"status": x.status, "reason": x.reason, "callback_id": x.callback_id},
    )


@app.get("/api/audit-events")
def audit_events(limit: int = Query(default=200, ge=1, le=1000)):
    with connect() as c:
        return rows(
            c,
            """
            SELECT id, actor_user_id, event_type, path, detail, created_at
            FROM audit_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )


@app.get("/api/kitchen")
def kitchen(queue: str = Query("active", pattern="^(active|ready)$")):
    if queue == "ready":
        status_filter = "k.status IN ('ready','served')"
    else:
        status_filter = "k.status!='served'"
    with connect() as c: return rows(c, f"SELECT k.*,o.order_number,o.customer_name,o.order_channel,t.code table_code FROM kitchen_tickets k JOIN restaurant_orders o ON o.id=k.order_id JOIN table_sessions s ON s.id=o.session_id JOIN dining_tables t ON t.id=s.table_id WHERE o.status!='closed' AND {status_filter} ORDER BY k.id")
@app.get("/api/dashboard")
def dashboard():
    today_prefix = f"{now_iso()[:10]}%"
    with connect() as c: return {"metrics":{"open_tables":c.execute("SELECT COUNT(*) FROM table_sessions WHERE status='open'").fetchone()[0],"active_orders":c.execute("SELECT COUNT(*) FROM restaurant_orders WHERE status!='closed'").fetchone()[0],"kitchen_queue":c.execute("SELECT COUNT(*) FROM kitchen_tickets WHERE status!='served'").fetchone()[0],"today_revenue":c.execute("SELECT COALESCE(SUM(total),0) FROM restaurant_orders WHERE status='closed' AND closed_at LIKE ?", (today_prefix,)).fetchone()[0]},"tables":tables(),"menu":menu(),"kitchen":kitchen()}
@app.post("/api/tables/{tid}/open")
def open_table(tid: int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); t=get(c,"dining_tables",tid)
        if c.execute("SELECT 1 FROM table_sessions WHERE table_id=? AND status='open'",(tid,)).fetchone(): fail("Table already has an active session",409)
        n=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM table_sessions").fetchone()[0]; c.execute("UPDATE dining_tables SET status='occupied' WHERE id=?",(tid,)); c.execute("INSERT INTO table_sessions VALUES(?,?,?,'open',?,NULL)",(n,f"SES-{n:04d}",tid,now_iso())); c.commit(); return table_view(c,tid)
    except (HTTPException,sqlite3.IntegrityError) as e: c.rollback(); fail(str(e),409)
    finally:c.close()
@app.post("/api/sessions/{sid}/orders")
def create_order(sid: int, x: OrderStartIn | None = None):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); s=get(c,"table_sessions",sid)
        if s["status"]!="open": fail("Session must be open",409)
        if c.execute("SELECT 1 FROM restaurant_orders WHERE session_id=? AND status!='closed'",(sid,)).fetchone(): fail("Session already has an active order",409)
        n=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM restaurant_orders").fetchone()[0]
        c.execute("INSERT INTO restaurant_orders(id,order_number,session_id,status,subtotal,total,created_at,sent_at,served_at,paid_at,closed_at,customer_name,order_channel) VALUES(?,?,?,'open',0,0,?,NULL,NULL,NULL,NULL,?,?)", (n, f"ORD-{n:04d}", sid, now_iso(), (x.customer_name.strip() if x else ""), (x.order_channel if x else "table")))
        c.commit(); return order_view(c,n)
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/counter/orders")
def create_counter_order(x: OrderStartIn | None = None):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        counter = c.execute("SELECT id FROM dining_tables WHERE code='COUNTER'").fetchone()
        if not counter:
            fail("Counter pickup context is not initialized", 503)
        session_id = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM table_sessions").fetchone()[0]
        stamp = now_iso()
        c.execute("INSERT INTO table_sessions(id,session_number,table_id,status,opened_at,closed_at) VALUES(?,?,?,'counter',?,NULL)", (session_id, f"SES-{session_id:04d}", counter["id"], stamp))
        order_id = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM restaurant_orders").fetchone()[0]
        c.execute("INSERT INTO restaurant_orders(id,order_number,session_id,status,subtotal,total,created_at,sent_at,served_at,paid_at,closed_at,customer_name,order_channel) VALUES(?,?,?,'open',0,0,?,NULL,NULL,NULL,NULL,?,?)", (order_id, f"ORD-{order_id:04d}", session_id, stamp, (x.customer_name.strip() if x else ""), (x.order_channel if x else "counter")))
        c.commit()
        return order_view(c, order_id)
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()

@app.post("/api/orders/{oid}/confirm")
def confirm_order(oid: int, x: OrderConfirmIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = get(c, "restaurant_orders", oid)
        if o["status"] != "open":
            fail("Only open orders can be confirmed", 409)
        if not c.execute("SELECT 1 FROM restaurant_order_lines WHERE order_id=?", (oid,)).fetchone():
            fail("Cannot confirm an empty order", 409)
        if o["order_channel"] == "delivery" and not c.execute(
            "SELECT 1 FROM delivery_orders WHERE order_id = ?", (oid,)
        ).fetchone():
            fail("Delivery address and contact are required before confirmation", 422)
        c.execute("UPDATE restaurant_orders SET customer_name=?,status='awaiting_payment' WHERE id=?", (x.customer_name.strip(), oid))
        c.commit()
        return order_view(c, oid)
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()
@app.post("/api/orders/{oid}/lines")
def add_line(oid:int,x:LineIn):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); o=get(c,"restaurant_orders",oid)
        if o["status"]!="open": fail("Only open orders can be edited",409)
        item=c.execute("SELECT * FROM menu_items WHERE id=? AND active=1",(x.menu_item_id,)).fetchone()
        if not item: fail("Menu item not found or inactive",404)
        old=c.execute("SELECT quantity FROM restaurant_order_lines WHERE order_id=? AND menu_item_id=?",(oid,x.menu_item_id)).fetchone(); new_qty=x.quantity+(old[0] if old else 0)
        if old: c.execute("UPDATE restaurant_order_lines SET quantity=?,line_total=? WHERE order_id=? AND menu_item_id=?",(new_qty,new_qty*item["price"],oid,x.menu_item_id))
        else: c.execute("INSERT INTO restaurant_order_lines(order_id,menu_item_id,item_name,quantity,unit_price,line_total) VALUES(?,?,?,?,?,?)",(oid,x.menu_item_id,item["name"],x.quantity,item["price"],x.quantity*item["price"]))
        total=c.execute("SELECT COALESCE(SUM(line_total),0) FROM restaurant_order_lines WHERE order_id=?",(oid,)).fetchone()[0]; c.execute("UPDATE restaurant_orders SET subtotal=?,total=? WHERE id=?",(total,total,oid)); c.commit(); return order_view(c,oid)
    except HTTPException:c.rollback();raise
    finally:c.close()
@app.delete("/api/orders/{oid}/lines/{lid}")
def remove_line(oid:int,lid:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); o=get(c,"restaurant_orders",oid)
        if o["status"]!="open": fail("Only open orders can be edited",409)
        if not c.execute("DELETE FROM restaurant_order_lines WHERE id=? AND order_id=?",(lid,oid)).rowcount: fail("Order line not found",404)
        total=c.execute("SELECT COALESCE(SUM(line_total),0) FROM restaurant_order_lines WHERE order_id=?",(oid,)).fetchone()[0]; c.execute("UPDATE restaurant_orders SET subtotal=?,total=? WHERE id=?",(total,total,oid)); c.commit(); return order_view(c,oid)
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/orders/{oid}/send")
def send_order(oid:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); o=get(c,"restaurant_orders",oid)
        if o["status"] == "paid":
            create_ticket(c, oid)
            c.commit()
            return order_view(c, oid)
        if o["status"] in {"open", "awaiting_payment"}:
            fail("Payment is required before sending the order to kitchen", 409)
        fail("Order must be open before sending", 409)
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/kitchen/{ticket_id}/start")
def start(ticket_id:int): return transition(ticket_id,"queued","preparing","started_at")
@app.post("/api/kitchen/{ticket_id}/ready")
def ready(ticket_id:int): return transition(ticket_id,"preparing","ready","ready_at")
@app.post("/api/kitchen/{ticket_id}/serve")
def serve(ticket_id:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); t=get(c,"kitchen_tickets",ticket_id)
        if t["status"]=="served": c.commit(); return dict(t)
        if t["status"]!="ready": fail(f"Kitchen ticket {t['ticket_number']} must be ready before served; current status is {t['status']}",409)
        stamp = now_iso(); c.execute("UPDATE kitchen_tickets SET status='served',served_at=? WHERE id=?",(stamp,ticket_id)); c.execute("UPDATE restaurant_orders SET status='served',served_at=? WHERE id=? AND status IN ('sent','paid')",(stamp,t["order_id"])); c.commit(); return dict(get(c,"kitchen_tickets",ticket_id))
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/orders/{oid}/pay")
def pay(oid:int,x:PaymentIn):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); o=get(c,"restaurant_orders",oid)
        if o["order_channel"] == "delivery" and x.method != "cash":
            fail("Delivery orders accept cash payment only", 409)
        if o["status"]=="paid": c.commit(); return order_view(c, oid)
        if o["status"] != "awaiting_payment": fail("Order must be awaiting payment before payment",409)
        if abs(x.amount-o["total"])>0.001: fail("Payment amount must equal order total",409)
        if o["order_channel"] == "delivery" and not c.execute(
            "SELECT 1 FROM delivery_orders WHERE order_id = ?", (oid,)
        ).fetchone():
            fail("Delivery address and contact are required before payment", 422)
        stamp = now_iso(); n=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM payments").fetchone()[0]; c.execute("INSERT INTO payments VALUES(?,?,?,?,?,'paid',?)",(n,f"PAY-{n:04d}",oid,x.amount,x.method,stamp)); c.execute("UPDATE restaurant_orders SET status='paid',paid_at=? WHERE id=?",(stamp,oid));
        if o["status"] == "awaiting_payment":
            create_ticket(c, oid, stamp)
        c.commit(); return order_view(c,oid)
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/orders/{oid}/close")
def close_order(oid:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); o=get(c,"restaurant_orders",oid)
        if o["status"]=="closed": c.commit(); return order_view(c,oid)
        if o["status"] not in {"paid", "served"}: fail("Order must be paid before close",409)
        if not c.execute("SELECT 1 FROM payments WHERE order_id=?",(oid,)).fetchone(): fail("Paid order has no payment",409)
        stamp = now_iso(); n=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM receipts").fetchone()[0]; c.execute("INSERT INTO receipts VALUES(?,?,?,?,?)",(n,f"REC-{n:04d}",oid,o["total"],stamp)); c.execute("UPDATE restaurant_orders SET status='closed',closed_at=? WHERE id=?",(stamp,oid)); c.execute("UPDATE table_sessions SET status='closed',closed_at=? WHERE id=(SELECT session_id FROM restaurant_orders WHERE id=?)",(stamp,oid)); c.execute("UPDATE dining_tables SET status='available' WHERE id=(SELECT table_id FROM table_sessions WHERE id=(SELECT session_id FROM restaurant_orders WHERE id=?))",(oid,)); c.commit(); return order_view(c,oid)
    except HTTPException:c.rollback();raise
    finally:c.close()

@app.post("/api/tables/{tid}/close")
def close_table(tid:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); s=c.execute("SELECT * FROM table_sessions WHERE table_id=? AND status='open'",(tid,)).fetchone()
        if not s: fail("Table has no active session",409)
        o=c.execute("SELECT * FROM restaurant_orders WHERE session_id=? AND status!='closed'",(s["id"],)).fetchone()
        if o: fail("Active order must be paid and closed first",409)
        c.execute("UPDATE table_sessions SET status='closed',closed_at=? WHERE id=?",(now_iso(),s["id"])); c.execute("UPDATE dining_tables SET status='available' WHERE id=?",(tid,)); c.commit(); return table_view(c,tid)
    except HTTPException:c.rollback();raise
    finally:c.close()

# Bakuran composite operational resources. These handlers intentionally keep each mutation
# in a single BEGIN IMMEDIATE transaction so inventory and workflow state cannot drift.
class GenericIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    quantity: int = Field(default=1, ge=1)
    value: str | None = None
    product_id: int | None = None
    supplier_id: int | None = None
    unit_cost: float = Field(default=0, ge=0)


def _simple_rows(table: str):
    with connect() as c:
        return rows(c, f"SELECT * FROM {table} ORDER BY id DESC")


@app.get("/api/catalog")
def catalog():
    with connect() as c: return rows(c, "SELECT m.*, c.name category_name FROM menu_items m JOIN menu_categories c ON c.id=m.category_id ORDER BY m.id")
@app.get("/api/inventory")
def bakuran_inventory():
    with connect() as c: return {"products": rows(c, "SELECT m.id,m.sku,m.name,i.on_hand,i.reserved,i.updated_at FROM menu_items m JOIN inventory i ON i.product_id=m.id ORDER BY m.id"), "movements": rows(c, "SELECT * FROM stock_movements ORDER BY id DESC")}
@app.get("/api/customers")
def bakuran_customers(): return _simple_rows("customers")
@app.get("/api/suppliers")
def bakuran_suppliers(): return _simple_rows("suppliers")
@app.get("/api/settings")
def settings():
    with connect() as c: return {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings")}

@app.get("/api/receipts")
def receipts():
    with connect() as c:
        return rows(c, "SELECT r.*,o.order_number,t.code table_code FROM receipts r JOIN restaurant_orders o ON o.id=r.order_id JOIN table_sessions s ON s.id=o.session_id JOIN dining_tables t ON t.id=s.table_id ORDER BY r.id DESC")

@app.get("/api/payment-queue")
def payment_queue(q: str = ""):
    needle = f"%{q.strip()}%"
    with connect() as c:
        values = rows(c, "SELECT o.*,t.code table_code FROM restaurant_orders o JOIN table_sessions s ON s.id=o.session_id JOIN dining_tables t ON t.id=s.table_id WHERE o.status='awaiting_payment' AND (o.order_number LIKE ? OR o.customer_name LIKE ? OR t.code LIKE ?) ORDER BY o.id", (needle, needle, needle))
        for value in values:
            value["lines"] = rows(c, "SELECT * FROM restaurant_order_lines WHERE order_id=? ORDER BY id", (value["id"],))
        return values

@app.get("/api/search")
def search(q: str = ""):
    q = f"%{q.strip()}%"
    with connect() as c:
        return {"catalog": rows(c,"SELECT * FROM menu_items WHERE name LIKE ? OR sku LIKE ?",(q,q)), "customers": rows(c,"SELECT * FROM customers WHERE name LIKE ? OR code LIKE ?",(q,q)), "suppliers": rows(c,"SELECT * FROM suppliers WHERE name LIKE ? OR code LIKE ?",(q,q))}
@app.get("/api/notifications")
def notifications(): return _simple_rows("notifications")
@app.get("/api/attendance")
def attendance(): return _simple_rows("attendance")
@app.get("/api/purchases")
def purchases():
    with connect() as c: return rows(c,"SELECT p.*,s.name supplier_name FROM purchases p JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC")
@app.post("/api/purchases")
def create_purchase(x: GenericIn):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); sid=x.supplier_id or 1
        if not c.execute("SELECT 1 FROM suppliers WHERE id=? AND active=1",(sid,)).fetchone(): fail("Supplier not found",404)
        n=c.execute("SELECT COALESCE(MAX(id),0)+1 FROM purchases").fetchone()[0]
        c.execute("INSERT INTO purchases VALUES (?,?,?,'draft',0,?,NULL)",(n,f"PUR-{n:04d}",sid,now_iso())); c.commit(); return dict(c.execute("SELECT * FROM purchases WHERE id=?",(n,)).fetchone())
    except HTTPException: c.rollback(); raise
    finally: c.close()
@app.post("/api/purchases/{pid}/receive")
def receive_purchase(pid:int):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); p=c.execute("SELECT * FROM purchases WHERE id=?",(pid,)).fetchone()
        if not p: fail("Purchase not found",404)
        if p["status"] not in ("ordered","draft"): fail("Purchase cannot be received in its current state",409)
        lines=c.execute("SELECT * FROM purchase_lines WHERE purchase_id=?",(pid,)).fetchall()
        if not lines: fail("Purchase requires lines",409)
        for line in lines: c.execute("UPDATE inventory SET on_hand=on_hand+?,updated_at=? WHERE product_id=?",(line["quantity"],now_iso(),line["product_id"]))
        c.execute("UPDATE purchases SET status='received',received_at=? WHERE id=?",(now_iso(),pid)); c.commit(); return dict(c.execute("SELECT * FROM purchases WHERE id=?",(pid,)).fetchone())
    except HTTPException: c.rollback(); raise
    finally: c.close()
@app.post("/api/purchases/{pid}/lines")
def purchase_line(pid: int, x: GenericIn):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        purchase = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        if not purchase: fail("Purchase not found", 404)
        if purchase["status"] != "draft": fail("Only draft purchases can be edited", 409)
        product_id = x.product_id or 1
        product = c.execute("SELECT * FROM menu_items WHERE id=? AND active=1", (product_id,)).fetchone()
        if not product: fail("Product not found", 404)
        c.execute("INSERT INTO purchase_lines(purchase_id,product_id,quantity,unit_cost) VALUES(?,?,?,?)", (pid, product_id, x.quantity, x.unit_cost))
        total = c.execute("SELECT COALESCE(SUM(quantity*unit_cost),0) FROM purchase_lines WHERE purchase_id=?", (pid,)).fetchone()[0]
        c.execute("UPDATE purchases SET total=? WHERE id=?", (total, pid)); c.commit()
        return {"purchase": dict(c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()), "lines": rows(c, "SELECT * FROM purchase_lines WHERE purchase_id=?", (pid,))}
    except sqlite3.IntegrityError:
        c.rollback(); fail("Product is already on this purchase", 409)
    except HTTPException:
        c.rollback(); raise
    finally: c.close()
@app.post("/api/attendance")
def clock(x: GenericIn):
    with connect() as c:
        c.execute("INSERT INTO attendance(employee_name,status,occurred_at) VALUES (?,?,?)",(x.name,x.value or "in",now_iso())); return dict(c.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 1").fetchone())
@app.post("/api/stock/receipt")
def stock_receipt(x: GenericIn):
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE"); pid=x.product_id or 1
        if not c.execute("SELECT 1 FROM inventory WHERE product_id=?",(pid,)).fetchone(): fail("Product not found",404)
        c.execute("UPDATE inventory SET on_hand=on_hand+?,updated_at=? WHERE product_id=?",(x.quantity,now_iso(),pid)); c.execute("INSERT INTO stock_movements(product_id,movement_type,quantity,reference,created_at) VALUES(?,?,?,?,?)",(pid,'receipt',x.quantity,x.value or 'manual',now_iso())); c.commit(); return {"product_id":pid,"quantity":x.quantity}
    except HTTPException: c.rollback(); raise
    finally: c.close()

# Stable workflow-oriented aliases used by the composite frontend and API clients.
@app.get("/api/pos/transactions")
def pos_transactions(): return orders()
@app.get("/api/order-to-cash")
def order_to_cash(): return orders()
@app.get("/api/kitchen/tickets")
def kitchen_tickets(): return kitchen()
@app.get("/api/restaurant/service")
def restaurant_service(): return tables()
@app.get("/api/purchasing")
def purchasing(): return purchases()
@app.get("/api/stock/receipts")
def stock_receipts():
    with connect() as c: return rows(c, "SELECT * FROM stock_movements WHERE movement_type='receipt' ORDER BY id DESC")
