import { useEffect, useMemo, useState, type ReactNode } from "react";
import "./styles.css";
import { csrfHeaders } from "./auth";

type Row = Record<string, any>;
type Step = "build" | "confirm" | "payment" | "fulfillment";
type View = "order" | "payments" | "kitchen" | "ready" | "operations";

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
    credentials: "include",
    headers: { ...csrfHeaders(), "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
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
  const [orderMode, setOrderMode] = useState<"manual" | "qr" | null>(null);
  const [showEntryChoice, setShowEntryChoice] = useState(true);
  const [step, setStep] = useState<Step>("build");
  const [view, setView] = useState<View>("order");
  const [customerName, setCustomerName] = useState("");
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [secondaryLoading, setSecondaryLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [secondary, setSecondary] = useState<Record<string, Row[]>>({});
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
    });
    if (payload.order.customer_name) setCustomerName(payload.order.customer_name);
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
        body: JSON.stringify({ amount: Number(order.total), method: "cash" }),
      });
      applyOrderPayload(payload);
      setStep("fulfillment");
      setView("order");
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
          : "/api/kitchen";
      const values = await api<Row[]>(path);
      setSecondary((current) => ({ ...current, [target]: values }));
      if (target === "operations") {
        const receipts = await api<Row[]>("/api/receipts");
        setSecondary((current) => ({ ...current, receipts }));
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

  async function openSecondaryOrder(order: Row) {
    try {
      setError("");
      const payload = await refreshOrder(order.id || order.order_id);
      const isPaymentQueue = view === "payments";
      setOrderMode(isPaymentQueue ? "qr" : payload.order.order_channel === "qr" ? "qr" : "manual");
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
  const readyRows = (secondary.ready || []).filter((row) => ["ready", "served"].includes(row.status));
  const paymentRows = (secondary.payments || []).filter((row) => row.order_channel === "qr");
  const tableRows = (secondary.operations || []).filter((row) => row.code !== "COUNTER");
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
          {([["order", "New order"], ["payments", "QR orders"], ["kitchen", "Kitchen"], ["ready", "Ready"], ["operations", "Operations"]] as Array<[View, string]>).map(([key, text]) => (
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
                              <div className="order-total"><span>Total</span><strong>{money(currentOrder?.total)}</strong></div>
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
                          <div className="panel-heading"><div><span className="eyebrow">02 / Customer</span><h2>Name for pickup</h2></div></div>
                          <p className="panel-intro">Use the name to call the customer when the order is ready.</p>
                          <label className="field-label" htmlFor="customer-name">Customer name</label>
                          <input id="customer-name" className="text-input" autoFocus value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="e.g. Mika" />
                          <div className="button-row">
                            <button className="text-button" onClick={() => setStep("build")}>Back to basket</button>
                            <button className="action-button primary" disabled={!customerName.trim() || !hasItems || !!busy} onClick={() => void confirmOrder()}>{busy === "confirm" ? "Saving…" : "Continue to payment"}</button>
                          </div>
                        </section>
                        <section className="panel summary-panel">
                          <span className="eyebrow">Order summary</span>
                          <h2>Current order</h2>
                          <OrderLines order={currentOrder || {}} />
                          <div className="order-total"><span>Total</span><strong>{money(currentOrder?.total)}</strong></div>
                        </section>
                      </section>
                    )}

                    {step === "payment" && (
                      <section className="handoff-card">
                        <div className="handoff-copy">
                          <span className="eyebrow">03 / {orderMode === "qr" ? "QR payment" : "Payment"}</span>
                          <h2>{orderMode === "qr" ? "Review and collect cash." : "Collect cash."}</h2>
                          <p>{orderMode === "qr" ? "This order was submitted by the customer. The basket is read-only." : "The order number appears after payment."}</p>
                          {orderMode === "qr" && <div className="order-number">{currentOrder?.order_number}</div>}
                          <div className="handoff-meta">
                            <span>{currentOrder?.customer_name || "Customer"}</span>
                            {orderMode === "qr" && currentOrder?.table_code && <span>{currentOrder.table_code}</span>}
                            <span>{money(currentOrder?.total)} due</span>
                            <StatusPill value={orderMode === "qr" ? "qr order" : "payment required"} />
                          </div>
                        </div>
                        <div className="handoff-action">
                          <div className="mini-summary"><OrderLines order={currentOrder || {}} compact /><div className="order-total"><span>Total due</span><strong>{money(currentOrder?.total)}</strong></div></div>
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
            tableRows={tableRows}
            receipts={receipts}
            search={search}
            setSearch={setSearch}
            onSearch={() => void loadSecondary("payments")}
            onRefresh={() => void loadSecondary(view)}
            onSelect={(order) => void openSecondaryOrder(order)}
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

function SecondaryView({ view, loading, paymentRows, kitchenRows, tableRows, receipts, search, setSearch, onSearch, onRefresh, onSelect }: { view: View; loading: boolean; paymentRows: Row[]; kitchenRows: Row[]; tableRows: Row[]; receipts: Row[]; search: string; setSearch: (value: string) => void; onSearch: () => void; onRefresh: () => void; onSelect: (order: Row) => void }) {
  const titles: Record<View, [string, string]> = {
    order: ["", ""],
    payments: ["02 / Payment", "QR orders"],
    kitchen: ["03 / Kitchen", "Kitchen"],
    ready: ["04 / Pickup", "Ready"],
    operations: ["05 / Reference", "Operations"],
  };
  const [eyebrow, heading] = titles[view];
  const description = view === "payments"
    ? "Select a submitted QR order and record cash."
    : view === "kitchen"
      ? "Paid orders appear here automatically."
      : view === "ready"
        ? "Call customers by name or order number."
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
      ) : (
        <div className="operations-grid">
          <section className="panel"><span className="eyebrow">Floor reference</span><h3>Tables</h3>{tableRows.length ? <div className="simple-list">{tableRows.map((table) => <div className="simple-row" key={table.id}><div><strong>{table.code}</strong><small>{table.name} · {table.seats} seats</small></div><StatusPill value={table.status} /></div>)}</div> : <Empty>No tables found.</Empty>}</section>
          <section className="panel"><span className="eyebrow">Sales history</span><h3>Receipts</h3>{receipts.length ? <div className="simple-list">{receipts.slice(0, 8).map((receipt) => <div className="simple-row" key={receipt.id}><div><strong>{receipt.receipt_number}</strong><small>{receipt.order_number} · {receipt.table_code}</small></div><strong>{money(receipt.total)}</strong></div>)}</div> : <Empty>No receipts yet.</Empty>}</section>
        </div>
      )}
    </section>
  );
}
