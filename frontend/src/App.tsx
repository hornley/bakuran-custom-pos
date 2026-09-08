import { useEffect, useMemo, useState, type ReactNode } from "react";
import "./styles.css";
import { csrfHeaders } from "./auth";

type Row = Record<string, any>;
type Step = "build" | "confirm" | "payment" | "fulfillment";
type View = "order" | "payments" | "kitchen" | "ready" | "delivery" | "operations";
type DeliveryAction = "assign" | "out-for-delivery" | "delivered" | "failed" | "cancel";
type OrderMode = "manual" | "qr" | "delivery" | null;

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:5300";
const PROJECT_NAME = "Bakuran POS";
const steps: Array<[Step, string]> = [
  ["build", "Basket"],
  ["confirm", "Customer"],
  ["payment", "Payment"],
  ["fulfillment", "Kitchen & pickup"],
];

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: { ...csrfHeaders(), "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || "The request could not be completed.");
  return body as T;
}

const money = (value: any) => `$${Number(value || 0).toFixed(2)}`;
const label = (value: any) => String(value ?? "").replaceAll("_", " ");

function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

function StatusPill({ value }: { value: string }) {
  const normalized = String(value || "").toLowerCase();
  return <span className={`status-pill ${normalized}`}><span />{label(value)}</span>;
}

function OrderLines({ order, compact = false }: { order: Row; compact?: boolean }) {
  const lines = order.lines || [];
  if (!lines.length) return <Empty>{compact ? "No items" : "Your basket is empty. Add something to begin."}</Empty>;
  return (
    <div className={`order-lines ${compact ? "compact" : ""}`}>
      {lines.map((line: Row) => (
        <div className="order-line" key={line.id || `${line.menu_item_id}-${line.item_name}`}>
          <div>
            <strong>{line.item_name || `Item ${line.menu_item_id}`}</strong>
            <small>{line.quantity} × {money(line.unit_price)}</small>
          </div>
          <strong>{money(line.line_total ?? Number(line.quantity) * Number(line.unit_price))}</strong>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [menu, setMenu] = useState<Row[]>([]);
  const [currentOrder, setCurrentOrder] = useState<Row | null>(null);
  const [completedReceipt, setCompletedReceipt] = useState<Row | null>(null);
  const [orderMode, setOrderMode] = useState<OrderMode>(null);
  const [showEntryChoice, setShowEntryChoice] = useState(true);
  const [step, setStep] = useState<Step>("build");
  const [view, setView] = useState<View>("order");
  const [customerName, setCustomerName] = useState("");
  const [deliveryAddress, setDeliveryAddress] = useState("");
  const [deliveryContact, setDeliveryContact] = useState("");
  const [deliveryContactName, setDeliveryContactName] = useState("");
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [secondaryLoading, setSecondaryLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [secondary, setSecondary] = useState<Record<string, any>>({});
  const [search, setSearch] = useState("");

  const categories = useMemo(
    () => Array.from(new Set(menu.map((item) => String(item.category_name || item.category || "Menu")))),
    [menu],
  );
  const currentLines = currentOrder?.lines || [];
  const orderStatus = String(currentOrder?.status || "open");
  const ticket = currentOrder?.ticket || null;

  function applyOrderPayload(payload: Row) {
    if (!payload?.order) return;
    setCurrentOrder({
      ...payload.order,
      lines: payload.lines || [],
      ticket: payload.ticket || null,
      payment: payload.payment || null,
      receipt: payload.receipt || null,
      tax: payload.tax || null,
      delivery: payload.delivery || null,
    });
    if (payload.order.customer_name) setCustomerName(payload.order.customer_name);
    if (payload.delivery) {
      setDeliveryAddress(payload.delivery.address || "");
      setDeliveryContact(payload.delivery.contact || "");
      setDeliveryContactName(payload.delivery.contact_name || "");
    }
  }

  async function loadMenu() {
    try {
      setLoading(true);
      setError("");
      setMenu(await api<Row[]>("/api/menu"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reach the Bakuran API.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshOrder(orderId: number) {
    const payload = await api<Row>(`/api/orders/${orderId}`);
    applyOrderPayload(payload);
    return payload;
  }

  async function ensureOrder() {
    if (currentOrder) return currentOrder;
    const payload = await api<Row>("/api/counter/orders", { method: "POST", body: JSON.stringify({}) });
    applyOrderPayload(payload);
    setOrderMode("manual");
    return { ...payload.order, lines: payload.lines || [] };
  }

  async function startOrder() {
    try {
      setBusy("start");
      setError("");
      setNotice("");
      await ensureOrder();
      setCompletedReceipt(null);
      setShowEntryChoice(false);
      setStep("build");
      setView("order");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start a new order.");
    } finally {
      setBusy("");
    }
  }

  async function startDeliveryOrder() {
    try {
      setBusy("delivery-start");
      setError("");
      setNotice("");
      setCustomerName("");
      setDeliveryAddress("");
      setDeliveryContact("");
      setDeliveryContactName("");
      setQuantities({});
      const payload = await api<Row>("/api/counter/orders", { method: "POST", body: JSON.stringify({ order_channel: "delivery" }) });
      applyOrderPayload(payload);
      setOrderMode("delivery");
      setCompletedReceipt(null);
      setShowEntryChoice(false);
      setStep("build");
      setView("order");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start a delivery order.");
    } finally {
      setBusy("");
    }
  }

  async function addItem(item: Row) {
    const key = `add-${item.id}`;
    try {
      setBusy(key);
      setError("");
      const order = await ensureOrder();
      const payload = await api<Row>(`/api/orders/${order.id}/lines`, {
        method: "POST",
        body: JSON.stringify({ menu_item_id: item.id, quantity: quantities[item.id] || 1 }),
      });
      applyOrderPayload(payload);
      setNotice(`${item.name} added.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add the item.");
    } finally {
      setBusy("");
    }
  }

  async function confirmOrder() {
    if (!currentOrder) return;
    try {
      setBusy("confirm");
      setError("");
      if (orderMode === "delivery") {
        const metadata = await api<Row>(`/api/orders/${currentOrder.id}/delivery`, {
          method: "POST",
          body: JSON.stringify({ address: deliveryAddress.trim(), contact: deliveryContact.trim(), contact_name: deliveryContactName.trim() }),
        });
        applyOrderPayload(metadata);
      }
      const payload = await api<Row>(`/api/orders/${currentOrder.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ customer_name: customerName.trim() }),
      });
      applyOrderPayload(payload);
      setStep("payment");
      setNotice("Ready to collect cash.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not confirm the order.");
    } finally {
      setBusy("");
    }
  }

  async function payOrder(order = currentOrder) {
    if (!order) return;
    const key = `pay-${order.id}`;
    try {
      setBusy(key);
      setError("");
      const payload = await api<Row>(`/api/orders/${order.id}/pay`, {
        method: "POST",
        body: JSON.stringify({ amount: String(order.total), method: "cash" }),
      });
      applyOrderPayload(payload);
      setStep("fulfillment");
      if (orderMode === "delivery") {
        setView("delivery");
        void loadSecondary("delivery");
      } else {
        setView("order");
      }
      setNotice("Payment recorded. The order is in the kitchen.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not record payment.");
    } finally {
      setBusy("");
    }
  }

  async function advanceKitchen(action: string) {
    if (!ticket) return;
    const key = `ticket-${action}`;
    try {
      setBusy(key);
      setError("");
      await api(`/api/kitchen/${ticket.id}/${action}`, { method: "POST", body: JSON.stringify({}) });
      await refreshOrder(currentOrder!.id);
      setNotice(action === "serve" ? "Order is ready for pickup." : `Kitchen ticket marked ${action}.`);
      await loadSecondary("kitchen");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the kitchen ticket.");
    } finally {
      setBusy("");
    }
  }

  async function closeOrder() {
    if (!currentOrder) return;
    try {
      setBusy("close");
      setError("");
      const payload = await api<Row>(`/api/orders/${currentOrder.id}/close`, { method: "POST", body: JSON.stringify({}) });
      applyOrderPayload(payload);
      setCompletedReceipt(payload.receipt || null);
      setNotice("Order closed. Receipt issued.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not close the order.");
    } finally {
      setBusy("");
    }
  }

  function resetOrder() {
    setCurrentOrder(null);
    setCompletedReceipt(null);
    setOrderMode(null);
    setShowEntryChoice(true);
    setCustomerName("");
    setDeliveryAddress("");
    setDeliveryContact("");
    setDeliveryContactName("");
    setQuantities({});
    setStep("build");
    setView("order");
    setError("");
    setNotice("");
  }

  function backToOrderType() {
    setShowEntryChoice(true);
    setView("order");
    setStep("build");
    setError("");
    setNotice("");
  }

  async function loadSecondary(target: View) {
    if (target === "order") return;
    try {
      setSecondaryLoading(true);
      const path = target === "payments"
        ? `/api/payment-queue${search ? `?q=${encodeURIComponent(search)}` : ""}`
        : target === "operations"
          ? "/api/tables"
          : target === "delivery"
            ? "/api/delivery"
          : target === "ready"
            ? "/api/kitchen?queue=ready"
            : "/api/kitchen";
      const values = await api<Row[]>(path);
      setSecondary((current) => ({ ...current, [target]: values }));
      if (target === "delivery") {
        const drivers = await api<Row[]>("/api/delivery/drivers");
        setSecondary((current) => ({ ...current, deliveryDrivers: drivers }));
      }
      if (target === "operations") {
        const receipts = await api<Row[]>("/api/receipts");
        const taxConfiguration = await api<Row>("/api/tax/configuration");
        setSecondary((current) => ({ ...current, receipts, taxConfiguration }));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load this operational view.");
    } finally {
      setSecondaryLoading(false);
    }
  }

  function navigate(target: View) {
    setView(target);
    setError("");
    if (target !== "order") void loadSecondary(target);
  }

  async function saveTaxRule(payload: Row): Promise<boolean> {
    try {
      setBusy("tax-config");
      setError("");
      await api<Row>("/api/tax/configuration", { method: "POST", body: JSON.stringify(payload) });
      const taxConfiguration = await api<Row>("/api/tax/configuration");
      setSecondary((current) => ({ ...current, taxConfiguration }));
      setNotice("Tax rule saved.");
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the tax rule.");
      return false;
    }
  }

  async function mutateDelivery(
    deliveryId: number,
    action: DeliveryAction,
    body: Row = {},
  ) {
    const busyKey = `delivery-${deliveryId}-${action}`;
    const idempotencyKey = `desk-${action}-${deliveryId}-${body.driver_id || ""}`;
    const reason = body.reason || "";
    try {
      setBusy(busyKey);
      setError("");
      const path = action === "assign"
        ? `/api/delivery/${deliveryId}/assign`
        : `/api/delivery/${deliveryId}/${action}`;
      await api<Row>(path, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(action === "failed" || action === "cancel" ? { reason } : body),
      });
      await loadSecondary("delivery");
      setNotice(`Delivery ${label(action)}.`);
    } catch (reasonValue) {
      setError(reasonValue instanceof Error ? reasonValue.message : "Could not update the delivery.");
    } finally {
      setBusy("");
    }
  }

  async function openSecondaryOrder(order: Row) {
    try {
      setError("");
      const payload = await refreshOrder(order.id || order.order_id);
      const isPaymentQueue = view === "payments";
      setOrderMode(isPaymentQueue ? "qr" : payload.order.order_channel === "qr" ? "qr" : payload.order.order_channel === "delivery" ? "delivery" : "manual");
      setStep(isPaymentQueue ? "payment" : "fulfillment");
      setView("order");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not open this order.");
    }
  }

  useEffect(() => { void loadMenu(); }, []);

  const hasItems = currentLines.length > 0;
  const currentStepIndex = steps.findIndex(([key]) => key === step);
  const kitchenRows = secondary.kitchen || [];
  const readyRows = (secondary.ready || []).filter((row: Row) => ["ready", "served"].includes(row.status));
  const paymentRows = (secondary.payments || []).filter((row: Row) => row.order_channel === "qr");
  const deliveryRows = secondary.delivery || [];
  const deliveryDrivers = secondary.deliveryDrivers || [];
  const tableRows = (secondary.operations || []).filter((row: Row) => row.code !== "COUNTER");
  const receipts = secondary.receipts || [];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">BK</span><span>{PROJECT_NAME}</span></div>
        <div className="topbar-right"><span className="topbar-note"><i className="live-dot" />{loading ? "Connecting" : "API ready"}</span></div>
      </header>

      <main className="main">
        <section className="hero compact-hero">
          <div>
            <span className="eyebrow">Front desk</span>
            <h1>Counter</h1>
            <p>Start a new order or open a QR order awaiting payment.</p>
          </div>
          {currentOrder && (orderMode === "qr" || step === "fulfillment" || currentOrder.status === "closed") && (
            <div className="hero-side">
              <span className="hero-order">{currentOrder.order_number}<small>{label(orderStatus)}</small></span>
            </div>
          )}
        </section>

        <nav className="tabs" aria-label="Bakuran operations">
          {([["order", "New order"], ["payments", "QR orders"], ["kitchen", "Kitchen"], ["ready", "Ready"], ["delivery", "Delivery"], ["operations", "Operations"]] as Array<[View, string]>).map(([key, text]) => (
            <button className={view === key ? "active" : ""} key={key} onClick={() => navigate(key)}>{text}</button>
          ))}
        </nav>

        {error && <div className="banner error"><strong>Needs attention</strong><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
        {notice && <div className="banner notice"><strong>Saved</strong><span>{notice}</span><button onClick={() => setNotice("")}>Dismiss</button></div>}

        {view === "order" ? (
          <>
            {showEntryChoice ? (
              <EntryChoice onManual={() => void startOrder()} onQr={() => navigate("payments")} busy={busy === "start"} />
            ) : (
              <>
                <div className="flow-toolbar"><button className="text-button" onClick={backToOrderType}>Back to order type</button></div>
                <section className="stepper" aria-label="Order progress">
                  {steps.map(([key, text], index) => (
                    <div className={`step ${index === currentStepIndex ? "active" : ""} ${index < currentStepIndex ? "complete" : ""}`} key={key}>
                      <span>{String(index + 1).padStart(2, "0")}</span><strong>{text}</strong>
                    </div>
                  ))}
                </section>

                {completedReceipt ? (
                  <section className="success-card">
                    <div className="success-mark">✓</div>
                    <span className="eyebrow">Complete</span>
                    <h2>Ready for the next customer.</h2>
                    <p>{currentOrder?.customer_name || "Customer"} · {currentOrder?.order_number}</p>
                    <TaxBreakdown order={{ ...(currentOrder || {}), ...(completedReceipt || {}) }} />
                    <div className="receipt-line"><span>Receipt {completedReceipt.receipt_number}</span><strong>{money(completedReceipt.total)}</strong></div>
                    <button className="action-button primary" onClick={resetOrder}>Start another order</button>
                  </section>
                ) : (
                  <>
                    {step === "build" && (
                      <section className="flow-grid">
                        <section className="panel menu-panel">
                          <div className="panel-heading"><div><span className="eyebrow">01 / Basket</span><h2>Choose items</h2></div><span className="panel-mark">{menu.length} items</span></div>
                          <p className="panel-intro">Build the basket for this customer.</p>
                          {loading ? <div className="state">Loading menu…</div> : (
                            <div className="category-list">
                              {categories.map((category) => (
                                <div className="category-block" key={category}>
                                  <span className="category-label">{category}</span>
                                  <div className="menu-list">
                                    {menu.filter((item) => (item.category_name || item.category || "Menu") === category).map((item) => {
                                      const key = `add-${item.id}`;
                                      return (
                                        <div
                                          className="menu-row"
                                          key={item.id}
                                          role="button"
                                          tabIndex={busy ? -1 : 0}
                                          aria-label={`Add ${item.name} to order`}
                                          aria-disabled={!!busy}
                                          onClick={() => { if (!busy) void addItem(item); }}
                                          onKeyDown={(event) => {
                                            if ((event.key === "Enter" || event.key === " ") && event.target === event.currentTarget) {
                                              event.preventDefault();
                                              if (!busy) void addItem(item);
                                            }
                                          }}
                                        >
                                          <div><strong>{item.name}</strong><small>{item.description || "Menu item"}</small></div>
                                          <div className="menu-card-meta"><span className="menu-price">{money(item.price)}</span><span className="menu-action-label">{busy === key ? "Adding…" : "Tap to add"}</span></div>
                                          <div className="menu-controls" onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()}>
                                            <label className="sr-only" htmlFor={`quantity-${item.id}`}>Quantity for {item.name}</label>
                                            <input id={`quantity-${item.id}`} aria-label={`Quantity for ${item.name}`} type="number" min="1" value={quantities[item.id] || 1} onChange={(event) => setQuantities({ ...quantities, [item.id]: Math.max(1, Number(event.target.value) || 1) })} />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                          {!categories.length && <Empty>No published menu items are available.</Empty>}
                        </section>

                        <section className="panel basket-panel">
                          <div className="panel-heading"><div><span className="eyebrow">Your basket</span><h2>Current order</h2></div><span className="panel-mark">{currentLines.length} lines</span></div>
                          {hasItems ? (
                            <>
                              <OrderLines order={currentOrder || {}} />
                              <TaxBreakdown order={currentOrder || {}} />
                            </>
                          ) : (
                            <div className="basket-start"><div className="basket-icon">+</div><strong>Add items to begin.</strong><p>The basket will appear here.</p></div>
                          )}
                          <div className="button-row basket-actions">
                            <button className="action-button primary" disabled={!hasItems || !!busy} onClick={() => setStep("confirm")}>Review order</button>
                          </div>
                        </section>
                      </section>
                    )}

                    {step === "confirm" && (
                      <section className="flow-grid confirm-grid">
                        <section className="panel">
                          <div className="panel-heading"><div><span className="eyebrow">02 / {orderMode === "delivery" ? "Delivery details" : "Customer"}</span><h2>{orderMode === "delivery" ? "Where should it go?" : "Name for pickup"}</h2></div></div>
                          <p className="panel-intro">{orderMode === "delivery" ? "Save the delivery address and contact details before collecting cash." : "Use the name to call the customer when the order is ready."}</p>
                          <label className="field-label" htmlFor="customer-name">{orderMode === "delivery" ? "Customer / contact name" : "Customer name"}</label>
                          <input id="customer-name" className="text-input" autoFocus value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="e.g. Mika" />
                          {orderMode === "delivery" && (
                            <div className="delivery-form">
                              <label className="field-label" htmlFor="delivery-address">Delivery address</label>
                              <input id="delivery-address" className="text-input" value={deliveryAddress} onChange={(event) => setDeliveryAddress(event.target.value)} placeholder="Street, area, city" />
                              <label className="field-label" htmlFor="delivery-contact">Contact number</label>
                              <input id="delivery-contact" className="text-input" type="tel" value={deliveryContact} onChange={(event) => setDeliveryContact(event.target.value)} placeholder="09xx xxx xxxx" />
                              <label className="field-label" htmlFor="delivery-contact-name">Contact name (optional)</label>
                              <input id="delivery-contact-name" className="text-input" value={deliveryContactName} onChange={(event) => setDeliveryContactName(event.target.value)} placeholder="Recipient name" />
                            </div>
                          )}
                          <div className="button-row">
                            <button className="text-button" onClick={() => setStep("build")}>Back to basket</button>
                            <button className="action-button primary" disabled={!customerName.trim() || !hasItems || !!busy || (orderMode === "delivery" && (!deliveryAddress.trim() || !deliveryContact.trim()))} onClick={() => void confirmOrder()}>{busy === "confirm" ? "Saving…" : "Continue to payment"}</button>
                          </div>
                        </section>
                        <section className="panel summary-panel">
                          <span className="eyebrow">Order summary</span>
                          <h2>Current order</h2>
                          <OrderLines order={currentOrder || {}} />
                          <TaxBreakdown order={currentOrder || {}} />
                        </section>
                      </section>
                    )}

                    {step === "payment" && (
                      <section className="handoff-card">
                        <div className="handoff-copy">
                          <span className="eyebrow">03 / {orderMode === "qr" ? "QR payment" : orderMode === "delivery" ? "Delivery payment" : "Payment"}</span>
                          <h2>{orderMode === "qr" ? "Review and collect cash." : orderMode === "delivery" ? "Collect cash for delivery." : "Collect cash."}</h2>
                          <p>{orderMode === "qr" ? "This order was submitted by the customer. The basket is read-only." : orderMode === "delivery" ? "The order is paid before dispatch. The delivery board opens after payment." : "The order number appears after payment."}</p>
                          {orderMode === "qr" && <div className="order-number">{currentOrder?.order_number}</div>}
                          <div className="handoff-meta">
                            <span>{currentOrder?.customer_name || "Customer"}</span>
                            {orderMode === "qr" && currentOrder?.table_code && <span>{currentOrder.table_code}</span>}
                            {orderMode === "delivery" && <span>{deliveryAddress}</span>}
                            <span>{money(currentOrder?.total)} due</span>
                            <StatusPill value={orderMode === "qr" ? "qr order" : "payment required"} />
                          </div>
                        </div>
                        <div className="handoff-action">
                          <div className="mini-summary"><OrderLines order={currentOrder || {}} compact /><TaxBreakdown order={currentOrder || {}} /></div>
                          <button className="action-button primary full" disabled={!!busy} onClick={() => void payOrder()}>{busy === `pay-${currentOrder?.id}` ? "Recording…" : "Record cash payment"}</button>
                          {orderMode === "qr" ? <button className="text-button" onClick={() => { setCurrentOrder(null); setOrderMode(null); setStep("build"); setView("payments"); }}>Back to QR orders</button> : <button className="text-button" onClick={() => setStep("confirm")}>Back to customer</button>}
                        </div>
                      </section>
                    )}

                    {step === "fulfillment" && (
                      <section className="fulfillment-card">
                        <div className="fulfillment-head">
                          <div><span className="eyebrow">04 / Kitchen & pickup</span><h2>{ticket?.status === "served" ? "Ready for pickup." : "Order is moving."}</h2><p>Call <strong>{currentOrder?.customer_name || "the customer"}</strong> or display the order number.</p></div>
                          <div className="order-number small">{currentOrder?.order_number}</div>
                        </div>
                        <div className="fulfillment-status">
                          <div><span>Payment</span><StatusPill value={currentOrder?.payment ? "paid" : orderStatus} /></div>
                          <div><span>Kitchen</span><StatusPill value={ticket?.status || "queued"} /></div>
                          <div><span>Pickup</span><strong>{ticket?.status === "served" ? "Customer called" : "Counter"}</strong></div>
                        </div>
                        <OrderLines order={currentOrder || {}} compact />
                        <div className="button-row fulfillment-actions">
                          <button className="text-button" onClick={() => navigate("kitchen")}>Back to kitchen</button>
                          {ticket?.status === "queued" && <button className="action-button primary" disabled={!!busy} onClick={() => void advanceKitchen("start")}>{busy === "ticket-start" ? "Starting…" : "Start preparation"}</button>}
                          {ticket?.status === "preparing" && <button className="action-button primary" disabled={!!busy} onClick={() => void advanceKitchen("ready")}>{busy === "ticket-ready" ? "Saving…" : "Mark ready"}</button>}
                          {ticket?.status === "ready" && <button className="action-button primary" disabled={!!busy} onClick={() => void advanceKitchen("serve")}>{busy === "ticket-serve" ? "Saving…" : "Call customer"}</button>}
                          {ticket?.status === "served" && <button className="action-button primary" disabled={!!busy} onClick={() => void closeOrder()}>{busy === "close" ? "Closing…" : "Complete pickup"}</button>}
                        </div>
                      </section>
                    )}
                  </>
                )}
              </>
            )}
          </>
        ) : (
          <SecondaryView
            view={view}
            loading={secondaryLoading}
            paymentRows={paymentRows}
            kitchenRows={view === "ready" ? readyRows : kitchenRows}
            deliveryRows={deliveryRows}
            deliveryDrivers={deliveryDrivers}
            deliveryBusy={busy.startsWith("delivery-")}
            tableRows={tableRows}
            receipts={receipts}
            taxConfiguration={secondary.taxConfiguration || null}
            taxSaving={busy === "tax-config"}
            onSaveTaxRule={saveTaxRule}
            search={search}
            setSearch={setSearch}
            onSearch={() => void loadSecondary("payments")}
            onRefresh={() => void loadSecondary(view)}
            onSelect={(order) => void openSecondaryOrder(order)}
            onDeliveryAction={(deliveryId, action, body) => void mutateDelivery(deliveryId, action, body)}
            onStartDelivery={() => void startDeliveryOrder()}
          />
        )}
      </main>
    </div>
  );
}

function EntryChoice({ onManual, onQr, busy }: { onManual: () => void; onQr: () => void; busy: boolean }) {
  return (
    <section className="entry-choice" aria-label="Start at counter">
      <div className="entry-grid">
        <button className="entry-card" onClick={onManual} disabled={busy}>
          <span className="entry-icon">+</span>
          <span className="eyebrow">Manual</span>
          <h3>New order</h3>
          <p>Build the basket, add a name, and collect cash.</p>
          <strong>{busy ? "Starting…" : "Start order"}</strong>
        </button>
        <button className="entry-card qr" onClick={onQr} disabled={busy}>
          <span className="entry-icon">QR</span>
          <span className="eyebrow">Connected</span>
          <h3>QR orders</h3>
          <p>Choose a submitted order and record cash.</p>
          <strong>Open orders</strong>
        </button>
      </div>
    </section>
  );
}

function TaxBreakdown({ order }: { order: Row }) {
  const tax = order.tax || {};
  const policy = String(tax.policy ?? order.tax_policy ?? "none");
  const taxableSubtotal = tax.taxable_subtotal ?? order.taxable_subtotal ?? order.subtotal ?? 0;
  const taxAmount = tax.tax_amount ?? order.tax_amount ?? 0;
  const total = tax.total ?? order.total ?? 0;
  const rate = tax.rate ?? order.tax_rate;
  const name = tax.name || order.tax_name || "Tax";
  return (
    <div className="tax-breakdown" aria-label="Tax breakdown">
      <div className="tax-breakdown-row"><span>{policy === "inclusive" ? "Taxable subtotal" : "Subtotal"}</span><strong>{money(taxableSubtotal)}</strong></div>
      <div className="tax-breakdown-row"><span>{policy === "none" ? "Tax" : `${name} (${rate}%)`}</span><strong>{money(taxAmount)}</strong></div>
      <div className="tax-breakdown-row tax-breakdown-total"><span>Total</span><strong>{money(total)}</strong></div>
    </div>
  );
}

export function DeliveryBoard({ deliveries, drivers, busy, onAction, onStartDelivery }: { deliveries: Row[]; drivers: Row[]; busy: boolean; onAction: (deliveryId: number, action: DeliveryAction, body?: Row) => void; onStartDelivery?: () => void }) {
  const [driverSelection, setDriverSelection] = useState<Record<string, string>>({});

  function selectedDriver(delivery: Row) {
    return driverSelection[delivery.id] || String(delivery.driver_id || drivers[0]?.id || "");
  }

  function askForReason(deliveryId: number, action: "failed" | "cancel") {
    const reason = window.prompt(action === "failed" ? "Why did this delivery fail?" : "Why was this delivery cancelled?");
    if (reason?.trim()) onAction(deliveryId, action, { reason: reason.trim() });
  }

  return (
    <>
      <div className="delivery-board-toolbar"><div><span className="eyebrow">Local dispatch</span><p>Paid delivery orders only. No external courier connection.</p></div><button className="action-button primary" onClick={onStartDelivery} disabled={busy}>New delivery</button></div>
      {deliveries.length ? <div className="delivery-board">
        {deliveries.map((delivery) => {
        const status = String(delivery.status);
        const selected = selectedDriver(delivery);
        const terminal = ["delivered", "failed", "cancelled"].includes(status);
        return (
          <article className="delivery-card" key={delivery.id}>
            <div className="delivery-card-head">
              <div><span className="eyebrow">{delivery.order_number}</span><h3>{delivery.contact_name || delivery.customer_name || "Unnamed customer"}</h3><p>{money(delivery.order_total)} · {delivery.contact}</p></div>
              <StatusPill value={status} />
            </div>
            <div className="delivery-meta">
              <div><span>Address</span><strong>{delivery.address}</strong></div>
              <div><span>Contact</span><strong>{delivery.contact_name || delivery.customer_name || "No contact name"}</strong><small>{delivery.contact}</small></div>
              <div><span>Driver</span><strong>{delivery.driver?.name || "Unassigned"}</strong></div>
            </div>
            <div className="delivery-history">
              <span>Assignment history</span>
              {delivery.assignments?.length ? delivery.assignments.map((assignment: Row) => <small key={assignment.id}>{assignment.driver_name} · {assignment.status}</small>) : <small>No driver assigned yet.</small>}
            </div>
            {!terminal && (
              <div className="delivery-actions">
                {(status === "pending" || status === "assigned") && (
                  <>
                    <select aria-label={`Driver for ${delivery.order_number}`} value={selected} onChange={(event) => setDriverSelection({ ...driverSelection, [delivery.id]: event.target.value })} disabled={busy}>
                      <option value="">Choose driver</option>
                      {drivers.map((driver) => <option value={driver.id} key={driver.id}>{driver.name}</option>)}
                    </select>
                    <button className="action-button" disabled={busy || !selected} onClick={() => onAction(delivery.id, "assign", { driver_id: Number(selected) })}>{status === "assigned" ? "Reassign" : "Assign driver"}</button>
                  </>
                )}
                {status === "assigned" && <button className="action-button primary" disabled={busy} onClick={() => onAction(delivery.id, "out-for-delivery")}>Out for delivery</button>}
                {status === "out_for_delivery" && <button className="action-button primary" disabled={busy} onClick={() => onAction(delivery.id, "delivered")}>Mark delivered</button>}
                <button className="text-button" disabled={busy} onClick={() => askForReason(delivery.id, "failed")}>Fail</button>
                <button className="text-button" disabled={busy} onClick={() => askForReason(delivery.id, "cancel")}>Cancel</button>
              </div>
            )}
          </article>
        );
        })}
      </div> : <Empty>No delivery orders are ready for dispatch.</Empty>}
    </>
  );
}

function SecondaryView({ view, loading, paymentRows, kitchenRows, deliveryRows, deliveryDrivers, deliveryBusy, tableRows, receipts, taxConfiguration, taxSaving, onSaveTaxRule, search, setSearch, onSearch, onRefresh, onSelect, onDeliveryAction, onStartDelivery }: { view: View; loading: boolean; paymentRows: Row[]; kitchenRows: Row[]; deliveryRows: Row[]; deliveryDrivers: Row[]; deliveryBusy: boolean; tableRows: Row[]; receipts: Row[]; taxConfiguration: Row | null; taxSaving: boolean; onSaveTaxRule: (payload: Row) => Promise<boolean>; search: string; setSearch: (value: string) => void; onSearch: () => void; onRefresh: () => void; onSelect: (order: Row) => void; onDeliveryAction: (deliveryId: number, action: DeliveryAction, body?: Row) => void; onStartDelivery: () => void }) {
  const titles: Record<View, [string, string]> = {
    order: ["", ""],
    payments: ["02 / Payment", "QR orders"],
    kitchen: ["03 / Kitchen", "Kitchen"],
    ready: ["04 / Pickup", "Ready"],
    delivery: ["05 / Dispatch", "Delivery"],
    operations: ["06 / Reference", "Operations"],
  };
  const [eyebrow, heading] = titles[view];
  const description = view === "payments"
    ? "Select a submitted QR order and record cash."
    : view === "kitchen"
      ? "Paid orders appear here automatically."
      : view === "ready"
        ? "Call customers by name or order number."
        : view === "delivery"
          ? "Assign active drivers and track paid deliveries."
          : "Tables and receipts stay available when needed.";

  return (
    <section className="secondary-page">
      <div className="secondary-heading">
        <div><span className="eyebrow">{eyebrow}</span><h2>{heading}</h2><p>{description}</p></div>
        <button className="refresh" onClick={onRefresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      {view === "payments" && (
        <div className="search-row">
          <input className="text-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Order number, name, or table" />
          <button className="action-button" onClick={onSearch}>Search</button>
        </div>
      )}

      {loading ? <div className="panel state">Loading…</div> : view === "payments" ? (
        <div className="queue-list">
          {paymentRows.length ? paymentRows.map((order) => (
            <article className="queue-card" key={order.id}>
              <div><span className="eyebrow">{order.order_number}</span><h3>{order.customer_name || "Unnamed customer"}</h3><p>{order.table_code || "QR order"} · {order.lines?.length || 0} items</p></div>
              <div className="queue-side"><strong>{money(order.total)}</strong><StatusPill value="awaiting payment" /><button className="action-button" onClick={() => onSelect(order)}>Review & pay</button></div>
            </article>
          )) : <Empty>No QR orders are waiting for payment.</Empty>}
        </div>
      ) : view === "kitchen" || view === "ready" ? (
        <div className="queue-list">
          {kitchenRows.length ? kitchenRows.map((ticket) => (
            <article className="queue-card" key={ticket.id}>
              <div><span className="eyebrow">{ticket.order_number}</span><h3>{ticket.customer_name || "Customer"}</h3><p>{ticket.table_code === "COUNTER" ? "Counter" : ticket.table_code} · {ticket.ticket_number}</p></div>
              <div className="queue-side"><StatusPill value={ticket.status} /><button className="action-button" onClick={() => onSelect({ id: ticket.order_id, status: ticket.status, order_number: ticket.order_number, customer_name: ticket.customer_name, ticket })}>Open order</button></div>
            </article>
          )) : <Empty>No orders in this queue.</Empty>}
        </div>
      ) : view === "delivery" ? (
        <DeliveryBoard deliveries={deliveryRows} drivers={deliveryDrivers} busy={loading || deliveryBusy} onAction={onDeliveryAction} onStartDelivery={onStartDelivery} />
      ) : (
        <>
          <div className="operations-grid">
            <section className="panel"><span className="eyebrow">Floor reference</span><h3>Tables</h3>{tableRows.length ? <div className="simple-list">{tableRows.map((table) => <div className="simple-row" key={table.id}><div><strong>{table.code}</strong><small>{table.name} · {table.seats} seats</small></div><StatusPill value={table.status} /></div>)}</div> : <Empty>No tables found.</Empty>}</section>
            <section className="panel"><span className="eyebrow">Sales history</span><h3>Receipts</h3>{receipts.length ? <div className="simple-list">{receipts.slice(0, 8).map((receipt) => <div className="simple-row" key={receipt.id}><div><strong>{receipt.receipt_number}</strong><small>{receipt.order_number} · {receipt.table_code}</small></div><strong>{money(receipt.total)}</strong></div>)}</div> : <Empty>No receipts yet.</Empty>}</section>
          </div>
          <TaxConfiguration configuration={taxConfiguration} saving={taxSaving} onSave={onSaveTaxRule} />
        </>
      )}
    </section>
  );
}

function TaxConfiguration({ configuration, saving, onSave }: { configuration: Row | null; saving: boolean; onSave: (payload: Row) => Promise<boolean> }) {
  const [draft, setDraft] = useState({
    name: "VAT",
    rate: "10",
    policy: "exclusive",
    effective_from: new Date().toISOString().slice(0, 10),
    effective_to: "",
  });

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const saved = await onSave({ ...draft, effective_to: draft.effective_to || null });
    if (saved) setDraft((current) => ({ ...current, effective_to: "" }));
  }

  const active = configuration?.effective_rule;
  const rules = configuration?.rules || [];
  return (
    <section className="panel tax-config-panel" aria-label="Tax configuration">
      <div className="panel-heading"><div><span className="eyebrow">Configuration</span><h3>Tax rules</h3></div><span className="panel-mark">Manager / admin</span></div>
      <p className="panel-intro">Rules are selected by effective date and copied into orders at confirmation. Existing receipts do not change.</p>
      <div className="tax-active-rule"><span className="eyebrow">Effective today</span><strong>{active ? `${active.name} · ${active.rate}% ${active.policy}` : "No active tax rule"}</strong></div>
      <form className="tax-rule-form" onSubmit={submit}>
        <label>Rule name<input id="tax-name" className="text-input" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required /></label>
        <label>Rate (%)<input id="tax-rate" className="text-input" inputMode="decimal" value={draft.rate} onChange={(event) => setDraft({ ...draft, rate: event.target.value })} required /></label>
        <label>Policy<select id="tax-policy" className="text-input" value={draft.policy} onChange={(event) => setDraft({ ...draft, policy: event.target.value })}><option value="exclusive">Exclusive</option><option value="inclusive">Inclusive</option></select></label>
        <label>Effective from<input id="tax-effective-from" className="text-input" type="date" value={draft.effective_from} onChange={(event) => setDraft({ ...draft, effective_from: event.target.value })} required /></label>
        <label>Effective to <span className="muted-label">optional</span><input id="tax-effective-to" className="text-input" type="date" value={draft.effective_to} onChange={(event) => setDraft({ ...draft, effective_to: event.target.value })} /></label>
        <button className="action-button primary tax-save" disabled={saving}>{saving ? "Saving…" : "Save tax rule"}</button>
      </form>
      {rules.length > 0 && <div className="tax-rule-list"><span className="eyebrow">Configured rules</span>{rules.map((rule: Row) => <div className="simple-row" key={rule.id}><div><strong>{rule.name} · {rule.rate}% {rule.policy}</strong><small>{rule.effective_from} → {rule.effective_to || "open-ended"}</small></div><span className="status-pill">{rule.id === active?.id ? "Active" : "Scheduled"}</span></div>)}</div>}
    </section>
  );
}
