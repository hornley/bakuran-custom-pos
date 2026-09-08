from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from .db import REQUIRED_TABLES, connect, initialize
from .auth import AUTH_ALLOWED_ORIGINS, AuthMiddleware, initialize_auth, router as auth_router

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
        if value not in {"table", "qr", "counter"}:
            raise ValueError("order_channel must be table, qr, or counter")
        return value

def rows(c, sql, params=()): return [dict(x) for x in c.execute(sql, params).fetchall()]
def fail(message, status=400): raise HTTPException(status_code=status, detail=message)
def get(c, table, ident):
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (ident,)).fetchone()
    if not row: fail(f"{table.replace('_',' ').title()} not found", 404)
    return row
def order_view(c, oid):
    o = get(c, "restaurant_orders", oid)
    return {"order": dict(o), "lines": rows(c, "SELECT * FROM restaurant_order_lines WHERE order_id=? ORDER BY id", (oid,)), "ticket": next(iter(rows(c, "SELECT * FROM kitchen_tickets WHERE order_id=?", (oid,))), None), "payment": next(iter(rows(c, "SELECT * FROM payments WHERE order_id=?", (oid,))), None), "receipt": next(iter(rows(c, "SELECT * FROM receipts WHERE order_id=?", (oid,))), None)}
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
            required = REQUIRED_TABLES
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
        c.execute("INSERT INTO restaurant_orders(id,order_number,session_id,status,subtotal,total,created_at,sent_at,served_at,paid_at,closed_at,customer_name,order_channel) VALUES(?,?,?,'open',0,0,?,NULL,NULL,NULL,NULL,?,'counter')", (order_id, f"ORD-{order_id:04d}", session_id, stamp, (x.customer_name.strip() if x else "")))
        c.commit()
        return order_view(c, order_id)
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()

@app.post("/api/orders/{oid}/confirm")
def confirm_order(oid: int, x: OrderConfirmIn):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = get(c, "restaurant_orders", oid)
        if o["status"] != "open":
            fail("Only open orders can be confirmed", 409)
        if not c.execute("SELECT 1 FROM restaurant_order_lines WHERE order_id=?", (oid,)).fetchone():
            fail("Cannot confirm an empty order", 409)
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
        if o["status"]=="paid": c.commit(); return order_view(c, oid)
        if o["status"] != "awaiting_payment": fail("Order must be awaiting payment before payment",409)
        if abs(x.amount-o["total"])>0.001: fail("Payment amount must equal order total",409)
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
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class WarehouseIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("code", "name", mode="before")
    @classmethod
    def text_valid(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class StockAdjustmentIn(BaseModel):
    product_id: int = Field(gt=0)
    warehouse_id: int = Field(default=1, gt=0)
    quantity: int
    reason: str = Field(min_length=1, max_length=240)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("reason", mode="before")
    @classmethod
    def reason_valid(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class PurchaseLineIn(BaseModel):
    product_id: int = Field(default=1, gt=0)
    warehouse_id: int = Field(default=1, gt=0)
    quantity: int = Field(gt=0)
    unit_cost: float = Field(ge=0, allow_inf_nan=False)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("unit_cost", mode="before")
    @classmethod
    def unit_cost_valid(cls, value):
        try:
            finite_value = math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return value
        return value if finite_value else "non-finite unit_cost"

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class PurchaseReceiptLineIn(BaseModel):
    product_id: int = Field(gt=0)
    warehouse_id: int = Field(default=1, gt=0)
    quantity: int = Field(gt=0)


class PurchaseReceiptIn(BaseModel):
    lines: list[PurchaseReceiptLineIn] = Field(min_length=1)
    allow_over_receipt: bool = False
    override_reason: str | None = Field(default=None, max_length=240)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("override_reason", mode="before")
    @classmethod
    def override_reason_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class ReorderLevelIn(BaseModel):
    product_id: int = Field(gt=0)
    warehouse_id: int = Field(default=1, gt=0)
    reorder_level: int = Field(ge=0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


def _auth_user_id(request):
    user = getattr(request.state, "auth_user", None)
    return user["id"] if user else None


def _auth_roles(request):
    user = getattr(request.state, "auth_user", None)
    return set(user.get("roles", [])) if user else set()


def _audit(c, request, event_type, detail=""):
    user = getattr(request.state, "auth_user", None)
    actor_id = user["id"] if user else None
    c.execute(
        "INSERT INTO audit_events(actor_user_id,event_type,path,detail,created_at) VALUES (?,?,?,?,?)",
        (actor_id, event_type, request.url.path[:240], detail[:500], now_iso()),
    )


def _request_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _idempotent_response(c, operation, key, payload):
    if not key:
        return None
    row = c.execute("SELECT operation,request_hash,response_json FROM idempotency_keys WHERE key=?", (key,)).fetchone()
    if row and (row["operation"] != operation or row["request_hash"] != _request_hash(payload)):
        fail("Idempotency key was already used for a different request", 409)
    return json.loads(row["response_json"]) if row else None


def _save_idempotent_response(c, operation, key, payload, response):
    if key:
        c.execute(
            "INSERT INTO idempotency_keys(key,operation,request_hash,response_json,created_at) VALUES (?,?,?,?,?)",
            (key, operation, _request_hash(payload), json.dumps(response, sort_keys=True), now_iso()),
        )


def _require_override_authority(request):
    # Optional-auth deployments accept the same workflow for unauthenticated
    # operators, while an enabled auth deployment reserves overrides for admins
    # and managers. The middleware already authenticates every API request.
    if auth_enabled_for_request(request) and not (_auth_roles(request) & {"admin", "manager"}):
        fail("Manager or admin role is required for an over-receipt override", 403)


def auth_enabled_for_request(request):
    # Import lazily so tests and disabled deployments keep the existing path.
    from .auth import auth_enabled
    return auth_enabled()


class PurchaseCreateIn(BaseModel):
    supplier_id: int = Field(default=1, gt=0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


class PurchaseLifecycleIn(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def idempotency_key_valid(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be blank")
        return value


def _purchase_line_total(quantity, unit_cost):
    try:
        if not math.isfinite(unit_cost):
            fail("Purchase unit cost must be finite", 422)
        line_total = quantity * unit_cost
    except (OverflowError, TypeError, ValueError):
        fail("Purchase line total exceeds the supported numeric range", 422)
    if not math.isfinite(line_total):
        fail("Purchase line total exceeds the supported numeric range", 422)
    return line_total


def _purchase_total(line_totals):
    if any(not math.isfinite(line_total) for line_total in line_totals):
        fail("Purchase total exceeds the supported numeric range", 422)
    try:
        total = math.fsum(line_totals)
    except OverflowError:
        fail("Purchase total exceeds the supported numeric range", 422)
    if not math.isfinite(total):
        fail("Purchase total exceeds the supported numeric range", 422)
    return total


def _active_product(c, product_id):
    row = c.execute("SELECT id FROM menu_items WHERE id=? AND active=1", (product_id,)).fetchone()
    if not row:
        fail("Product not found", 404)
    return row


def _active_warehouse(c, warehouse_id):
    row = c.execute("SELECT id FROM warehouses WHERE id=? AND active=1", (warehouse_id,)).fetchone()
    if not row:
        fail("Warehouse not found", 404)
    return row


def _ensure_inventory_row(c, product_id, warehouse_id, stamp=None):
    row = c.execute(
        "SELECT * FROM inventory WHERE product_id=? AND warehouse_id=?",
        (product_id, warehouse_id),
    ).fetchone()
    if row:
        return row
    c.execute(
        "INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at,reorder_level) VALUES (?,?,0,0,?,5)",
        (product_id, warehouse_id, stamp or now_iso()),
    )
    return c.execute(
        "SELECT * FROM inventory WHERE product_id=? AND warehouse_id=?",
        (product_id, warehouse_id),
    ).fetchone()


def _simple_rows(table: str):
    with connect() as c:
        return rows(c, f"SELECT * FROM {table} ORDER BY id DESC")


@app.get("/api/catalog")
def catalog():
    with connect() as c: return rows(c, "SELECT m.*, c.name category_name FROM menu_items m JOIN menu_categories c ON c.id=m.category_id ORDER BY m.id")
@app.get("/api/warehouses")
def warehouses():
    with connect() as c:
        return rows(c, "SELECT * FROM warehouses WHERE active=1 ORDER BY id")


@app.post("/api/warehouses")
def create_warehouse(x: WarehouseIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {"code": x.code, "name": x.name}
        existing = _idempotent_response(c, "inventory.warehouse", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        try:
            n = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM warehouses").fetchone()[0]
            c.execute("INSERT INTO warehouses(id,code,name,active,created_at) VALUES (?,?,?,1,?)", (n, x.code, x.name, now_iso()))
            c.execute(
                """
                INSERT INTO inventory(product_id,warehouse_id,on_hand,reserved,updated_at,reorder_level)
                SELECT id, ?, 0, 0, ?, 5 FROM menu_items WHERE active=1
                """,
                (n, now_iso()),
            )
        except sqlite3.IntegrityError:
            fail("Warehouse code already exists", 409)
        _audit(c, request, "inventory.warehouse_created", x.code)
        result = dict(c.execute("SELECT * FROM warehouses WHERE id=?", (n,)).fetchone())
        _save_idempotent_response(c, "inventory.warehouse", x.idempotency_key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


def _inventory_rows(c, warehouse_id=None):
    params = () if warehouse_id is None else (warehouse_id,)
    where = "" if warehouse_id is None else " AND i.warehouse_id=?"
    values = rows(
        c,
        """
        SELECT m.id AS product_id,m.sku,m.name,i.warehouse_id,w.code warehouse_code,
               i.on_hand,i.reserved,(i.on_hand-i.reserved) available,
               i.reorder_level,i.updated_at
        FROM menu_items m JOIN inventory i ON i.product_id=m.id
        JOIN warehouses w ON w.id=i.warehouse_id
        WHERE m.active=1 AND w.active=1
        """ + where + " ORDER BY w.id,m.id",
        params,
    )
    for value in values:
        value["low_stock"] = value["available"] <= value["reorder_level"]
        value["reorder_quantity"] = max(value["reorder_level"] - value["available"], 0)
    return values


@app.get("/api/inventory")
def bakuran_inventory(warehouse_id: int | None = Query(default=None, gt=0)):
    with connect() as c:
        if warehouse_id is not None:
            _active_warehouse(c, warehouse_id)
        movement_params = () if warehouse_id is None else (warehouse_id,)
        movement_where = "" if warehouse_id is None else " WHERE warehouse_id=?"
        return {
            "products": _inventory_rows(c, warehouse_id),
            "movements": rows(c, "SELECT * FROM stock_movements" + movement_where + " ORDER BY id DESC", movement_params),
        }


@app.get("/api/inventory/low-stock")
def low_stock(warehouse_id: int | None = Query(default=None, gt=0)):
    with connect() as c:
        if warehouse_id is not None:
            _active_warehouse(c, warehouse_id)
        values = _inventory_rows(c, warehouse_id)
        return [row for row in values if row["low_stock"]]


@app.get("/api/inventory/reorder")
def reorder_inventory(warehouse_id: int | None = Query(default=None, gt=0)):
    return low_stock(warehouse_id)


def _reorder_payload(x):
    return {
        "product_id": x.product_id,
        "warehouse_id": x.warehouse_id,
        "reorder_level": x.reorder_level,
    }


@app.put("/api/inventory/reorder-level")
def update_reorder_level(x: ReorderLevelIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = _reorder_payload(x)
        existing = _idempotent_response(c, "inventory.reorder_level", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        _active_product(c, x.product_id)
        _active_warehouse(c, x.warehouse_id)
        stamp = now_iso()
        _ensure_inventory_row(c, x.product_id, x.warehouse_id, stamp)
        c.execute(
            "UPDATE inventory SET reorder_level=?,updated_at=? WHERE product_id=? AND warehouse_id=?",
            (x.reorder_level, stamp, x.product_id, x.warehouse_id),
        )
        product = next(row for row in _inventory_rows(c, x.warehouse_id) if row["product_id"] == x.product_id)
        _audit(
            c,
            request,
            "inventory.reorder_level_updated",
            f"product={x.product_id};warehouse={x.warehouse_id};reorder_level={x.reorder_level}",
        )
        result = {"product": product}
        _save_idempotent_response(c, "inventory.reorder_level", x.idempotency_key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


@app.post("/api/stock/adjustment")
def stock_adjustment(x: StockAdjustmentIn, request: Request):
    if x.quantity == 0:
        fail("Adjustment quantity must not be zero", 422)
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {
            "product_id": x.product_id,
            "warehouse_id": x.warehouse_id,
            "quantity": x.quantity,
            "reason": x.reason,
        }
        existing = _idempotent_response(c, "stock.adjustment", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        _active_product(c, x.product_id)
        _active_warehouse(c, x.warehouse_id)
        current = _ensure_inventory_row(c, x.product_id, x.warehouse_id)
        if current["on_hand"] + x.quantity < current["reserved"]:
            fail("Adjustment cannot reduce stock below reserved quantity", 409)
        stamp = now_iso()
        c.execute(
            "UPDATE inventory SET on_hand=on_hand+?,updated_at=? WHERE product_id=? AND warehouse_id=?",
            (x.quantity, stamp, x.product_id, x.warehouse_id),
        )
        movement = c.execute(
            "INSERT INTO stock_movements(product_id,warehouse_id,movement_type,quantity,reference,reason,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (x.product_id, x.warehouse_id, "adjustment", x.quantity, "manual-adjustment", x.reason, x.idempotency_key, stamp),
        )
        movement_id = movement.lastrowid
        product = next(row for row in _inventory_rows(c, x.warehouse_id) if row["product_id"] == x.product_id)
        result = {
            "product": product,
            "movement": dict(c.execute("SELECT * FROM stock_movements WHERE id=?", (movement_id,)).fetchone()),
        }
        _audit(c, request, "inventory.adjustment", f"product={x.product_id};warehouse={x.warehouse_id};quantity={x.quantity};reason={x.reason}")
        _save_idempotent_response(c, "stock.adjustment", x.idempotency_key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


@app.get("/api/audit-events")
def audit_events():
    with connect() as c:
        return rows(c, "SELECT * FROM audit_events ORDER BY id DESC")
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
    with connect() as c:
        values = rows(c, "SELECT p.*,s.name supplier_name FROM purchases p JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC")
        for value in values:
            value["lines"] = _purchase_lines(c, value["id"])
        return values


def _purchase_lines(c, purchase_id):
    return rows(
        c,
        """
        SELECT pl.*,m.sku,m.name product_name,w.code warehouse_code
        FROM purchase_lines pl
        JOIN menu_items m ON m.id=pl.product_id
        JOIN warehouses w ON w.id=pl.warehouse_id
        WHERE pl.purchase_id=?
        ORDER BY pl.id
        """,
        (purchase_id,),
    )


def purchase_view(c, purchase_id):
    purchase = c.execute("SELECT p.*,s.name supplier_name FROM purchases p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?", (purchase_id,)).fetchone()
    if not purchase:
        fail("Purchase not found", 404)
    return {"purchase": dict(purchase), "lines": _purchase_lines(c, purchase_id)}


@app.get("/api/purchases/{pid}")
def purchase_detail(pid: int):
    with connect() as c:
        return purchase_view(c, pid)


@app.post("/api/purchases")
def create_purchase(x: PurchaseCreateIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {"supplier_id": x.supplier_id}
        existing = _idempotent_response(c, "purchasing.create", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        if not c.execute("SELECT 1 FROM suppliers WHERE id=? AND active=1", (x.supplier_id,)).fetchone():
            fail("Supplier not found", 404)
        n = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM purchases").fetchone()[0]
        c.execute(
            "INSERT INTO purchases(id,purchase_number,supplier_id,status,total,created_at) VALUES (?,?,?,'draft',0,?)",
            (n, f"PUR-{n:04d}", x.supplier_id, now_iso()),
        )
        _audit(c, request, "purchasing.created", f"purchase={n}")
        result = dict(c.execute("SELECT * FROM purchases WHERE id=?", (n,)).fetchone())
        _save_idempotent_response(c, "purchasing.create", x.idempotency_key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally: c.close()


@app.post("/api/purchases/{pid}/order")
def order_purchase(pid: int, request: Request, x: PurchaseLifecycleIn | None = Body(default=None)):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {"purchase_id": pid, "action": "order"}
        key = x.idempotency_key if x else None
        existing = _idempotent_response(c, f"purchasing.order:{pid}", key, payload)
        if existing is not None:
            c.commit()
            return existing
        purchase = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        if not purchase:
            fail("Purchase not found", 404)
        if purchase["status"] == "ordered":
            result = dict(purchase)
            _save_idempotent_response(c, f"purchasing.order:{pid}", key, payload, result)
            c.commit()
            return result
        if purchase["status"] != "draft":
            fail("Only draft purchases can be ordered", 409)
        if not c.execute("SELECT 1 FROM purchase_lines WHERE purchase_id=?", (pid,)).fetchone():
            fail("Purchase requires lines", 409)
        stamp = now_iso()
        c.execute("UPDATE purchases SET status='ordered',ordered_at=? WHERE id=?", (stamp, pid))
        _audit(c, request, "purchasing.ordered", f"purchase={pid}")
        result = dict(c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone())
        _save_idempotent_response(c, f"purchasing.order:{pid}", key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


@app.post("/api/purchases/{pid}/close")
def close_purchase(pid: int, request: Request, x: PurchaseLifecycleIn | None = Body(default=None)):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {"purchase_id": pid, "action": "close"}
        key = x.idempotency_key if x else None
        existing = _idempotent_response(c, f"purchasing.close:{pid}", key, payload)
        if existing is not None:
            c.commit()
            return existing
        purchase = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        if not purchase:
            fail("Purchase not found", 404)
        if purchase["status"] == "closed":
            result = dict(purchase)
            _save_idempotent_response(c, f"purchasing.close:{pid}", key, payload, result)
            c.commit()
            return result
        if purchase["status"] != "received":
            fail("Only fully received purchases can be closed", 409)
        stamp = now_iso()
        c.execute("UPDATE purchases SET status='closed',closed_at=? WHERE id=?", (stamp, pid))
        _audit(c, request, "purchasing.closed", f"purchase={pid}")
        result = dict(c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone())
        _save_idempotent_response(c, f"purchasing.close:{pid}", key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
    finally:
        c.close()


@app.post("/api/purchases/{pid}/receive")
def receive_purchase(pid: int, request: Request, x: PurchaseReceiptIn | None = Body(default=None)):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        p = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        if not p:
            fail("Purchase not found", 404)
        legacy = x is None
        if legacy:
            if p["status"] not in ("draft", "ordered", "partially_received"):
                fail("Purchase must be ordered or partially received before receiving", 409)
            outstanding = c.execute(
                "SELECT product_id,warehouse_id,quantity-received_quantity AS quantity FROM purchase_lines WHERE purchase_id=? AND received_quantity<quantity ORDER BY id",
                (pid,),
            ).fetchall()
            if not outstanding:
                fail("Purchase has no outstanding lines", 409)
            x = PurchaseReceiptIn(
                lines=[
                    PurchaseReceiptLineIn(product_id=row["product_id"], warehouse_id=row["warehouse_id"], quantity=row["quantity"])
                    for row in outstanding
                ]
            )
            if p["status"] == "draft":
                ordered_at = now_iso()
                c.execute("UPDATE purchases SET status='ordered',ordered_at=? WHERE id=?", (ordered_at, pid))
                _audit(c, request, "purchasing.ordered", f"purchase={pid};legacy_receive=true")
                p = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        payload = {
            "purchase_id": pid,
            "lines": sorted(
                [{"product_id": line.product_id, "warehouse_id": line.warehouse_id, "quantity": line.quantity} for line in x.lines],
                key=lambda line: (line["product_id"], line["warehouse_id"]),
            ),
            "allow_over_receipt": x.allow_over_receipt,
            "override_reason": x.override_reason,
        }
        if x.allow_over_receipt:
            if not x.override_reason:
                fail("Override reason is required", 422)
            _require_override_authority(request)
        existing = _idempotent_response(c, f"purchasing.receive:{pid}", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        if p["status"] not in ("ordered", "partially_received") and not (legacy and p["status"] == "draft"):
            fail("Purchase must be ordered or partially received before receiving", 409)
        requested = {}
        for receipt_line in x.lines:
            _active_product(c, receipt_line.product_id)
            _active_warehouse(c, receipt_line.warehouse_id)
            key = (receipt_line.product_id, receipt_line.warehouse_id)
            requested[key] = requested.get(key, 0) + receipt_line.quantity
        purchase_lines = {}
        for line in c.execute("SELECT * FROM purchase_lines WHERE purchase_id=?", (pid,)).fetchall():
            purchase_lines[(line["product_id"], line["warehouse_id"])] = line
        if not purchase_lines:
            fail("Purchase requires lines", 409)
        if set(requested) - set(purchase_lines):
            fail("Receipt contains a product or warehouse not on this purchase", 409)
        for key, quantity in requested.items():
            line = purchase_lines[key]
            if not x.allow_over_receipt and line["received_quantity"] + quantity > line["quantity"]:
                fail("Receipt exceeds ordered quantity", 409)
        stamp = now_iso()
        for (product_id, warehouse_id), quantity in requested.items():
            line = purchase_lines[(product_id, warehouse_id)]
            _ensure_inventory_row(c, product_id, warehouse_id, stamp)
            c.execute("UPDATE inventory SET on_hand=on_hand+?,updated_at=? WHERE product_id=? AND warehouse_id=?", (quantity, stamp, product_id, warehouse_id))
            c.execute("UPDATE purchase_lines SET received_quantity=received_quantity+? WHERE id=?", (quantity, line["id"]))
            c.execute("INSERT INTO stock_movements(product_id,warehouse_id,movement_type,quantity,reference,reason,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?)", (product_id, warehouse_id, "receipt", quantity, p["purchase_number"], x.override_reason or "Purchase receipt", x.idempotency_key, stamp))
        remaining = c.execute(
            "SELECT 1 FROM purchase_lines WHERE purchase_id=? AND received_quantity<quantity LIMIT 1",
            (pid,),
        ).fetchone()
        status = "partially_received" if remaining else "received"
        received_at = stamp if status == "received" else p["received_at"]
        c.execute("UPDATE purchases SET status=?,received_at=? WHERE id=?", (status, received_at, pid))
        reason = x.override_reason or "Purchase receipt"
        _audit(
            c,
            request,
            "purchasing.receipt",
            f"purchase={pid};quantity={sum(requested.values())};override={x.allow_over_receipt};reason={reason}",
        )
        if x.allow_over_receipt:
            _audit(c, request, "purchasing.receipt_override", f"purchase={pid};reason={reason}")
        result = purchase_view(c, pid)
        if not legacy:
            _save_idempotent_response(c, f"purchasing.receive:{pid}", x.idempotency_key, payload, result)
        c.commit()
        if legacy:
            return dict(c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone())
        return result
    except HTTPException:
        c.rollback()
        raise
    finally: c.close()


@app.post("/api/purchases/{pid}/lines")
def purchase_line(pid: int, x: PurchaseLineIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        payload = {
            "purchase_id": pid,
            "product_id": x.product_id,
            "warehouse_id": x.warehouse_id,
            "quantity": x.quantity,
            "unit_cost": x.unit_cost,
        }
        existing = _idempotent_response(c, f"purchasing.line:{pid}", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        purchase = c.execute("SELECT * FROM purchases WHERE id=?", (pid,)).fetchone()
        if not purchase: fail("Purchase not found", 404)
        if purchase["status"] != "draft": fail("Only draft purchases can be edited", 409)
        _active_product(c, x.product_id)
        _active_warehouse(c, x.warehouse_id)
        line_total = _purchase_line_total(x.quantity, x.unit_cost)
        existing_line_totals = [
            _purchase_line_total(line["quantity"], line["unit_cost"])
            for line in c.execute(
                "SELECT quantity,unit_cost FROM purchase_lines WHERE purchase_id=?",
                (pid,),
            ).fetchall()
        ]
        total = _purchase_total([*existing_line_totals, line_total])
        c.execute(
            "INSERT INTO purchase_lines(purchase_id,product_id,warehouse_id,quantity,unit_cost) VALUES(?,?,?,?,?)",
            (pid, x.product_id, x.warehouse_id, x.quantity, x.unit_cost),
        )
        c.execute("UPDATE purchases SET total=? WHERE id=?", (total, pid))
        _audit(c, request, "purchasing.line_added", f"purchase={pid};product={x.product_id};warehouse={x.warehouse_id}")
        result = purchase_view(c, pid)
        _save_idempotent_response(c, f"purchasing.line:{pid}", x.idempotency_key, payload, result)
        c.commit()
        return result
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
def stock_receipt(x: GenericIn, request: Request):
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        product_id = x.product_id or 1
        warehouse_id = 1
        payload = {
            "name": x.name,
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity": x.quantity,
            "reference": x.value or "manual",
        }
        existing = _idempotent_response(c, "stock.receipt.legacy", x.idempotency_key, payload)
        if existing is not None:
            c.commit()
            return existing
        _active_product(c, product_id)
        _active_warehouse(c, warehouse_id)
        stamp = now_iso()
        _ensure_inventory_row(c, product_id, warehouse_id, stamp)
        c.execute("UPDATE inventory SET on_hand=on_hand+?,updated_at=? WHERE product_id=? AND warehouse_id=?", (x.quantity, stamp, product_id, warehouse_id))
        c.execute(
            "INSERT INTO stock_movements(product_id,warehouse_id,movement_type,quantity,reference,reason,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (product_id, warehouse_id, "receipt", x.quantity, x.value or "manual", "Legacy stock receipt", x.idempotency_key, stamp),
        )
        _audit(c, request, "inventory.receipt_legacy", f"product={product_id};warehouse={warehouse_id};quantity={x.quantity}")
        result = {"product_id": product_id, "quantity": x.quantity}
        _save_idempotent_response(c, "stock.receipt.legacy", x.idempotency_key, payload, result)
        c.commit()
        return result
    except HTTPException:
        c.rollback()
        raise
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
