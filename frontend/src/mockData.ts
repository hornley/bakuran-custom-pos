export type MockRow = Record<string, any>;

export function isMockMode(): boolean {
  if (import.meta.env.VITE_MOCK_DATA === "true") return true;
  if (typeof window === "undefined") return false;
  const value = new URLSearchParams(window.location.search).get("mock");
  return value === "1" || value === "true";
}

type MockState = {
  nextOrderId: number;
  nextCustomerOrderId: number;
  nextAppliedPromotionId: number;
  orders: MockRow[];
  kitchen: MockRow[];
  payments: MockRow[];
  deliveries: MockRow[];
  inventory: MockRow[];
  purchases: MockRow[];
  receipts: MockRow[];
  taxConfiguration: MockRow;
  promotions: MockRow[];
};

const menu = [
  { id: 1, sku: "ADO-001", category_id: 1, category_code: "FOOD", category_name: "Mains", name: "Chicken adobo", description: "Slow-cooked · garlic rice", price: 185, active: 1 },
  { id: 2, sku: "LEC-001", category_id: 1, category_code: "FOOD", category_name: "Mains", name: "Lechon kawali", description: "Crispy pork · atchara", price: 245, active: 1 },
  { id: 3, sku: "LUM-001", category_id: 1, category_code: "FOOD", category_name: "Small plates", name: "Fresh lumpia", description: "Vegetables · peanut sauce", price: 125, active: 1 },
  { id: 4, sku: "HAL-001", category_id: 1, category_code: "FOOD", category_name: "Desserts", name: "Halo-halo", description: "Shaved ice · seasonal fruit", price: 145, active: 1 },
  { id: 5, sku: "CAL-001", category_id: 2, category_code: "DRINK", category_name: "Drinks", name: "Calamansi juice", description: "Fresh-squeezed · served cold", price: 85, active: 1 },
  { id: 6, sku: "COF-001", category_id: 2, category_code: "DRINK", category_name: "Drinks", name: "House coffee", description: "Locally roasted", price: 95, active: 1 },
];

const state: MockState = {
  nextOrderId: 105,
  nextCustomerOrderId: 501,
  nextAppliedPromotionId: 1,
  orders: [],
  kitchen: [],
  payments: [],
  deliveries: [],
  inventory: [],
  purchases: [],
  receipts: [],
  taxConfiguration: { rules: [], effective_rule: null },
  promotions: [],
};

const money = (value: number) => Number(value.toFixed(2));
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function promotionStatus(promotion: MockRow) {
  if (promotion.active === false) return "inactive";
  const today = new Date().toISOString().slice(0, 10);
  if (promotion.starts_on && today < promotion.starts_on) return "scheduled";
  if (promotion.ends_on && today > promotion.ends_on) return "expired";
  if (promotion.usage_limit != null && Number(promotion.usage_count || 0) >= Number(promotion.usage_limit)) return "exhausted";
  return "active";
}

function calculateMockTax(subtotal: number) {
  const rule = state.taxConfiguration.effective_rule;
  if (!rule) {
    return { policy: "none", rate: "0.00", name: "Tax", taxable_subtotal: money(subtotal), tax_amount: 0, total: money(subtotal) };
  }
  const rate = Number(rule.rate || 0);
  const total = rule.policy === "inclusive" ? money(subtotal) : money(subtotal + (subtotal * rate) / 100);
  const taxableSubtotal = rule.policy === "inclusive" ? money(subtotal / (1 + rate / 100)) : money(subtotal);
  const taxAmount = money(total - taxableSubtotal);
  return {
    policy: rule.policy,
    rate: String(rate.toFixed(2)),
    name: rule.name,
    tax_policy: rule.policy,
    tax_rate: String(rate.toFixed(2)),
    tax_name: rule.name,
    taxable_subtotal: taxableSubtotal,
    tax_amount: taxAmount,
    total,
  };
}

function promotionDiscount(promotion: MockRow, subtotal: number) {
  const value = Number(promotion.value || 0);
  const discount = promotion.discount_type === "percentage" || promotion.type === "percentage"
    ? (subtotal * value) / 100
    : value;
  return money(Math.min(Math.max(discount, 0), subtotal));
}

function recalculateMockOrder(order: MockRow) {
  const originalSubtotal = money((order.lines || []).reduce(
    (sum: number, line: MockRow) => sum + Number(line.line_total || 0),
    0,
  ));
  const discountAmount = order.promotion ? promotionDiscount(order.promotion, originalSubtotal) : 0;
  const discountedSubtotal = money(Math.max(originalSubtotal - discountAmount, 0));
  const shouldCalculateTax = order.status === "awaiting_payment";
  const tax = shouldCalculateTax ? calculateMockTax(discountedSubtotal) : {
    policy: "none",
    rate: "0.00",
    name: "Tax",
    taxable_subtotal: discountedSubtotal,
    tax_amount: 0,
    total: discountedSubtotal,
  };
  Object.assign(order, {
    subtotal: originalSubtotal,
    original_subtotal: originalSubtotal,
    discount_amount: discountAmount,
    discounted_subtotal: discountedSubtotal,
    ...tax,
  });
  order.total = tax.total;
}

function orderView(order: MockRow): MockRow {
  const value = clone(order);
  const lines = value.lines || [];
  const subtotal = value.subtotal ?? lines.reduce((sum: number, line: MockRow) => sum + Number(line.line_total || 0), 0);
  value.subtotal = subtotal;
  value.original_subtotal = value.original_subtotal ?? subtotal;
  value.discount_amount = value.discount_amount ?? 0;
  value.discounted_subtotal = value.discounted_subtotal ?? money(Number(value.original_subtotal) - Number(value.discount_amount));
  value.tax = value.tax || {
    policy: value.tax_policy || "none",
    rate: value.tax_rate || "0.00",
    name: value.tax_name || "Tax",
    taxable_subtotal: value.taxable_subtotal ?? subtotal,
    tax_amount: value.tax_amount ?? 0,
    total: value.total ?? subtotal,
  };
  value.tax_policy = value.tax.policy;
  value.tax_rate = value.tax.rate;
  value.tax_name = value.tax.name;
  value.tax_amount = value.tax.tax_amount;
  value.taxable_subtotal = value.tax.taxable_subtotal;
  const ticket = state.kitchen.find((candidate) => candidate.order_id === value.id) || value.ticket || null;
  const delivery = state.deliveries.find((candidate) => candidate.order_id === value.id) || value.delivery || null;
  if (value.promotion) delete value.promotion.idempotency_key;
  delete value.promotion_remove_key;
  return {
    order: value,
    lines: clone(lines),
    ticket: clone(ticket),
    payment: clone(value.payment || null),
    receipt: clone(value.receipt || null),
    delivery: clone(delivery),
    tax: clone(value.tax),
    promotion: clone(value.promotion || null),
    pricing: {
      original_subtotal: value.original_subtotal,
      discount_amount: value.discount_amount,
      discounted_subtotal: value.discounted_subtotal,
      total: value.total,
    },
  };
}

function seedOrders() {
  const orders = [
    { id: 101, order_number: "ORD-0101", status: "paid", order_channel: "counter", customer_name: "Maria", table_code: "COUNTER", total: 430, lines: [{ id: 1, item_name: "Chicken adobo", quantity: 1, unit_price: 185, line_total: 185 }, { id: 2, item_name: "Lechon kawali", quantity: 1, unit_price: 245, line_total: 245 }] },
    { id: 102, order_number: "ORD-0102", status: "paid", order_channel: "counter", customer_name: "Paolo", table_code: "COUNTER", total: 330, lines: [{ id: 3, item_name: "Lechon kawali", quantity: 1, unit_price: 245, line_total: 245 }, { id: 4, item_name: "Calamansi juice", quantity: 1, unit_price: 85, line_total: 85 }] },
    { id: 103, order_number: "QR-0018", status: "awaiting_payment", order_channel: "qr", customer_name: "Liza", table_code: "T04", subtotal: 305, taxable_subtotal: 305, tax_amount: 36.6, tax_rate: "12.00", tax_policy: "exclusive", tax_name: "VAT", total: 341.6, lines: [{ id: 5, item_name: "Fresh lumpia", quantity: 1, unit_price: 125, line_total: 125 }, { id: 6, item_name: "Calamansi juice", quantity: 1, unit_price: 85, line_total: 85 }, { id: 7, item_name: "House coffee", quantity: 1, unit_price: 95, line_total: 95 }] },
    { id: 104, order_number: "QR-0019", status: "awaiting_payment", order_channel: "qr", customer_name: "Nico", table_code: "T02", subtotal: 415, taxable_subtotal: 415, tax_amount: 49.8, tax_rate: "12.00", tax_policy: "exclusive", tax_name: "VAT", total: 464.8, lines: [{ id: 8, item_name: "Chicken adobo", quantity: 1, unit_price: 185, line_total: 185 }, { id: 9, item_name: "Halo-halo", quantity: 1, unit_price: 145, line_total: 145 }, { id: 10, item_name: "Calamansi juice", quantity: 1, unit_price: 85, line_total: 85 }] },
    { id: 98, order_number: "ORD-0098", status: "served", order_channel: "counter", customer_name: "Nico", table_code: "T03", subtotal: 145, total: 145, lines: [{ id: 11, item_name: "Halo-halo", quantity: 1, unit_price: 145, line_total: 145 }] },
    { id: 99, order_number: "ORD-0099", status: "paid", order_channel: "counter", customer_name: "Ari", table_code: "T02", subtotal: 210, total: 210, lines: [{ id: 12, item_name: "Fresh lumpia", quantity: 1, unit_price: 125, line_total: 125 }, { id: 13, item_name: "Calamansi juice", quantity: 1, unit_price: 85, line_total: 85 }] },
  ];
  state.orders = orders;
  state.payments = orders.filter((order) => order.order_channel === "qr");
  state.kitchen = [
    { id: 1, order_id: 101, order_number: "ORD-0101", customer_name: "Maria", table_code: "COUNTER", ticket_number: "KIT-0101", status: "preparing" },
    { id: 2, order_id: 102, order_number: "ORD-0102", customer_name: "Paolo", table_code: "COUNTER", ticket_number: "KIT-0102", status: "queued" },
    { id: 3, order_id: 99, order_number: "ORD-0099", customer_name: "Ari", table_code: "T02", ticket_number: "KIT-0099", status: "ready" },
    { id: 4, order_id: 98, order_number: "ORD-0098", customer_name: "Nico", table_code: "T03", ticket_number: "KIT-0098", status: "served" },
  ];
  state.deliveries = [
    { id: 1, order_id: 97, order_number: "DL-0007", contact_name: "Mika", customer_name: "Mika", address: "12 Mabini Street, Cebu City", contact: "0917 123 4567", order_total: 620, status: "pending", paid: true, assignments: [], driver: null },
    { id: 2, order_id: 96, order_number: "DL-0006", contact_name: "Carlo", customer_name: "Carlo", address: "88 Rizal Avenue, Cebu City", contact: "0917 765 4321", order_total: 480, status: "out_for_delivery", paid: true, assignments: [{ id: 1, driver_name: "Ari Santos", status: "active" }], driver: { name: "Ari Santos" } },
  ];
  state.inventory = menu.map((item, index) => ({ product_id: item.id, sku: item.sku, name: item.name, warehouse_id: 1, on_hand: index === 1 ? 3 : 18 - index, reserved: 0, available: index === 1 ? 3 : 18 - index, reorder_level: 5, low_stock: index === 1, reorder_quantity: index === 1 ? 2 : 0 }));
  state.purchases = [{ id: 1, purchase_number: "PUR-0004", supplier_name: "Local Food Supply", status: "ordered", total: 2450, lines: [{ id: 1, product_id: 1, warehouse_id: 1, product_name: "Chicken adobo", warehouse_code: "MAIN", received_quantity: 4, quantity: 10, unit_cost: 185 }] }];
  state.receipts = [{ id: 1, receipt_number: "REC-0100", order_number: "ORD-0100", table_code: "COUNTER", total: 430 }];
  state.taxConfiguration = { rules: [{ id: 1, name: "VAT", rate: "12.00", policy: "exclusive", effective_from: "2026-01-01" }], effective_rule: { id: 1, name: "VAT", rate: "12.00", policy: "exclusive" } };
  state.promotions = [
    { id: 1, code: "WELCOME20", name: "Welcome 20", discount_type: "percentage", value: "20.00", status: "active", active: true, can_apply: true, usage_count: 0, remaining_uses: null },
    { id: 2, code: "SAVE50", name: "Save ₱50", discount_type: "fixed", value: "50.00", status: "active", active: true, can_apply: true, usage_count: 0, remaining_uses: null },
  ];
}

export function resetMockData() {
  state.nextOrderId = 105;
  state.nextCustomerOrderId = 501;
  state.nextAppliedPromotionId = 1;
  seedOrders();
}

function newCounterOrder(channel = "counter") {
  const id = state.nextOrderId++;
  const order = { id, order_number: `ORD-${String(id).padStart(4, "0")}`, status: "open", order_channel: channel, customer_name: "", table_code: "COUNTER", subtotal: 0, original_subtotal: 0, discount_amount: 0, discounted_subtotal: 0, total: 0, promotion: null, lines: [] as MockRow[] };
  state.orders.unshift(order);
  return order;
}

function findOrder(id: number) {
  return state.orders.find((order) => order.id === id);
}

function parseJson(options?: RequestInit): MockRow {
  try { return JSON.parse(String(options?.body || "{}")) as MockRow; } catch { return {}; }
}

export async function mockApi<T = any>(path: string, options?: RequestInit): Promise<T> {
  const [pathname, query = ""] = path.split("?");
  const params = new URLSearchParams(query);
  const method = String(options?.method || "GET").toUpperCase();
  if (pathname === "/api/promotions") {
    if (method === "GET") return clone(state.promotions) as T;
    throw new Error(`Unknown mock mutation: ${method} ${pathname}`);
  }
  if ((pathname === "/api/menu" || pathname === "/api/catalog") && method === "GET") return clone(menu) as T;
  if (pathname === "/api/kitchen") return clone(params.get("queue") === "ready" ? state.kitchen.filter((ticket) => ["ready", "served"].includes(ticket.status)) : state.kitchen.filter((ticket) => ticket.status !== "served")) as T;
  if (pathname === "/api/payment-queue") {
    const search = params.get("q")?.toLowerCase() || "";
    return clone(state.payments.filter((order) => order.status === "awaiting_payment" && (!search || `${order.order_number} ${order.customer_name} ${order.table_code}`.toLowerCase().includes(search)))) as T;
  }
  if (pathname === "/api/delivery") return clone(state.deliveries.filter((delivery) => delivery.paid !== false)) as T;
  if (pathname === "/api/delivery/drivers") return clone([{ id: 1, name: "Ari Santos" }, { id: 2, name: "Ben Cruz" }]) as T;
  if (pathname === "/api/tables") return clone([{ id: 1, code: "T01", name: "Table 1", seats: 2, status: "available" }, { id: 2, code: "T02", name: "Table 2", seats: 4, status: "occupied" }, { id: 3, code: "T03", name: "Table 3", seats: 4, status: "available" }]) as T;
  if (pathname === "/api/warehouses") return clone([{ id: 1, code: "MAIN", name: "Main Warehouse" }]) as T;
  if (pathname === "/api/suppliers") return clone([{ id: 1, code: "SUP-001", name: "Local Food Supply", active: 1 }]) as T;
  if (pathname === "/api/receipts") return clone(state.receipts) as T;
  if (pathname === "/api/audit-events") return clone([{ id: 1, event_type: "payment.recorded", detail: "Cash payment received", created_at: "Today" }]) as T;
  if (pathname === "/api/tax/configuration" && (!options?.method || options.method === "GET")) return clone(state.taxConfiguration) as T;
  if (pathname === "/api/inventory") return clone({ products: state.inventory, movements: [] }) as T;
  if (pathname === "/api/stock/adjustment" && options?.method === "POST") {
    const payload = parseJson(options);
    const product = state.inventory.find((candidate) => candidate.product_id === Number(payload.product_id) && candidate.warehouse_id === Number(payload.warehouse_id || 1));
    if (!product) throw new Error("Inventory product not found");
    const quantity = Number(payload.quantity || 0);
    product.on_hand += quantity;
    product.available = product.on_hand - product.reserved;
    product.low_stock = product.available <= product.reorder_level;
    product.reorder_quantity = Math.max(product.reorder_level - product.available, 0);
    return clone({ product, movement: { quantity, reason: payload.reason } }) as T;
  }
  if (pathname === "/api/inventory/reorder-level" && options?.method === "PUT") {
    const payload = parseJson(options);
    const product = state.inventory.find((candidate) => candidate.product_id === Number(payload.product_id) && candidate.warehouse_id === Number(payload.warehouse_id || 1));
    if (!product) throw new Error("Inventory product not found");
    product.reorder_level = Math.max(0, Number(payload.reorder_level || 0));
    product.low_stock = product.available <= product.reorder_level;
    product.reorder_quantity = Math.max(product.reorder_level - product.available, 0);
    return clone({ product }) as T;
  }
  if (pathname === "/api/purchases" && (!options?.method || options.method === "GET")) return clone(state.purchases) as T;
  if (pathname === "/api/tax/configuration" && options?.method === "POST") {
    const payload = parseJson(options);
    const nextRule = { id: (state.taxConfiguration.rules?.length || 0) + 1, ...payload, rate: String(payload.rate), policy: payload.policy || "exclusive" };
    state.taxConfiguration = { rules: [nextRule, ...(state.taxConfiguration.rules || [])], effective_rule: nextRule };
    return clone(nextRule) as T;
  }
  if (pathname === "/api/purchases" && options?.method === "POST") {
    const id = state.purchases.length + 1;
    const purchase = { id, purchase_number: `PUR-${String(id).padStart(4, "0")}`, supplier_name: "Local Food Supply", supplier_id: parseJson(options).supplier_id, status: "draft", total: 0, lines: [] };
    state.purchases.unshift(purchase);
    return clone(purchase) as T;
  }
  const purchaseLineMatch = pathname.match(/^\/api\/purchases\/(\d+)\/lines$/);
  if (purchaseLineMatch && options?.method === "POST") {
    const purchase = state.purchases.find((candidate) => candidate.id === Number(purchaseLineMatch[1]));
    if (!purchase) throw new Error("Purchase not found");
    const payload = parseJson(options);
    const item = menu.find((candidate) => candidate.id === Number(payload.product_id)) || menu[0];
    purchase.lines.push({ id: Date.now(), product_id: item.id, warehouse_id: payload.warehouse_id || 1, product_name: item.name, warehouse_code: "MAIN", received_quantity: 0, quantity: Number(payload.quantity || 1), unit_cost: Number(payload.unit_cost || item.price) });
    purchase.total = purchase.lines.reduce((sum: number, line: MockRow) => sum + line.quantity * line.unit_cost, 0);
    return clone(purchase) as T;
  }
  const purchaseActionMatch = pathname.match(/^\/api\/purchases\/(\d+)\/(order|receive|close)$/);
  if (purchaseActionMatch && options?.method === "POST") {
    const purchase = state.purchases.find((candidate) => candidate.id === Number(purchaseActionMatch[1]));
    if (!purchase) throw new Error("Purchase not found");
    const action = purchaseActionMatch[2];
    if (action === "order") purchase.status = "ordered";
    if (action === "receive") {
      const payload = parseJson(options);
      for (const received of payload.lines || []) {
        const line = purchase.lines.find((candidate: MockRow) => candidate.product_id === received.product_id);
        if (line) line.received_quantity += Number(received.quantity || 0);
      }
      purchase.status = purchase.lines.length && purchase.lines.every((line: MockRow) => line.received_quantity >= line.quantity) ? "received" : "partially_received";
    }
    if (action === "close") purchase.status = "closed";
    return clone(purchase) as T;
  }
  const deliveryMutationMatch = pathname.match(/^\/api\/delivery\/(\d+)\/(assign|out-for-delivery|delivered|failed|cancel)$/);
  if (deliveryMutationMatch && options?.method === "POST") {
    const delivery = state.deliveries.find((candidate) => candidate.id === Number(deliveryMutationMatch[1]));
    if (!delivery) throw new Error("Delivery not found");
    const action = deliveryMutationMatch[2];
    const payload = parseJson(options);
    if (action === "assign") {
      const driver = [{ id: 1, name: "Ari Santos" }, { id: 2, name: "Ben Cruz" }].find((candidate) => candidate.id === Number(payload.driver_id));
      delivery.driver = driver || null;
      delivery.driver_id = driver?.id;
      delivery.status = "assigned";
      delivery.assignments = [{ id: Date.now(), driver_name: driver?.name || "Driver", status: "active" }];
    } else if (action === "out-for-delivery") delivery.status = "out_for_delivery";
    else if (action === "delivered") delivery.status = "delivered";
    else if (action === "failed") delivery.status = "failed";
    else if (action === "cancel") delivery.status = "cancelled";
    return clone(delivery) as T;
  }
  const deliveryMetadataMatch = pathname.match(/^\/api\/orders\/(\d+)\/delivery$/);
  if (deliveryMetadataMatch && options?.method === "POST") {
    const order = findOrder(Number(deliveryMetadataMatch[1]));
    if (!order) throw new Error("Order not found");
    if (order.order_channel !== "delivery") throw new Error("Only delivery orders can have delivery metadata");
    const payload = parseJson(options);
    const existing = state.deliveries.find((candidate) => candidate.order_id === order.id);
    const delivery = existing || { id: state.deliveries.reduce((max, candidate) => Math.max(max, Number(candidate.id)), 0) + 1, order_id: order.id, order_number: order.order_number, status: "pending", assignments: [], driver: null, paid: false };
    Object.assign(delivery, {
      contact_name: payload.contact_name || "",
      customer_name: order.customer_name,
      address: payload.address || "",
      contact: payload.contact || "",
      order_total: order.total,
    });
    if (!existing) state.deliveries.push(delivery);
    return clone(orderView(order)) as T;
  }
  if (/^\/api\/customer\/tables\/[^/]+$/.test(pathname)) return clone({ table: { id: 6, code: "T06", name: "Table 6", seats: 4 }, session: { id: 6, session_number: "SES-0006", status: "open" }, menu }) as T;
  if (/^\/api\/customer\/tables\/[^/]+\/orders$/.test(pathname) && options?.method === "POST") {
    const payload = parseJson(options);
    const lines = (payload.lines || []).map((line: MockRow, index: number) => { const item = menu.find((entry) => entry.id === line.menu_item_id) || menu[0]; return { id: index + 1, menu_item_id: item.id, item_name: item.name, quantity: line.quantity, unit_price: item.price, line_total: item.price * line.quantity }; });
    const subtotal = lines.reduce((sum: number, line: MockRow) => sum + line.line_total, 0);
    const tax = calculateMockTax(subtotal);
    const order = { id: state.nextCustomerOrderId++, order_number: `QR-${String(state.nextCustomerOrderId - 1).padStart(4, "0")}`, status: "awaiting_payment", customer_name: payload.customer_name, table_code: "T06", order_channel: "qr", subtotal, ...tax, lines };
    state.orders.unshift(order);
    state.payments.unshift(order);
    return clone({ order, lines, table: { table_code: "T06", table_name: "Table 6" } }) as T;
  }
  if (pathname === "/api/counter/orders" && options?.method === "POST") return clone(orderView(newCounterOrder(parseJson(options).order_channel || "counter"))) as T;
  const promotionApplyMatch = pathname.match(/^\/api\/orders\/(\d+)\/promotions$/);
  if (promotionApplyMatch && method === "POST") {
    const order = findOrder(Number(promotionApplyMatch[1]));
    if (!order) throw new Error("Order not found");
    if (!Object.keys(options?.headers || {}).some((key) => key.toLowerCase() === "idempotency-key")) throw new Error("Idempotency-Key is required");
    if (!["manual", "counter", "delivery"].includes(String(order.order_channel || "counter"))) throw new Error("Promotions are unavailable for this order");
    const payload = parseJson(options);
    const code = String(payload.code || "").trim().toUpperCase();
    const idempotencyKey = Object.entries(options?.headers || {}).find(([key]) => key.toLowerCase() === "idempotency-key")?.[1];
    const fingerprint = JSON.stringify({ code });
    if (order.promotion?.idempotency_key === idempotencyKey) {
      if (order.promotion.idempotency_fingerprint !== fingerprint) throw new Error("Idempotency-Key was already used with a different request");
      return clone(orderView(order)) as T;
    }
    if (!["open", "awaiting_payment"].includes(String(order.status || "open"))) throw new Error("Promotion cannot be changed after payment or release");
    const promotion = state.promotions.find((candidate) => candidate.code === code);
    if (!promotion) throw new Error("Promotion code is not available");
    if (promotionStatus(promotion) !== "active") throw new Error("Promotion code is not available");
    if (order.promotion && order.promotion.code === code) return clone(orderView(order)) as T;
    if (order.promotion) {
      const previous = state.promotions.find((candidate) => candidate.code === order.promotion.code);
      if (previous) previous.usage_count = Math.max(Number(previous.usage_count || 0) - 1, 0);
    }
    const applied = {
      ...clone(promotion),
      id: state.nextAppliedPromotionId++,
      applied_id: state.nextAppliedPromotionId - 1,
      idempotency_key: idempotencyKey,
      idempotency_fingerprint: fingerprint,
      discount_amount: promotionDiscount(promotion, Number(order.subtotal || 0)),
      discounted_subtotal: money(Math.max(Number(order.subtotal || 0) - promotionDiscount(promotion, Number(order.subtotal || 0)), 0)),
    };
    order.promotion = applied;
    promotion.usage_count = Number(promotion.usage_count || 0) + 1;
    recalculateMockOrder(order);
    order.promotion = { ...applied, discount_amount: order.discount_amount, discounted_subtotal: order.discounted_subtotal };
    return clone(orderView(order)) as T;
  }
  const promotionRemoveMatch = pathname.match(/^\/api\/orders\/(\d+)\/promotions\/(\d+)$/);
  if (promotionRemoveMatch && method === "DELETE") {
    const order = findOrder(Number(promotionRemoveMatch[1]));
    if (!order) throw new Error("Order not found");
    if (!Object.keys(options?.headers || {}).some((key) => key.toLowerCase() === "idempotency-key")) throw new Error("Idempotency-Key is required");
    const idempotencyKey = Object.entries(options?.headers || {}).find(([key]) => key.toLowerCase() === "idempotency-key")?.[1];
    if (!order.promotion && order.promotion_remove_key === idempotencyKey) return clone(orderView(order)) as T;
    if (!["open", "awaiting_payment"].includes(String(order.status || "open"))) throw new Error("Promotion cannot be changed after payment or release");
    if (!order.promotion || ![Number(promotionRemoveMatch[2]), Number(order.promotion.applied_id)].includes(Number(order.promotion.id))) throw new Error("Applied promotion not found");
    const previousCode = order.promotion.code;
    order.promotion = null;
    order.promotion_remove_key = idempotencyKey;
    const previous = state.promotions.find((candidate) => candidate.code === previousCode);
    if (previous) previous.usage_count = Math.max(Number(previous.usage_count || 0) - 1, 0);
    recalculateMockOrder(order);
    return clone(orderView(order)) as T;
  }
  const kitchenMatch = pathname.match(/^\/api\/kitchen\/(\d+)\/(start|ready|serve)$/);
  if (kitchenMatch && options?.method === "POST") {
    const ticket = state.kitchen.find((candidate) => candidate.id === Number(kitchenMatch[1]));
    if (!ticket) throw new Error("Kitchen ticket not found");
    ticket.status = kitchenMatch[2] === "start" ? "preparing" : kitchenMatch[2] === "ready" ? "ready" : "served";
    const order = findOrder(ticket.order_id);
    if (order && ticket.status === "served") order.status = "served";
    return clone(ticket) as T;
  }
  const orderMatch = pathname.match(/^\/api\/orders\/(\d+)(?:\/(lines|confirm|pay))?$/);
  if (orderMatch) {
    const order = findOrder(Number(orderMatch[1]));
    if (!order) throw new Error("Order not found");
    const action = orderMatch[2];
    if (!action) return clone(orderView(order)) as T;
    if (action === "lines") {
      const payload = parseJson(options);
      const item = menu.find((entry) => entry.id === payload.menu_item_id) || menu[0];
      const quantity = Number(payload.quantity || 1);
      const existing = order.lines.find((line: MockRow) => line.menu_item_id === item.id);
      if (existing) {
        existing.quantity += quantity;
        existing.line_total = item.price * existing.quantity;
      } else {
        order.lines.push({ id: Date.now(), menu_item_id: item.id, item_name: item.name, quantity, unit_price: item.price, line_total: item.price * quantity });
      }
      recalculateMockOrder(order);
      return clone(orderView(order)) as T;
    }
    if (action === "confirm") {
      order.customer_name = parseJson(options).customer_name;
      Object.assign(order, { status: "awaiting_payment" });
      recalculateMockOrder(order);
      const pendingDelivery = state.deliveries.find((candidate) => candidate.order_id === order.id);
      if (pendingDelivery) Object.assign(pendingDelivery, { customer_name: order.customer_name, order_total: order.total });
      return clone(orderView(order)) as T;
    }
    order.status = "paid";
    order.payment = { method: "cash", status: "paid" };
    const delivery = state.deliveries.find((candidate) => candidate.order_id === order.id);
    if (delivery) { delivery.paid = true; delivery.order_total = order.total; }
    const payment = state.payments.find((candidate) => candidate.id === order.id);
    if (payment) Object.assign(payment, order);
    order.ticket = { id: Date.now(), status: "queued" };
    state.kitchen.unshift({ ...order.ticket, order_id: order.id, order_number: order.order_number, customer_name: order.customer_name, table_code: order.table_code, ticket_number: `KIT-${order.id}` });
    return clone(orderView(order)) as T;
  }
  const closeMatch = pathname.match(/^\/api\/orders\/(\d+)\/close$/);
  if (closeMatch && options?.method === "POST") {
    const order = findOrder(Number(closeMatch[1]));
    if (!order) throw new Error("Order not found");
    order.status = "closed";
    order.receipt = { receipt_number: `REC-${String(order.id).padStart(4, "0")}`, total: order.total };
    state.receipts.unshift({ id: order.id, receipt_number: order.receipt.receipt_number, order_number: order.order_number, table_code: order.table_code, total: order.total });
    return clone(orderView(order)) as T;
  }
  if (method !== "GET") throw new Error(`Unknown mock mutation: ${method} ${pathname}`);
  return clone([]) as T;
}

resetMockData();
