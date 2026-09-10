import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import "./styles.css";
import { csrfHeaders } from "./auth";
import { isMockMode, mockApi } from "./mockData";

type Row = Record<string, any>;
type Step = "build" | "confirm" | "payment" | "fulfillment";
type View = "order" | "payments" | "kitchen" | "ready" | "delivery" | "operations";
type DeliveryAction = "assign" | "out-for-delivery" | "delivered" | "failed" | "cancel";
type OrderMode = "manual" | "qr" | "delivery" | null;

export function resolveApiBase(location?: Pick<Location, "protocol" | "hostname">) {
  const current = location || (typeof window !== "undefined" ? window.location : { protocol: "http:", hostname: "localhost" });
  return `${current.protocol}//${current.hostname}:5300`;
}

const API_BASE = import.meta.env.VITE_API_URL || resolveApiBase();
const PROJECT_NAME = "Bakuran POS";
const todayLabel = new Intl.DateTimeFormat("en-US", { dateStyle: "full" }).format(new Date());
const steps: Array<[Step, string]> = [
  ["build", "Basket"],
  ["confirm", "Customer"],
  ["payment", "Payment"],
  ["fulfillment", "Kitchen & pickup"],
];

const titles: Record<View, [string, string]> = {
  order: ["", ""],

  payments: ["02 / Payment", "QR orders"],
  kitchen: ["03 / Kitchen", "Kitchen"],
  ready: ["04 / Pickup", "Ready"],
  delivery: ["05 / Dispatch", "Delivery"],
  operations: ["06 / Reference", "Operations"],
};
type ApiError = Error & { responseReceived?: boolean };

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  if (isMockMode()) return mockApi<T>(path, options);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: { ...csrfHeaders(), "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || body.message || "The request could not be completed.") as ApiError;
    error.responseReceived = true;
    throw error;
  }
  return body as T;
}

const money = (value: any) => `₱${Number(value || 0).toFixed(2)}`;
const label = (value: any) => String(value ?? "").replaceAll("_", " ");
const newOperationKey = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

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
  const [loading, setLoading] = useState(false);
  const [secondaryLoading, setSecondaryLoading] = useState(false);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewQueueError, setOverviewQueueError] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [secondary, setSecondary] = useState<Record<string, any>>({});
  const [promotions, setPromotions] = useState<Row[]>([]);
  const [promotionLoading, setPromotionLoading] = useState(false);
  const [promotionError, setPromotionError] = useState("");
  const [promotionAvailabilityError, setPromotionAvailabilityError] = useState("");
  const [promotionCode, setPromotionCode] = useState("");
  const [promotionBusy, setPromotionBusy] = useState("");
  const [search, setSearch] = useState("");
  const [operationsWarehouse, setOperationsWarehouse] = useState(1);
  const secondaryRequest = useRef(0);
  const overviewRequest = useRef(0);
  const pendingOperationKeys = useRef(new Map<string, string>());
  const startingOrderRef = useRef(false);

  useEffect(() => {
    loadOverviewQueues();
  }, []);

  function operationKey(operationId: string, prefix: string) {
    const pending = pendingOperationKeys.current.get(operationId);
    if (pending) return pending;
    const key = newOperationKey(prefix);
    pendingOperationKeys.current.set(operationId, key);
    return key;
  }

  function clearOperationKey(operationId: string, key: string) {
    if (pendingOperationKeys.current.get(operationId) === key) pendingOperationKeys.current.delete(operationId);
  }

  async function mutate<T>(operationId: string, prefix: string, path: string, method: string, payload: Row, includeBodyIdempotency = true) {
    const key = operationKey(operationId, prefix);
    try {
      const headers = { "Idempotency-Key": key };
      const body = includeBodyIdempotency ? { ...payload, idempotency_key: key } : payload;
      const result = await api<T>(path, { method, headers, body: JSON.stringify(body) });
      clearOperationKey(operationId, key);
      return result;
    } catch (reason) {
      if ((reason as ApiError)?.responseReceived) clearOperationKey(operationId, key);
      throw reason;
    }
  }

  const categories = useMemo(
    () => Array.from(new Set(menu.map((item) => String(item.category_name || item.category || "Menu")))),
    [menu],
  );
  const currentLines = currentOrder?.lines || [];
  const orderStatus = String(currentOrder?.status || "open");
  const ticket = currentOrder?.ticket || null;

  function applyOrderPayload(payload: Row) {
    if (!payload?.order) return;
    const promotion = payload.promotion ?? payload.order.promotion ?? null;
    setCurrentOrder({
      ...payload.order,
      lines: payload.lines || [],
      ticket: payload.ticket || null,
      payment: payload.payment || null,
      receipt: payload.receipt || null,
      tax: payload.tax || null,
      delivery: payload.delivery || null,
      promotion,
    });
    if (promotion) {
      setPromotionError("");
      setPromotionCode("");
    }
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
      const errorMessage = reason instanceof Error ? reason.message : "Could not reach the Bakuran API.";
      setError(errorMessage);
      throw reason;
    } finally {
      setLoading(false);
    }
  }

  async function loadPromotions() {
    try {
      setPromotionLoading(true);
      setPromotionError("");
      setPromotionAvailabilityError("");
      const available = await api<Row[]>("/api/promotions");
      setPromotions(available);
      return available;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Could not load promotions.";
      setPromotionAvailabilityError(message);
      setPromotionError(message);
      return [];
    } finally {
      setPromotionLoading(false);
    }
  }

  async function refreshOrder(orderId: number) {
    const payload = await api<Row>(`/api/orders/${orderId}`);
    applyOrderPayload(payload);
    return payload;
  }

  async function ensureOrder(forceNew = false) {
    if (currentOrder && !forceNew) return currentOrder;
    const payload = await api<Row>("/api/counter/orders", { method: "POST", body: JSON.stringify({}) });
    applyOrderPayload(payload);
    setOrderMode("manual");
    return { ...payload.order, lines: payload.lines || [] };
  }

  async function startOrder() {
    if (startingOrderRef.current || busy) return;
    startingOrderRef.current = true;
    try {
      setBusy("start");
      setError("");
      setNotice("");
      if (!menu.length) await loadMenu();
      if (!promotions.length) await loadPromotions();
      const forceNew = !!currentOrder && String(currentOrder.status) !== "open";
      if (forceNew) {
        setCurrentOrder(null);
        setOrderMode(null);
        setCustomerName("");
        setDeliveryAddress("");
        setDeliveryContact("");
        setDeliveryContactName("");
        setQuantities({});
        setPromotionCode("");
        setPromotionError("");
      }
      await ensureOrder(forceNew);
      setCompletedReceipt(null);
      setShowEntryChoice(false);
      setStep("build");
      setView("order");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start a new order.");
    } finally {
      startingOrderRef.current = false;
      setBusy("");
    }
  }

  async function startDeliveryOrder() {
    if (startingOrderRef.current || busy) return;
    startingOrderRef.current = true;
    try {
      setBusy("delivery-start");
      setError("");
      setNotice("");
      setCustomerName("");
      setDeliveryAddress("");
      setDeliveryContact("");
      setDeliveryContactName("");
      setQuantities({});
      setPromotionCode("");
      setPromotionError("");
      if (!promotions.length) await loadPromotions();
      if (!menu.length) await loadMenu();
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
      startingOrderRef.current = false;
      setBusy("");
    }
  }

  async function applyPromotion() {
    if (!currentOrder || !promotionCode.trim()) return;
    const code = promotionCode.trim();
    const operationId = `promotion-apply-${currentOrder.id}`;
    try {
      setPromotionBusy(operationId);
      setPromotionError("");
      setError("");
      const payload = await mutate<Row>(operationId, "promotion", `/api/orders/${currentOrder.id}/promotions`, "POST", { code }, false);
      applyOrderPayload(payload);
      setPromotionCode("");
      setNotice("Promotion applied.");
    } catch (reason) {
      setPromotionError(reason instanceof Error ? reason.message : "Could not apply this promotion.");
    } finally {
      setPromotionBusy("");
    }
  }

  async function removePromotion() {
    if (!currentOrder?.promotion) return;
    const appliedId = currentOrder.promotion.id ?? currentOrder.promotion.applied_id;
    const operationId = `promotion-remove-${currentOrder.id}-${appliedId}`;
    try {
      setPromotionBusy(operationId);
      setPromotionError("");
      setError("");
      const payload = await mutate<Row>(operationId, "promotion-remove", `/api/orders/${currentOrder.id}/promotions/${appliedId}`, "DELETE", {}, false);
      applyOrderPayload(payload);
      setNotice("Promotion removed.");
    } catch (reason) {
      setPromotionError(reason instanceof Error ? reason.message : "Could not remove this promotion.");
    } finally {
      setPromotionBusy("");
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
    setPromotionCode("");
    setPromotionError("");
    setPromotionBusy("");
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
    setPromotionCode("");
    setPromotionError("");
    setPromotionBusy("");
  }

  async function loadSecondary(target: View, warehouseId = operationsWarehouse) {
    if (target === "order") return;
    const requestId = ++secondaryRequest.current;
    try {
      setSecondaryLoading(true);

      const path = target === "payments"
        ? `/api/payment-queue${search ? `?q=${encodeURIComponent(search)}` : ""}`
        : target === "ready"
          ? "/api/kitchen?queue=ready"
          : target === "delivery"
            ? "/api/delivery"
            : "/api/kitchen";
      if (target === "operations") {
        const [tables, receipts, inventoryPayload, warehouseRows, purchaseRows, catalogRows, supplierRows, auditRows, taxConfiguration] = await Promise.all([
          api<Row[]>("/api/tables"),
          api<Row[]>("/api/receipts"),
          api<Row>(`/api/inventory?warehouse_id=${warehouseId}`),
          api<Row[]>("/api/warehouses"),
          api<Row[]>("/api/purchases"),
          api<Row[]>("/api/catalog"),
          api<Row[]>("/api/suppliers"),
          api<Row[]>("/api/audit-events"),
          api<Row>("/api/tax/configuration"),
        ]);
        if (requestId !== secondaryRequest.current) return;
        setSecondary((current) => ({
          ...current,
          operations: tables,
          receipts,
          inventory: inventoryPayload.products || [],
          movements: inventoryPayload.movements || [],
          warehouses: warehouseRows,
          purchases: purchaseRows,
          catalog: catalogRows.filter((item) => item.active !== 0),
          suppliers: supplierRows.filter((supplier) => supplier.active !== 0),
          audit: auditRows,
          taxConfiguration,
        }));
      } else {
        const values = await api<Row[]>(path);
        if (requestId !== secondaryRequest.current) return;
        setSecondary((current) => ({ ...current, [target]: values }));
        if (target === "delivery") {
          const drivers = await api<Row[]>("/api/delivery/drivers");
          if (requestId !== secondaryRequest.current) return;
          setSecondary((current) => ({ ...current, deliveryDrivers: drivers }));
        }
      }
    } catch (reason) {
      if (requestId === secondaryRequest.current) {
        setError(reason instanceof Error ? reason.message : "Could not load this operational view.");
      }
    } finally {
      if (requestId === secondaryRequest.current) setSecondaryLoading(false);
    }
  }

  function loadOverviewQueues() {
    const requestId = ++overviewRequest.current;
    setOverviewLoading(true);
    setOverviewQueueError("");
    void Promise.all([
      api<Row[]>("/api/kitchen"),
      api<Row[]>("/api/kitchen?queue=ready"),
      api<Row[]>("/api/payment-queue"),
    ]).then(([kitchen, ready, payments]) => {
      if (requestId !== overviewRequest.current) return;
      setSecondary((current) => ({ ...current, kitchen, ready, payments: payments.filter((order) => order.status === "awaiting_payment") }));
      setOverviewLoading(false);
    }).catch(() => {
      if (requestId !== overviewRequest.current) return;
      setOverviewLoading(false);
      setOverviewQueueError("Live service status is temporarily unavailable.");
    });
  }

  async function inventoryAdjustment(values: Row) {
    try {
      setBusy("inventory-adjustment");
      setError("");
      await mutate("inventory-adjustment", "adjustment", "/api/stock/adjustment", "POST", values);
      setNotice("Stock adjustment saved.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the stock adjustment.");
    } finally {
      setBusy("");
    }
  }

  async function updateReorderLevel(values: Row) {
    try {
      setBusy(`reorder-${values.product_id}`);
      setError("");
      await mutate(`reorder-${values.warehouse_id}-${values.product_id}`, "reorder", "/api/inventory/reorder-level", "PUT", values);
      setNotice("Reorder level saved.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the reorder level.");
    } finally {
      setBusy("");
    }
  }

  async function createPurchase(supplierId: number) {
    try {
      setBusy("purchase-create");
      setError("");
      await mutate("purchase-create", "purchase", "/api/purchases", "POST", { supplier_id: supplierId });
      setNotice("Draft purchase created.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the purchase.");
    } finally {
      setBusy("");
    }
  }

  async function addPurchaseLine(purchaseId: number, values: Row) {
    try {
      setBusy(`purchase-line-${purchaseId}`);
      setError("");
      await mutate(`purchase-line-${purchaseId}`, "purchase-line", `/api/purchases/${purchaseId}/lines`, "POST", values);
      setNotice("Purchase line added.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not add the purchase line.");
    } finally {
      setBusy("");
    }
  }

  async function changePurchaseStatus(purchaseId: number, action: "order" | "close") {
    try {
      setBusy(`purchase-${action}-${purchaseId}`);
      setError("");
      await mutate(`purchase-${action}-${purchaseId}`, `purchase-${action}`, `/api/purchases/${purchaseId}/${action}`, "POST", {});
      setNotice(action === "order" ? "Purchase ordered." : "Purchase closed.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the purchase.");
    } finally {
      setBusy("");
    }
  }

  async function receivePurchase(purchaseId: number, values: Row) {
    try {
      setBusy(`purchase-receive-${purchaseId}`);
      setError("");
      await mutate(`purchase-receive-${purchaseId}`, "receipt", `/api/purchases/${purchaseId}/receive`, "POST", values);
      setNotice("Receipt saved and inventory updated.");
      await loadSecondary("operations");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not receive this purchase.");
    } finally {
      setBusy("");
    }
  }

  function navigate(target: View) {
    setView(target);
    setError("");
    if (target === "order") loadOverviewQueues();
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

  async function openSecondaryOrder(order: Row, paymentQueue = false) {
    try {
      setError("");
      const payload = await refreshOrder(order.id || order.order_id);
      const isPaymentQueue = paymentQueue || view === "payments";
      setOrderMode(isPaymentQueue ? "qr" : payload.order.order_channel === "qr" ? "qr" : payload.order.order_channel === "delivery" ? "delivery" : "manual");
      setStep(isPaymentQueue ? "payment" : "fulfillment");
      setShowEntryChoice(false);
      setView("order");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not open this order.");
    }
  }

  const hasItems = currentLines.length > 0;
  const currentStepIndex = steps.findIndex(([key]) => key === step);
  const kitchenRows = secondary.kitchen || [];
  const readyRows = (secondary.ready || []).filter((row: Row) => ["ready", "served"].includes(row.status));
  const paymentRows = (secondary.payments || []).filter((row: Row) => row.order_channel === "qr");
  const deliveryRows = secondary.delivery || [];
  const deliveryDrivers = secondary.deliveryDrivers || [];
  const tableRows = (secondary.operations || []).filter((row: Row) => row.code !== "COUNTER");
  const receipts = secondary.receipts || [];
  const inventoryRows = secondary.inventory || [];
  const warehouses = secondary.warehouses || [];
  const purchases = secondary.purchases || [];
  const catalog = secondary.catalog || [];
  const suppliers = secondary.suppliers || [];
  const auditEvents = secondary.audit || [];
  const attentionRows = [
    ...paymentRows.map((order: Row) => ({ key: `payment-${order.id}`, order: order.order_number, orderMeta: `${order.lines?.length || 0} items · QR order`, customer: order.customer_name || order.table_code || "QR order", customerMeta: order.table_code || "Table order", status: order.status || "awaiting_payment", action: "Review & pay", onAction: () => void openSecondaryOrder(order, true) })),
    ...kitchenRows.filter((ticket: Row) => !["ready", "served"].includes(ticket.status)).map((ticket: Row) => ({ key: `kitchen-${ticket.id}`, order: ticket.order_number, orderMeta: ticket.ticket_number || "Kitchen ticket", customer: ticket.customer_name || "Customer", customerMeta: ticket.table_code === "COUNTER" ? "Counter pickup" : ticket.table_code || "Pickup", status: ticket.status, action: "Open", onAction: () => void openSecondaryOrder({ ...ticket, id: ticket.order_id }) })),
    ...readyRows.map((ticket: Row) => ({ key: `ready-${ticket.id}`, order: ticket.order_number, orderMeta: ticket.ticket_number || "Ready for pickup", customer: ticket.customer_name || "Customer", customerMeta: ticket.table_code === "COUNTER" ? "Counter pickup" : ticket.table_code || "Pickup desk", status: ticket.status, action: "Open", onAction: () => void openSecondaryOrder({ ...ticket, id: ticket.order_id }) })),
  ].slice(0, 4);

  return (
    <div className="operator-shell">
      <aside className="operator-rail" aria-label="Bakuran navigation">
        <div className="rail-brand"><span className="brand-mark">BK</span><span>{PROJECT_NAME}</span></div>
        <nav className="rail-nav" aria-label="Bakuran operations">
          <span className="rail-label">Workspace</span>
          <button className={`rail-link ${view === "order" && showEntryChoice ? "active" : ""}`} onClick={() => { setShowEntryChoice(true); setView("order"); loadOverviewQueues(); }}><span className="rail-icon" aria-hidden="true">O</span>Overview</button>
          <span className="rail-label">Sell</span>
          <button className={`rail-link ${view === "order" && !showEntryChoice ? "active" : ""}`} onClick={() => void startOrder()} disabled={busy === "start"}><span className="rail-icon" aria-hidden="true">＋</span>New order</button>
          <button className={`rail-link ${view === "payments" ? "active" : ""}`} onClick={() => navigate("payments")}><span className="rail-icon" aria-hidden="true">QR</span>QR payments{paymentRows.length > 0 && <b>{paymentRows.length}</b>}</button>
          <span className="rail-label">Fulfillment</span>
          <button className={`rail-link ${view === "kitchen" ? "active" : ""}`} onClick={() => navigate("kitchen")}><span className="rail-icon" aria-hidden="true">K</span>Kitchen{(secondary.kitchen || []).length > 0 && <b>{(secondary.kitchen || []).length}</b>}</button>
          <button className={`rail-link ${view === "ready" ? "active" : ""}`} onClick={() => navigate("ready")}><span className="rail-icon" aria-hidden="true">R</span>Ready{readyRows.length > 0 && <b>{readyRows.length}</b>}</button>
          <span className="rail-label">Operations</span>
          <button className={`rail-link ${view === "delivery" ? "active" : ""}`} onClick={() => navigate("delivery")}><span className="rail-icon" aria-hidden="true">D</span>Delivery{deliveryRows.length > 0 && <b>{deliveryRows.length}</b>}</button>
          <button className={`rail-link ${view === "operations" ? "active" : ""}`} onClick={() => navigate("operations")}><span className="rail-icon" aria-hidden="true">Ops</span>Operations</button>
        </nav>
        <div className="rail-shift"><span>Current shift</span><strong>Front desk · Current shift</strong></div>
      </aside>

      <div className="operator-content">
        <header className="topbar">
          <div className="topbar-context"><span>{todayLabel}</span><span className="topbar-register">Cash desk · Local <i className="live-dot" />{overviewLoading ? "Checking" : overviewQueueError ? "Attention" : "Online"}</span>{isMockMode() && <span className="mock-badge">Preview data</span>}</div>
          <div className="topbar-right"><span className="operator-avatar" aria-label="Current operator">OP</span></div>
        </header>

        <main className="main">
          {view === "order" && showEntryChoice ? (
            <section className="overview-view">
              <div className="hero overview-hero">
                <div><h1>Overview</h1></div>
                <button className="action-button primary hero-action" onClick={() => void startOrder()} disabled={busy === "start"}>{busy === "start" ? "Starting…" : "New order"}</button>
              </div>
              <section className="service-strip" aria-label="Live service status">
                <div className="service-cell active"><span>Front desk</span><strong>{overviewLoading ? "Checking status…" : overviewQueueError ? "Unavailable" : "Taking orders"}</strong></div>
                <div className="service-cell"><span>Kitchen</span><strong>{overviewLoading ? "Checking status…" : overviewQueueError ? "Unavailable" : kitchenRows.length ? `${kitchenRows.length} in motion` : "Ready"}</strong></div>
                <div className="service-cell"><span>Pickup</span><strong>{overviewLoading ? "Checking status…" : overviewQueueError ? "Unavailable" : readyRows.length ? `${readyRows.length} ready` : "Clear"}</strong></div>
                <div className="service-cell"><span>Cash gate</span><strong>{overviewLoading ? "Checking status…" : overviewQueueError ? "Unavailable" : paymentRows.length ? `${paymentRows.length} to review` : "All clear"}</strong></div>
              </section>
              <section className="queue-surface" aria-labelledby="attention-heading">
                <div className="surface-heading"><h2 id="attention-heading">Attention queue</h2><button className="text-button" onClick={() => navigate("kitchen")}>View kitchen</button></div>
                <div className="queue-header"><span>Order</span><span>Customer / table</span><span>Status</span><span>Action</span></div>
                {overviewLoading ? <div className="state" role="status">Loading live queue…</div> : overviewQueueError ? <div className="state" role="alert">{overviewQueueError}</div> : attentionRows.length ? <div role="list">{attentionRows.map((row) => <div className="queue-row" key={row.key} role="listitem"><div><strong>{row.order}</strong><small>{row.orderMeta}</small></div><div><strong>{row.customer}</strong><small>{row.customerMeta}</small></div><StatusPill value={row.status} /><button className={`row-action ${["ready", "served"].includes(row.status) ? "success" : ""}`} onClick={row.onAction}>{row.action}</button></div>)}</div> : <Empty>No orders need attention right now.</Empty>}
              </section>
              <div className="shortcut-panel"><button className="shortcut-tile" onClick={() => void startOrder()}><span className="shortcut-icon" aria-hidden="true">+</span><strong>Start order</strong></button><button className="shortcut-tile" onClick={() => navigate("payments")}><span className="shortcut-icon" aria-hidden="true">QR</span><strong>Review QR payments</strong></button><button className="shortcut-tile" onClick={() => navigate("delivery")}><span className="shortcut-icon" aria-hidden="true">D</span><strong>Open delivery</strong></button></div>
            </section>
          ) : (
            <>
              <section className="hero compact-hero">
                <div><h1>{view === "order" ? "Build an order." : titles[view][1]}</h1></div>
                {currentOrder && (orderMode === "qr" || step === "fulfillment" || currentOrder.status === "closed") && <div className="hero-side"><span className="hero-order">{currentOrder.order_number}<small>{label(orderStatus)}</small></span></div>}
              </section>
              <nav className={`tabs ${view === "order" ? "order-tabs" : ""}`} aria-label="Bakuran operations">
                {([["order", "New order"], ["payments", "QR payments"], ["kitchen", "Kitchen"], ["ready", "Ready"], ["delivery", "Delivery"], ["operations", "Operations"]] as Array<[View, string]>).map(([key, text]) => <button className={view === key ? "active" : ""} key={key} onClick={() => navigate(key)}>{text}</button>)}
              </nav>
            </>
          )}

        {error && <div className="banner error" role="alert"><strong>Needs attention</strong><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
        {notice && <div className="banner notice" role="status"><strong>Saved</strong><span>{notice}</span><button onClick={() => setNotice("")}>Dismiss</button></div>}

        {view === "order" ? (
          <>
            {!showEntryChoice && (
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
                          <div className="panel-heading"><div><h2>Choose items</h2></div><span className="panel-mark">{menu.length} items</span></div>

                          {loading ? <div className="state">Loading menu…</div> : (
                            <div className="category-list">
                              {categories.map((category) => (
                                <div className="category-block" key={category}>
                                  <span className="category-label">{category}</span>
                                  <div className="menu-list">
                                    {menu.filter((item) => (item.category_name || item.category || "Menu") === category).map((item) => {
                                      const key = `add-${item.id}`;
                                      return (
                                        <div className="menu-row" key={item.id}>
                                          <button type="button" className="menu-card-main" aria-label={`Add ${item.name} to order`} disabled={!!busy} onClick={() => void addItem(item)}>
                                            <div><strong>{item.name}</strong><small>{item.description || "Menu item"}</small></div>
                                            <div className="menu-card-meta"><span className="menu-price">{money(item.price)}</span><span className="menu-add-button" aria-hidden="true">{busy === key ? "Adding…" : "Add"}</span></div>
                                          </button>
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
                          <div className="panel-heading"><div><h2>Current order</h2></div><span className="panel-mark">{currentLines.length} lines</span></div>
                          {hasItems ? (
                            <>
                              <OrderLines order={currentOrder || {}} />
                              <TaxBreakdown order={currentOrder || {}} />
                            </>
                          ) : (
                            <div className="basket-start"><div className="basket-icon">+</div><strong>Add items to begin.</strong></div>
                          )}
                          {hasItems && <PromotionControl
                            order={currentOrder || {}}
                            promotions={promotions}
                            loading={promotionLoading}
                            error={promotionError}
                            availabilityError={promotionAvailabilityError}
                            code={promotionCode}
                            busy={promotionBusy}
                            onCodeChange={setPromotionCode}
                            onApply={() => void applyPromotion()}
                            onRemove={() => void removePromotion()}
                          />}
                          <div className="button-row basket-actions">
                            <button className="action-button primary" disabled={!hasItems || !!busy} onClick={() => setStep("confirm")}>Review order</button>
                          </div>
                        </section>
                      </section>
                    )}

                    {step === "confirm" && (
                      <section className="flow-grid confirm-grid">
                        <section className="panel">
                          <div className="panel-heading"><div><h2>{orderMode === "delivery" ? "Where should it go?" : "Name for pickup"}</h2></div></div>

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
                          <h2>Current order</h2>
                          <OrderLines order={currentOrder || {}} />
                          <TaxBreakdown order={currentOrder || {}} />
                        </section>
                      </section>
                    )}

                    {step === "payment" && (
                      <section className="handoff-card">
                        <div className="handoff-copy">
                          <h2>{orderMode === "qr" ? "Review and collect cash." : orderMode === "delivery" ? "Collect cash for delivery." : "Collect cash."}</h2>

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
                          <div><span className="eyebrow">04 / Kitchen & pickup</span><h2>{ticket?.status === "served" ? "Ready for pickup." : "Order is moving."}</h2></div>
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
            inventoryRows={inventoryRows}
            warehouses={warehouses}
            purchases={purchases}
            catalog={catalog}
            suppliers={suppliers}
            auditEvents={auditEvents}
            operationsWarehouse={operationsWarehouse}
            onWarehouseChange={(warehouseId) => { setOperationsWarehouse(warehouseId); void loadSecondary("operations", warehouseId); }}
            onAdjust={inventoryAdjustment}
            onReorderLevel={updateReorderLevel}
            onCreatePurchase={createPurchase}
            onAddPurchaseLine={addPurchaseLine}
            onChangePurchaseStatus={changePurchaseStatus}
            onReceivePurchase={receivePurchase}
            busy={busy}
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
      </div>
  );
}

function EntryChoice({ onManual, onQr, busy }: { onManual: () => void; onQr: () => void; busy: boolean }) {
  return (
    <section className="entry-choice" aria-label="Start at counter">
      <div className="entry-grid">
        <button className="entry-card" onClick={onManual} disabled={busy}>
          <span className="entry-icon">+</span>
          <h3>New order</h3>
          <strong>{busy ? "Starting…" : "Start order"}</strong>
        </button>
        <button className="entry-card qr" onClick={onQr} disabled={busy}>
          <span className="entry-icon">QR</span>
          <h3>QR orders</h3>
          <strong>Open orders</strong>
        </button>
      </div>
    </section>
  );
}

function TaxBreakdown({ order }: { order: Row }) {
  const tax = order.tax || {};
  const policy = String(tax.policy ?? order.tax_policy ?? "none");
  const taxableSubtotal = tax.taxable_subtotal ?? order.taxable_subtotal ?? order.discounted_subtotal ?? order.subtotal ?? 0;
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

function PromotionControl({
  order,
  promotions,
  loading,
  error,
  availabilityError,
  code,
  busy,
  onCodeChange,
  onApply,
  onRemove,
}: {
  order: Row;
  promotions: Row[];
  loading: boolean;
  error: string;
  availabilityError: string;
  code: string;
  busy: string;
  onCodeChange: (value: string) => void;
  onApply: () => void;
  onRemove: () => void;
}) {
  const applied = order.promotion;
  const canApply = !availabilityError && promotions.length > 0 && promotions.some((promotion) => promotion.can_apply !== false && promotion.active !== false && !["inactive", "expired", "scheduled", "exhausted"].includes(String(promotion.status || "").toLowerCase()));
  const isReadOnly = promotions.length > 0 && !canApply;
  return (
    <section className="promotion-control" aria-label="Promotion">
      <div className="promotion-heading">
        <div><span className="eyebrow">Optional</span><h3>Promotion code</h3></div>
        {loading && <span className="promotion-state" role="status">Loading codes…</span>}
        {!loading && !error && !promotions.length && <span className="promotion-state" role="status">No active codes.</span>}
      </div>
      {applied && <div className="promotion-applied" role="status">
        <div><strong>{applied.code}</strong><small>{applied.name || "Promotion applied"}</small></div>
        <button className="text-button" type="button" onClick={onRemove} disabled={!!busy}>{busy.startsWith("promotion-remove") ? "Removing…" : "Remove promotion"}</button>
      </div>}
      <div className="promotion-form">
        <label className="sr-only" htmlFor="promotion-code">Promotion code</label>
        <input id="promotion-code" className="text-input" value={code} onChange={(event) => onCodeChange(event.target.value)} placeholder="Enter code" disabled={loading || !canApply || !!busy} />
        <button aria-label="Apply promotion" className="action-button" type="button" onClick={onApply} disabled={loading || !canApply || !code.trim() || !!busy}>{busy.startsWith("promotion-apply") ? "Applying…" : applied ? "Replace promotion" : "Apply promotion"}</button>
      </div>
      {isReadOnly && <p className="promotion-permission" role="status">Promotion access is read-only for this operator.</p>}
      {error && <p className="promotion-error" role="alert">{error}</p>}
      {applied && <div className="promotion-pricing"><div><span>Discount</span><strong>−{money(order.discount_amount ?? applied.discount_amount)}</strong></div><div><span>Discounted subtotal</span><strong>{money(order.discounted_subtotal ?? applied.discounted_subtotal)}</strong></div></div>}
    </section>
  );
}

type SecondaryViewProps = {
  view: View;
  loading: boolean;
  paymentRows: Row[];
  kitchenRows: Row[];
  deliveryRows: Row[];
  deliveryDrivers: Row[];
  deliveryBusy: boolean;
  tableRows: Row[];
  receipts: Row[];
  taxConfiguration: Row | null;
  taxSaving: boolean;
  onSaveTaxRule: (payload: Row) => Promise<boolean>;
  inventoryRows: Row[];
  warehouses: Row[];
  purchases: Row[];
  catalog: Row[];
  suppliers: Row[];
  auditEvents: Row[];
  operationsWarehouse: number;
  onWarehouseChange: (warehouseId: number) => void;
  onAdjust: (values: Row) => void;
  onReorderLevel: (values: Row) => void;
  onCreatePurchase: (supplierId: number) => void;
  onAddPurchaseLine: (purchaseId: number, values: Row) => void;
  onChangePurchaseStatus: (purchaseId: number, action: "order" | "close") => void;
  onReceivePurchase: (purchaseId: number, values: Row) => void;
  busy: string;
  search: string;
  setSearch: (value: string) => void;
  onSearch: () => void;
  onRefresh: () => void;
  onSelect: (order: Row) => void;
  onDeliveryAction: (deliveryId: number, action: DeliveryAction, body?: Row) => void;
  onStartDelivery: () => void;
};

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
      <div className="delivery-board-toolbar"><button className="action-button primary" onClick={onStartDelivery} disabled={busy}>New delivery</button></div>
      {deliveries.length ? <div className="delivery-board" role="list">
        {deliveries.map((delivery) => {
          const status = String(delivery.status);
          const selected = selectedDriver(delivery);
          const terminal = ["delivered", "failed", "cancelled"].includes(status);
          return (
            <article className="delivery-card" key={delivery.id} role="listitem">
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


function SecondaryView({
  view,
  loading,
  paymentRows,
  kitchenRows,
  deliveryRows,
  deliveryDrivers,
  deliveryBusy,
  tableRows,
  receipts,
  taxConfiguration,
  taxSaving,
  onSaveTaxRule,
  inventoryRows,
  warehouses,
  purchases,
  catalog,
  suppliers,
  auditEvents,
  operationsWarehouse,
  onWarehouseChange,
  onAdjust,
  onReorderLevel,
  onCreatePurchase,
  onAddPurchaseLine,
  onChangePurchaseStatus,
  onReceivePurchase,
  busy,
  search,
  setSearch,
  onSearch,
  onRefresh,
  onSelect,
  onDeliveryAction,
  onStartDelivery,
}: SecondaryViewProps) {
  const [adjustmentProduct, setAdjustmentProduct] = useState(1);
  const [adjustmentQuantity, setAdjustmentQuantity] = useState("1");
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const [reorderLevels, setReorderLevels] = useState<Record<string, string>>({});
  const [purchaseSupplier, setPurchaseSupplier] = useState(1);
  const [lineDrafts, setLineDrafts] = useState<Record<string, Row>>({});
  const [receiptDrafts, setReceiptDrafts] = useState<Record<string, Row>>({});
  const [, heading] = titles[view];
  const activeProducts = catalog.filter((item) => item.active !== 0);
  const lowStockRows = inventoryRows.filter((row) => row.low_stock);
  const defaultProduct = activeProducts[0]?.id || adjustmentProduct;
  const defaultSupplier = suppliers[0]?.id || purchaseSupplier;

  function lineDraft(purchase: Row) {
    return lineDrafts[purchase.id] || {
      product_id: defaultProduct,
      warehouse_id: operationsWarehouse,
      quantity: "1",
      unit_cost: "0",
    };
  }

  function receiptDraft(purchase: Row) {
    return receiptDrafts[purchase.id] || { quantities: {}, allow_over_receipt: false, override_reason: "" };
  }

  function updateLineDraft(purchaseId: number, key: string, value: string | number) {
    const current = lineDrafts[purchaseId] || lineDraft({ id: purchaseId });
    setLineDrafts((drafts) => ({ ...drafts, [purchaseId]: { ...current, [key]: value } }));
  }

  function updateReceiptDraft(purchaseId: number, next: Row) {
    setReceiptDrafts((drafts) => ({ ...drafts, [purchaseId]: next }));
  }

  function submitAdjustment() {
    const quantity = Number(adjustmentQuantity);
    if (!Number.isInteger(quantity) || quantity === 0 || !adjustmentReason.trim()) return;
    onAdjust({ product_id: adjustmentProduct || defaultProduct, warehouse_id: operationsWarehouse, quantity, reason: adjustmentReason.trim() });
    setAdjustmentReason("");
  }

  function reorderKey(row: Row) {
    return `${row.warehouse_id}-${row.product_id}`;
  }

  return (
    <section className="secondary-page">
      <div className="secondary-heading">
        <div><h1>{heading}</h1></div>
        <button className="refresh" onClick={onRefresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      {view === "payments" && (
        <div className="search-row">
          <input className="text-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Order number, name, or table" />
          <button className="action-button" onClick={onSearch}>Search</button>
        </div>
      )}

      {loading ? <div className="panel state">Loading…</div> : view === "payments" ? (
        <div className="queue-list" role="list">
          {paymentRows.length ? paymentRows.map((order) => (
            <article className="queue-card" key={order.id} role="listitem">
              <div><span className="eyebrow">{order.order_number}</span><h3>{order.customer_name || "Unnamed customer"}</h3><p>{order.table_code || "QR order"} · {order.lines?.length || 0} items</p></div>
              <div className="queue-side"><strong>{money(order.total)}</strong><StatusPill value="awaiting" /><button className="action-button" onClick={() => onSelect(order)}>Review & pay</button></div>
            </article>
          )) : <Empty>No QR orders are waiting for payment.</Empty>}
        </div>
      ) : view === "kitchen" || view === "ready" ? (
        <div className="queue-list" role="list">
          {kitchenRows.length ? kitchenRows.map((ticket) => (
            <article className="queue-card" key={ticket.id} role="listitem">
              <div><span className="eyebrow">{ticket.order_number}</span><h3>{ticket.customer_name || "Customer"}</h3><p>{ticket.table_code === "COUNTER" ? "Counter" : ticket.table_code} · {ticket.ticket_number}</p></div>
              <div className="queue-side"><StatusPill value={ticket.status} /><button className="action-button" onClick={() => onSelect({ id: ticket.order_id, status: ticket.status, order_number: ticket.order_number, customer_name: ticket.customer_name, ticket })}>Open order</button></div>
            </article>
          )) : <Empty>No orders in this queue.</Empty>}
        </div>
      ) : view === "delivery" ? (
        <DeliveryBoard deliveries={deliveryRows} drivers={deliveryDrivers} busy={loading || deliveryBusy} onAction={onDeliveryAction} onStartDelivery={onStartDelivery} />
      ) : (
        <div className="operations-stack">
          <section className="operations-toolbar">
            <label className="field-inline"><span>Warehouse</span><select className="text-input" value={operationsWarehouse} onChange={(event) => onWarehouseChange(Number(event.target.value))}>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.code} · {warehouse.name}</option>)}</select></label>
            <div className="operations-summary"><span>{inventoryRows.length} stock records</span><strong>{lowStockRows.length} low stock</strong></div>
          </section>

          <div className="operations-grid">
            <section className="panel operations-panel">
              <span className="eyebrow">Inventory / adjustment</span>
              <h3>Move stock with a reason</h3>

              <div className="form-grid">
                <label className="field-label">Product<select className="text-input" value={adjustmentProduct || defaultProduct} onChange={(event) => setAdjustmentProduct(Number(event.target.value))}>{activeProducts.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name}</option>)}</select></label>
                <label className="field-label">Quantity<input className="text-input" type="number" step="1" value={adjustmentQuantity} onChange={(event) => setAdjustmentQuantity(event.target.value)} /></label>
              </div>
              <label className="field-label">Reason<input className="text-input" value={adjustmentReason} onChange={(event) => setAdjustmentReason(event.target.value)} placeholder="Cycle count, damage, correction…" /></label>
              <button className="action-button primary" disabled={!!busy || !adjustmentReason.trim() || !Number.isInteger(Number(adjustmentQuantity)) || Number(adjustmentQuantity) === 0} onClick={submitAdjustment}>{busy === "inventory-adjustment" ? "Saving…" : "Save adjustment"}</button>
            </section>

            <section className="panel operations-panel">
              <span className="eyebrow">Inventory / reorder</span>
              <h3>Low-stock visibility</h3>
              {lowStockRows.length ? <div className="simple-list">{lowStockRows.map((row) => { const key = reorderKey(row); return <div className="simple-row inventory-row" key={key}><div><strong>{row.name}</strong><small>{row.available} available · reorder {row.reorder_quantity}</small></div><div className="inline-control"><input className="compact-input" aria-label={`Reorder level for ${row.name}`} type="number" min="0" value={reorderLevels[key] ?? row.reorder_level} onChange={(event) => setReorderLevels((levels) => ({ ...levels, [key]: event.target.value }))} /><button className="text-button" disabled={!!busy} onClick={() => onReorderLevel({ product_id: row.product_id, warehouse_id: row.warehouse_id, reorder_level: Math.max(0, Number(reorderLevels[key] ?? row.reorder_level)) })}>Save</button></div></div>; })}</div> : <Empty>No low-stock products in this warehouse.</Empty>}
              <div className="inventory-table">{inventoryRows.map((row) => { const key = reorderKey(row); return <div className="simple-row inventory-row" key={key}><div><strong>{row.sku} · {row.name}</strong><small>{row.on_hand} on hand · {row.reserved} reserved · available {row.available}</small></div><div className="inline-control"><StatusPill value={row.low_stock ? "low stock" : "healthy"} /><input className="compact-input" aria-label={`Reorder level for ${row.name}`} type="number" min="0" value={reorderLevels[key] ?? row.reorder_level} onChange={(event) => setReorderLevels((levels) => ({ ...levels, [key]: event.target.value }))} /><button className="text-button" disabled={!!busy} onClick={() => onReorderLevel({ product_id: row.product_id, warehouse_id: row.warehouse_id, reorder_level: Math.max(0, Number(reorderLevels[key] ?? row.reorder_level)) })}>Save</button></div></div>; })}</div>
            </section>
          </div>

          <section className="panel operations-panel purchase-panel">
            <div className="panel-heading"><div><h3>Drafts, receipts, and closeout</h3></div><div className="inline-control"><select className="text-input compact-select" value={purchaseSupplier || defaultSupplier} onChange={(event) => setPurchaseSupplier(Number(event.target.value))}>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select><button className="action-button" disabled={!!busy || !suppliers.length} onClick={() => onCreatePurchase(purchaseSupplier || defaultSupplier)}>{busy === "purchase-create" ? "Creating…" : "New draft"}</button></div></div>
            {purchases.length ? <div className="purchase-list">{purchases.map((purchase) => {
              const draft = lineDraft(purchase);
              const receipt = receiptDraft(purchase);
              const receiptLines = Object.entries(receipt.quantities || {}).map(([lineId, quantity]) => ({ lineId: Number(lineId), quantity: Number(quantity) })).filter((line) => Number.isInteger(line.quantity) && line.quantity > 0);
              return <article className="purchase-card" key={purchase.id}>
                <div className="purchase-heading"><div><span className="eyebrow">{purchase.purchase_number}</span><h3>{purchase.supplier_name}</h3><small>{purchase.lines?.length || 0} lines · {money(purchase.total)}</small></div><StatusPill value={purchase.status} /></div>
                {purchase.lines?.length ? <div className="purchase-lines">{purchase.lines.map((line: Row) => <div className="purchase-line" key={line.id}><div><strong>{line.product_name}</strong><small>{line.warehouse_code} · {line.received_quantity} / {line.quantity} received · {money(line.unit_cost)} each</small></div>{["ordered", "partially_received"].includes(purchase.status) && <input className="compact-input" aria-label={`Receive ${line.product_name}`} type="number" min="0" max={purchase.status === "received" ? undefined : line.quantity} value={receipt.quantities?.[line.id] ?? ""} onChange={(event) => updateReceiptDraft(purchase.id, { ...receipt, quantities: { ...(receipt.quantities || {}), [line.id]: event.target.value } })} />}</div>)}</div> : <Empty>Add at least one line before ordering.</Empty>}
                {purchase.status === "draft" && <div className="purchase-form"><select className="text-input" value={draft.product_id} onChange={(event) => updateLineDraft(purchase.id, "product_id", Number(event.target.value))}>{activeProducts.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name}</option>)}</select><select className="text-input" value={draft.warehouse_id} onChange={(event) => updateLineDraft(purchase.id, "warehouse_id", Number(event.target.value))}>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.code}</option>)}</select><input className="text-input" type="number" min="1" value={draft.quantity} onChange={(event) => updateLineDraft(purchase.id, "quantity", event.target.value)} /><input className="text-input" type="number" min="0" step="0.01" value={draft.unit_cost} onChange={(event) => updateLineDraft(purchase.id, "unit_cost", event.target.value)} /><button className="action-button" disabled={!!busy || !activeProducts.length} onClick={() => onAddPurchaseLine(purchase.id, { product_id: Number(draft.product_id), warehouse_id: Number(draft.warehouse_id), quantity: Number(draft.quantity), unit_cost: Number(draft.unit_cost) })}>{busy === `purchase-line-${purchase.id}` ? "Adding…" : "Add line"}</button></div>}
                {purchase.status === "draft" && <button className="action-button primary" disabled={!!busy || !purchase.lines?.length} onClick={() => onChangePurchaseStatus(purchase.id, "order")}>{busy === `purchase-order-${purchase.id}` ? "Ordering…" : "Mark ordered"}</button>}
                {["ordered", "partially_received"].includes(purchase.status) && <div className="receipt-form"><label className="check-label"><input type="checkbox" checked={!!receipt.allow_over_receipt} onChange={(event) => updateReceiptDraft(purchase.id, { ...receipt, allow_over_receipt: event.target.checked })} /> Authorized over-receipt</label>{receipt.allow_over_receipt && <input className="text-input" value={receipt.override_reason || ""} onChange={(event) => updateReceiptDraft(purchase.id, { ...receipt, override_reason: event.target.value })} placeholder="Manager/admin reason" />}<button className="action-button primary" disabled={!!busy || !receiptLines.length || (receipt.allow_over_receipt && !receipt.override_reason?.trim())} onClick={() => onReceivePurchase(purchase.id, { lines: receiptLines.map((line) => { const source = purchase.lines.find((candidate: Row) => candidate.id === line.lineId); return { product_id: source.product_id, warehouse_id: source.warehouse_id, quantity: line.quantity }; }), allow_over_receipt: !!receipt.allow_over_receipt, override_reason: receipt.override_reason?.trim() || null })}>{busy === `purchase-receive-${purchase.id}` ? "Receiving…" : "Receive selected"}</button></div>}
                {purchase.status === "received" && <button className="action-button primary" disabled={!!busy} onClick={() => onChangePurchaseStatus(purchase.id, "close")}>{busy === `purchase-close-${purchase.id}` ? "Closing…" : "Close purchase"}</button>}
              </article>;
            })}</div> : <Empty>No purchases yet. Create a draft to begin.</Empty>}
          </section>

          <div className="operations-grid">
            <section className="panel"><h3>Tables</h3>{tableRows.length ? <div className="simple-list">{tableRows.map((table) => <div className="simple-row" key={table.id}><div><strong>{table.code}</strong><small>{table.name} · {table.seats} seats</small></div><StatusPill value={table.status} /></div>)}</div> : <Empty>No tables found.</Empty>}</section>
            <section className="panel"><h3>Receipts</h3>{receipts.length ? <div className="simple-list">{receipts.slice(0, 8).map((receipt) => <div className="simple-row" key={receipt.id}><div><strong>{receipt.receipt_number}</strong><small>{receipt.order_number} · {receipt.table_code}</small></div><strong>{money(receipt.total)}</strong></div>)}</div> : <Empty>No receipts yet.</Empty>}</section>
          </div>

          <TaxConfiguration configuration={taxConfiguration} saving={taxSaving} onSave={onSaveTaxRule} />
          <section className="panel audit-panel"><h3>Inventory and purchasing events</h3>{auditEvents.length ? <div className="simple-list">{auditEvents.slice(0, 12).map((event) => <div className="simple-row" key={event.id}><div><strong>{label(event.event_type)}</strong><small>{event.detail || "No detail"}</small></div><small>{event.created_at}</small></div>)}</div> : <Empty>No operational events yet.</Empty>}</section>
        </div>
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
