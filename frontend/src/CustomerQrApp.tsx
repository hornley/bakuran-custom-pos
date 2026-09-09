import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { isMockMode, mockApi } from "./mockData";

type MenuItem = {
  id: number;
  sku: string;
  category_id: number;
  category_code: string;
  category_name: string;
  name: string;
  description: string;
  price: number;
};

type CustomerSession = {
  table: { id: number; code: string; name: string; seats: number };
  session: { id: number; session_number: string; status: string };
  menu: MenuItem[];
};

type CustomerLine = {
  id?: number;
  menu_item_id: number;
  item_name: string;
  quantity: number;
  unit_price: number;
  line_total: number;
};

type CustomerOrderResponse = {
  order: {
    id: number;
    order_number: string;
    status: string;
    customer_name: string;
    order_channel: string;
    subtotal: number;
    total: number;
  };
  lines: CustomerLine[];
  table?: { table_code: string; table_name: string };
};

type ApiFailure = Error & { status?: number };

const API_BASE = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:5300`;
const MAX_ITEM_QUANTITY = 20;

function apiFailure(message: string, status?: number): ApiFailure {
  return Object.assign(new Error(message), { status });
}

async function customerApi<T>(token: string, suffix: string, options?: RequestInit): Promise<T> {
  if (isMockMode()) return mockApi<T>(`/api/customer/tables/demo-token${suffix}`, options);
  const response = await fetch(
    `${API_BASE}/api/customer/tables/${encodeURIComponent(token)}${suffix}`,
    {
      credentials: "omit",
      ...options,
      headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    },
  );
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw apiFailure(typeof body?.detail === "string" ? body.detail : "The request could not be completed.", response.status);
  }
  return body as T;
}

function createIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return randomUuid;
  return `qr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function money(value: number | undefined): string {
  return `₱${Number(value || 0).toFixed(2)}`;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function StatusPill({ value }: { value: string }) {
  const normalized = String(value || "unknown").toLowerCase();
  return <span className={`customer-status ${normalized}`}><span />{statusLabel(normalized)}</span>;
}

function CustomerError({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="customer-alert" role="alert">
      <strong>Needs attention</strong>
      <span>{message}</span>
      {onDismiss && <button type="button" aria-label="Dismiss error" onClick={onDismiss}>Dismiss</button>}
    </div>
  );
}

function EmptyBasket() {
  return (
    <div className="customer-empty-basket">
      <span className="customer-empty-mark">+</span>
      <strong>Your basket is empty.</strong>
      <p>Choose something from the menu to get started.</p>
    </div>
  );
}

function SummaryLines({ lines }: { lines: CustomerLine[] }) {
  if (!lines.length) return <EmptyBasket />;
  return (
    <div className="customer-summary-lines">
      {lines.map((line) => (
        <div className="customer-summary-line" key={line.id || `${line.menu_item_id}-${line.item_name}`}>
          <div>
            <strong>{line.item_name}</strong>
            <small>{line.quantity} × {money(line.unit_price)}</small>
          </div>
          <strong>{money(line.line_total)}</strong>
        </div>
      ))}
    </div>
  );
}

function CustomerShell({ children }: { children: ReactNode }) {
  return (
    <div className="customer-shell">
      <header className="customer-topbar">
        <div className="customer-brand"><span className="customer-brand-mark">BK</span><span>Bakuran</span></div>
        <span className="customer-topbar-note">Order at your table</span>
      </header>
      <main className="customer-main">{children}</main>
      <footer className="customer-footer"><span>Bakuran</span><span>Cash payment at the front desk</span></footer>
    </div>
  );
}

function loadErrorMessage(reason: unknown): string {
  const status = (reason as ApiFailure)?.status;
  if (status === 404) return "This QR code is invalid or the table session is closed.";
  return "We could not load this table's menu. Check your connection and try again.";
}

function submitErrorMessage(reason: unknown): string {
  const status = (reason as ApiFailure)?.status;
  if (status === 404) return "Your order could not be submitted because one or more items are no longer available.";
  if (status === 409) return "Your order could not be submitted because this table already has an order waiting for payment.";
  if (status === 422) return "Your order could not be submitted. Check your name and basket, then try again.";
  return "Your order could not be submitted. Check your connection and try again.";
}

export default function CustomerQrApp({ token }: { token: string }) {
  const [session, setSession] = useState<CustomerSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [customerName, setCustomerName] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<CustomerOrderResponse | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    void customerApi<CustomerSession>(token, "", { signal: controller.signal })
      .then((value) => setSession(value))
      .catch((reason: unknown) => {
        if ((reason as DOMException)?.name === "AbortError") return;
        setSession(null);
        setLoadError(loadErrorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, reloadCount]);

  const menu = session?.menu || [];
  const categories = useMemo(() => {
    const groups = new Map<string, MenuItem[]>();
    menu.forEach((item) => {
      const category = item.category_name || item.category_code || "Menu";
      groups.set(category, [...(groups.get(category) || []), item]);
    });
    return [...groups.entries()];
  }, [menu]);

  const basketLines = useMemo(
    () => menu
      .filter((item) => (quantities[item.id] || 0) > 0)
      .map((item) => ({
        menu_item_id: item.id,
        item_name: item.name,
        quantity: quantities[item.id],
        unit_price: item.price,
        line_total: item.price * quantities[item.id],
      })),
    [menu, quantities],
  );
  const basketTotal = basketLines.reduce((total, line) => total + line.line_total, 0);
  const basketItemCount = basketLines.reduce((total, line) => total + line.quantity, 0);
  const canSubmit = basketLines.length > 0 && customerName.trim().length > 0 && !busy;

  function setQuantity(itemId: number, next: number) {
    const bounded = Math.max(0, Math.min(MAX_ITEM_QUANTITY, Math.trunc(next) || 0));
    setQuantities((current) => {
      if (!bounded) {
        const { [itemId]: _removed, ...remaining } = current;
        return remaining;
      }
      return { ...current, [itemId]: bounded };
    });
  }

  function addItem(itemId: number) {
    setQuantity(itemId, (quantities[itemId] || 0) + 1);
    setSubmitError("");
  }

  async function placeOrder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!basketLines.length) {
      setSubmitError("Add at least one item before placing your order.");
      return;
    }
    if (!customerName.trim()) {
      setSubmitError("Enter a name so the counter can call you.");
      return;
    }

    const key = idempotencyKey || createIdempotencyKey();
    setIdempotencyKey(key);
    setBusy(true);
    setSubmitError("");
    try {
      const response = await customerApi<CustomerOrderResponse>(token, "/orders", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          customer_name: customerName.trim(),
          lines: basketLines.map((line) => ({ menu_item_id: line.menu_item_id, quantity: line.quantity })),
        }),
      });
      setSubmitted(response);
    } catch (reason) {
      setSubmitError(submitErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <CustomerShell><div className="customer-state" role="status">Loading your table menu…</div></CustomerShell>;
  }

  if (loadError || !session) {
    return (
      <CustomerShell>
        <section className="customer-state customer-state-error">
          <span className="customer-eyebrow">Table QR</span>
          <h1>QR code unavailable</h1>
          <CustomerError message={loadError || "This QR code is invalid or the table session is closed."} />
          <button type="button" className="customer-button" onClick={() => setReloadCount((count) => count + 1)}>Try again</button>
        </section>
      </CustomerShell>
    );
  }

  if (submitted) {
    const order = submitted.order;
    return (
      <CustomerShell>
        <section className="customer-confirmation" aria-live="polite">
          <div className="customer-success-mark">✓</div>
          <span className="customer-eyebrow">Confirmation</span>
          <h1>Order received</h1>
          <p className="customer-lede">Thanks, {order.customer_name}. Your order is waiting for cash payment at the front desk. It will enter the kitchen after payment.</p>
          <div className="customer-order-number">{order.order_number}</div>
          <div className="customer-confirmation-meta">
            <StatusPill value={order.status} />
            <span>{submitted.table?.table_code || session.table.code}</span>
            <strong>{money(order.total)}</strong>
          </div>
          <div className="customer-confirmation-summary">
            <span className="customer-eyebrow">Your order</span>
            <SummaryLines lines={submitted.lines} />
            <div className="customer-total"><span>Total</span><strong>{money(order.total)}</strong></div>
          </div>
        </section>
      </CustomerShell>
    );
  }

  return (
    <CustomerShell>
      <section className="customer-intro">
        <div>
          <span className="customer-eyebrow">Table {session.table.code}</span>
          <h1>What can we get you?</h1>
          <p className="customer-lede">Choose your favourites, then give us a name for pickup.</p>
        </div>
        <div className="customer-table-context"><span>Dining at</span><strong>{session.table.name}</strong></div>
      </section>

      {submitError && <CustomerError message={submitError} onDismiss={() => setSubmitError("")} />}

      <form className="customer-layout" onSubmit={(event) => void placeOrder(event)}>
        <section className="customer-menu-panel" aria-labelledby="menu-heading">
          <div className="customer-section-heading">
            <div><span className="customer-eyebrow">Menu</span><h2 id="menu-heading">Pick your order</h2></div>
            <span>{menu.length} items</span>
          </div>
          {categories.length ? categories.map(([category, items]) => (
            <section className="customer-category" key={category}>
              <h3>{category}</h3>
              <div className="customer-menu-grid">
                {items.map((item) => {
                  const quantity = quantities[item.id] || 0;
                  return (
                    <article className={`customer-menu-card ${quantity ? "selected" : ""}`} key={item.id}>
                      <div>
                        <h4>{item.name}</h4>
                        <p>{item.description}</p>
                      </div>
                      <div className="customer-menu-card-bottom">
                        <strong>{money(item.price)}</strong>
                        <button type="button" className="customer-add-button" aria-label={`Add ${item.name}`} onClick={() => addItem(item.id)} disabled={quantity >= MAX_ITEM_QUANTITY}>Add</button>
                      </div>
                      {quantity > 0 && (
                        <div className="customer-card-quantity" aria-label={`${item.name} quantity`}>
                          <button type="button" aria-label={`Decrease ${item.name}`} onClick={() => setQuantity(item.id, quantity - 1)}>−</button>
                          <span>{quantity}</span>
                          <button type="button" aria-label={`Increase ${item.name}`} onClick={() => setQuantity(item.id, quantity + 1)} disabled={quantity >= MAX_ITEM_QUANTITY}>+</button>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>
          )) : <div className="customer-state">No menu items are available right now.</div>}
        </section>

        <aside className="customer-basket-panel" aria-labelledby="basket-heading">
          <div className="customer-section-heading">
            <div><span className="customer-eyebrow">Your basket</span><h2 id="basket-heading">Order summary</h2></div>
            <span>{basketItemCount} items</span>
          </div>
          <SummaryLines lines={basketLines} />
          {basketLines.length > 0 && <div className="customer-total"><span>Total</span><strong>{money(basketTotal)}</strong></div>}
          <label className="customer-name-label" htmlFor="customer-name">Name for pickup</label>
          <input
            id="customer-name"
            className="customer-name-input"
            value={customerName}
            maxLength={80}
            onChange={(event) => { setCustomerName(event.target.value); setSubmitError(""); }}
            placeholder="e.g. Mika"
            autoComplete="name"
          />
          <p className="customer-field-note">The counter will call this name when your order is ready.</p>
          <button type="submit" className="customer-button customer-button-primary" disabled={!canSubmit}>{busy ? "Placing order…" : "Place order"}</button>
          <p className="customer-payment-note">Cash payment is collected at the front desk. Unpaid orders do not enter the kitchen.</p>
        </aside>
      </form>
    </CustomerShell>
  );
}
