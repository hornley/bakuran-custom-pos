import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { resolveApiBase } from "./App";


type Row = Record<string, any>;

const menu = [{ id: 1, name: "Adobo", category_name: "Mains", description: "Savory", price: 12 }];
const order = { id: 7, order_number: "BK-007", status: "open", total: 12, customer_name: "", lines: [] };

function response(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

async function settle() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

function button(container: HTMLElement, text: string) {
  return (Array.from(container.querySelectorAll("button")) as HTMLButtonElement[]).find((item) => item.textContent?.includes(text))!;
}

async function renderApp(fetchMock: typeof fetch) {
  vi.stubGlobal("fetch", fetchMock);
  const container = document.createElement("div");
  document.body.appendChild(container);
  let root!: Root;
  await act(async () => { root = createRoot(container); root.render(<App />); });
  await settle();
  return { container, root };
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => response(menu)));
});

describe("counter operational flows", () => {
  it("derives the API host from the served operator hostname", () => {
    expect(resolveApiBase({ protocol: "http:", hostname: "100.108.61.26" })).toBe("http://100.108.61.26:5300");
  });

  it("starts a fresh counter order when New order is selected again", async () => {
    let createdOrders = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) {
        createdOrders += 1;
        return response({ order: { ...order, id: createdOrders, order_number: `BK-00${createdOrders}`, status: createdOrders === 1 ? "paid" : "open" }, lines: [] });
      }
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => button(container, "Start order").click());
    await settle();
    expect(createdOrders).toBe(1);

    await act(async () => button(container, "New order").click());
    await settle();
    expect(createdOrders).toBe(2);
    await act(async () => root.unmount());
  });

  it("renders the premium operator shell with explicit service states", async () => {
    const fetchMock = vi.fn((url: string) => response(url.endsWith("/api/menu") ? menu : []));
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    expect(container.querySelector(".operator-shell")).toBeTruthy();
    expect(container.querySelector(".operator-rail")).toBeTruthy();
    expect(container.querySelector(".service-strip")).toBeTruthy();
    expect(container.textContent).toContain("Overview");

    expect(container.textContent).toContain("Front desk");
    expect(container.textContent).toContain("Cash gate");
    expect(button(container, "New order")).toBeTruthy();
    expect(container.querySelector('[aria-label="Bakuran operations"]')).toBeTruthy();
    await act(async () => root.unmount());
  });

  it("requests the ready kitchen queue when Ready is opened", async () => {
    const fetchMock = vi.fn((url: string) => response(url.endsWith("/api/menu") ? menu : []));
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => { button(container, "Ready").click(); });
    await settle();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/kitchen?queue=ready", expect.objectContaining({ credentials: "include" }));
    await act(async () => root.unmount());
  });

  it("keeps the operator shell ready for touch interaction", async () => {
    const fetchMock = vi.fn((url: string) => response(url.endsWith("/api/menu") ? menu : []));
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    expect(container.querySelector(".rail-link")).toBeTruthy();
    expect(container.querySelector(".service-strip")).toBeTruthy();
    expect(container.querySelector(".action-button")).toBeTruthy();
    await act(async () => root.unmount());
  });

  it("opens a kitchen attention row using its order id", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/kitchen")) return response([{ id: 44, order_id: 7, order_number: "BK-007", customer_name: "Mika", table_code: "COUNTER", ticket_number: "KIT-0044", status: "preparing" }]);
      if (url.endsWith("/api/kitchen?queue=ready")) return response([]);
      if (url.endsWith("/api/payment-queue")) return response([]);
      if (url.endsWith("/api/orders/7")) return response({ order: { ...order, id: 7, status: "paid", order_channel: "counter" }, lines: [], ticket: { id: 44, order_id: 7, status: "preparing" } });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => { button(container, "Open").click(); });
    await settle();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/orders/7", expect.objectContaining({ credentials: "include" }));
    expect(fetchMock).not.toHaveBeenCalledWith("http://localhost:5300/api/orders/44", expect.anything());
    await act(async () => root.unmount());
  });

  it("keeps payment gated until an order has items, then advances after successful payment", async () => {
    const calls: string[] = [];
    const line = { id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 };
    const openOrder = { ...order, status: "open", lines: [] };
    const orderWithItems = { ...openOrder, total: 12, lines: [line] };
    const awaitingPaymentOrder = { ...orderWithItems, status: "awaiting_payment", customer_name: "Mika" };
    const paidOrder = { ...awaitingPaymentOrder, status: "paid", ticket: { id: 3, status: "queued" } };
    const paymentRequests: RequestInit[] = [];
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      calls.push(`${options?.method || "GET"} ${url}`);
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order: openOrder, lines: [] });
      if (url.endsWith("/lines")) return response({ order: orderWithItems, lines: orderWithItems.lines });
      if (url.endsWith("/confirm")) return response({ order: awaitingPaymentOrder, lines: awaitingPaymentOrder.lines });
      if (url.endsWith("/pay")) {
        paymentRequests.push(options || {});
        return response({ order: paidOrder, lines: paidOrder.lines, ticket: paidOrder.ticket });
      }
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    expect(button(container, "Start order")).toBeTruthy();
    await act(async () => button(container, "Start order").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    await act(async () => container.querySelector<HTMLButtonElement>(".basket-actions button")!.click());
    await settle();
    expect(calls.some((call) => call.includes("POST http://localhost:5300/api/orders/7/pay"))).toBe(false);
    const name = container.querySelector<HTMLInputElement>("#customer-name")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => {
      setInputValue?.call(name, "Mika");
      name.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => button(container, "Continue to payment").click());
    await settle();
    expect(calls.some((call) => call.includes("POST http://localhost:5300/api/orders/7/pay"))).toBe(false);
    expect(button(container, "Record cash payment")).toBeTruthy();
    await act(async () => button(container, "Record cash payment").click());
    await settle();

    expect(paymentRequests).toHaveLength(1);
    expect(JSON.parse(String(paymentRequests[0].body))).toEqual({ amount: "12", method: "cash" });
    expect(container.textContent).toContain("Order is moving.");
    await act(async () => root.unmount());
  });

  it("preserves default and idempotency headers for delivery mutations", async () => {
    Object.defineProperty(document, "cookie", { configurable: true, value: "local_csrf=test-token" });
    const delivery = {
      id: 7,
      order_number: "ORD-0007",
      contact_name: "Mika",
      customer_name: "Mika",
      address: "12 Mabini Street, Cebu City",
      contact: "09171234567",
      order_total: 18,
      status: "assigned",
      driver_id: 1,
      driver: { name: "Ari Santos" },
      assignments: [{ id: 1, driver_name: "Ari Santos", status: "active" }],
    };
    const requests: Array<{ url: string; options?: RequestInit }> = [];
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      requests.push({ url, options });
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/delivery")) return response([delivery]);
      if (url.endsWith("/api/delivery/drivers")) return response([{ id: 1, name: "Ari Santos" }]);
      return response(url.endsWith("/out-for-delivery") ? {} : [delivery]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => { button(container, "Delivery").click(); });
    await settle();
    await act(async () => { button(container, "Out for delivery").click(); });
    await settle();

    const mutation = requests.find(({ url }) => url.endsWith("/api/delivery/7/out-for-delivery"));
    expect(mutation?.options).toEqual(expect.objectContaining({
      credentials: "include",
      headers: {
        "X-CSRF-Token": "test-token",
        "Content-Type": "application/json",
        "Idempotency-Key": "desk-out-for-delivery-7-",
      },
    }));
    await act(async () => root.unmount());
    Object.defineProperty(document, "cookie", { configurable: true, value: "" });
  });

  it("shows a recoverable API error without losing the order UI", async () => {
    let fail = true;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/lines") && fail) { fail = false; return response({ detail: "Kitchen temporarily unavailable" }, false); }
      if (url.endsWith("/lines")) return response({ order: { ...order, lines: [{ item_name: "Adobo", quantity: 1, unit_price: 12 }] }, lines: [{ item_name: "Adobo", quantity: 1, unit_price: 12 }] });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => button(container, "Start order").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    expect(container.textContent).toContain("Kitchen temporarily unavailable");
    expect(container.textContent).toContain("Choose items");
    await act(async () => root.unmount());
  });

  it("renders the server tax breakdown in the confirmation step", async () => {
    const line = { id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 };
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order: { ...order }, lines: [] });
      if (url.endsWith("/lines")) return response({ order: { ...order, total: 12 }, lines: [line] });
      if (url.endsWith("/confirm")) return response({ order: { ...order, total: 13.2, customer_name: "Mika", status: "awaiting_payment", tax_policy: "exclusive", tax_rate: "10.00", tax_name: "VAT", taxable_subtotal: "12.00", tax_amount: "1.20" }, lines: [line], tax: { policy: "exclusive", rate: "10.00", name: "VAT", taxable_subtotal: "12.00", tax_amount: "1.20", total: "13.20" } });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => button(container, "Start order").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    await act(async () => container.querySelector<HTMLButtonElement>(".basket-actions button")!.click());
    await settle();
    const name = container.querySelector<HTMLInputElement>("#customer-name")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => { setInputValue?.call(name, "Mika"); name.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Continue to payment").click());
    await settle();
    expect(container.textContent).toContain("VAT (10.00%)");
    expect(container.textContent).toContain("₱1.20");
    expect(container.textContent).toContain("₱13.20");
    await act(async () => root.unmount());
  });

  it("loads tax configuration and inventory purchasing as secondary operations", async () => {
    const purchase = {
      id: 5,
      purchase_number: "PUR-0005",
      supplier_name: "Local Supply",
      status: "ordered",
      total: 80,
      lines: [{ id: 9, product_id: 1, warehouse_id: 1, product_name: "Adobo", warehouse_code: "MAIN", received_quantity: 0, quantity: 10, unit_cost: 8 }],
    };
    const configuration = { rules: [], effective_rule: null };
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === "POST" && url.endsWith("/api/tax/configuration")) return response({ id: 1 });
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/warehouses") || url.endsWith("/api/audit-events")) return response([]);
      if (url.endsWith("/api/tax/configuration")) return response(configuration);
      if (url.endsWith("/api/catalog")) return response(menu.map((item) => ({ ...item, sku: "ADO-001", active: 1 })));
      if (url.endsWith("/api/inventory?warehouse_id=1")) return response({ products: [], movements: [] });
      if (url.endsWith("/api/purchases")) return response([purchase]);
      if (url.endsWith("/api/suppliers")) return response([{ id: 1, name: "Local Supply", active: 1 }]);
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/inventory"), expect.anything());
    await act(async () => button(container, "Operations").click());
    await settle();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/inventory?warehouse_id=1", expect.objectContaining({ credentials: "include" }));
    expect(container.querySelector('[aria-label="Tax configuration"]')).toBeTruthy();
    expect(container.textContent).toContain("Move stock with a reason");
    expect(container.textContent).toContain("Low-stock visibility");
    await act(async () => button(container, "Save tax rule").click());
    await settle();
    expect(fetchMock.mock.calls.some(([url, options]) => String(url).endsWith("/api/tax/configuration") && (options as RequestInit)?.method === "POST")).toBe(true);
    await act(async () => root.unmount());
  });

  it("submits selected partial receipts and explicit over-receipt authorization details", async () => {
    const purchase = {
      id: 5,
      purchase_number: "PUR-0005",
      supplier_name: "Local Supply",
      status: "ordered",
      total: 80,
      lines: [{ id: 9, product_id: 1, warehouse_id: 1, product_name: "Adobo", warehouse_code: "MAIN", received_quantity: 0, quantity: 10, unit_cost: 8 }],
    };
    const receiptRequests: Row[] = [];
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === "POST" && url.endsWith("/api/purchases/5/receive")) {
        receiptRequests.push(JSON.parse(String(options.body)));
        return response({ purchase, lines: purchase.lines });
      }
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/audit-events") || url.endsWith("/api/tax/configuration")) return response(url.endsWith("/api/tax/configuration") ? { rules: [], effective_rule: null } : []);
      if (url.includes("/api/inventory?warehouse_id=1")) return response({ products: [{ product_id: 1, sku: "ADO-001", name: "Adobo", warehouse_id: 1, on_hand: 5, reserved: 0, available: 5, reorder_level: 2, low_stock: false, reorder_quantity: 0 }], movements: [] });
      if (url.endsWith("/api/warehouses")) return response([{ id: 1, code: "MAIN", name: "Main Warehouse" }]);
      if (url.endsWith("/api/purchases")) return response([purchase]);
      if (url.endsWith("/api/catalog")) return response(menu.map((item) => ({ ...item, sku: "ADO-001", active: 1 })));
      if (url.endsWith("/api/suppliers")) return response([{ id: 1, name: "Local Supply", active: 1 }]);
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => { button(container, "Operations").click(); });
    await settle();
    const receiptInput = container.querySelector<HTMLInputElement>('input[aria-label="Receive Adobo"]')!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => { setInputValue?.call(receiptInput, "3"); receiptInput.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    expect(receiptRequests[0]).toMatchObject({ lines: [{ product_id: 1, warehouse_id: 1, quantity: 3 }], allow_over_receipt: false });
    const override = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => override.click());
    await settle();
    const reason = container.querySelector<HTMLInputElement>('input[placeholder="Manager/admin reason"]')!;
    await act(async () => { setInputValue?.call(reason, "Manager approved supplier variance"); reason.dispatchEvent(new Event("input", { bubbles: true })); setInputValue?.call(receiptInput, "11"); receiptInput.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    expect(receiptRequests[1]).toMatchObject({ lines: [{ product_id: 1, warehouse_id: 1, quantity: 11 }], allow_over_receipt: true, override_reason: "Manager approved supplier variance" });
    await act(async () => root.unmount());
  });

  it("reuses a receipt idempotency key when the response is lost before retry", async () => {
    const purchase = { id: 5, purchase_number: "PUR-0005", supplier_name: "Local Supply", status: "ordered", total: 80, lines: [{ id: 9, product_id: 1, warehouse_id: 1, product_name: "Adobo", warehouse_code: "MAIN", received_quantity: 0, quantity: 10, unit_cost: 8 }] };
    const receiptRequests: Row[] = [];
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (options?.method === "POST" && url.endsWith("/api/purchases/5/receive")) {
        receiptRequests.push(JSON.parse(String(options.body)));
        if (receiptRequests.length === 1) return Promise.reject(new Error("Connection closed before the response"));
        return response({ purchase, lines: purchase.lines });
      }
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/audit-events") || url.endsWith("/api/tax/configuration")) return response(url.endsWith("/api/tax/configuration") ? { rules: [], effective_rule: null } : []);
      if (url.includes("/api/inventory?warehouse_id=1")) return response({ products: [], movements: [] });
      if (url.endsWith("/api/warehouses")) return response([{ id: 1, code: "MAIN", name: "Main Warehouse" }]);
      if (url.endsWith("/api/purchases")) return response([purchase]);
      if (url.endsWith("/api/catalog")) return response(menu.map((item) => ({ ...item, sku: "ADO-001", active: 1 })));
      if (url.endsWith("/api/suppliers")) return response([{ id: 1, name: "Local Supply", active: 1 }]);
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => { button(container, "Operations").click(); });
    await settle();
    const receiptInput = container.querySelector<HTMLInputElement>('input[aria-label="Receive Adobo"]')!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => { setInputValue?.call(receiptInput, "3"); receiptInput.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    await act(async () => button(container, "Receive selected").click());
    await settle();
    expect(receiptRequests).toHaveLength(2);
    expect(receiptRequests[0].idempotency_key).toMatch(/^receipt-/);
    expect(receiptRequests[1].idempotency_key).toBe(receiptRequests[0].idempotency_key);
    await act(async () => root.unmount());
  });

  it("clears previous delivery details when starting a new delivery", async () => {
    const line = { id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 };
    let createdOrders = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/delivery")) return response([]);
      if (url.endsWith("/api/delivery/drivers")) return response([]);
      if (url.endsWith("/api/counter/orders")) {
        createdOrders += 1;
        const created = { ...order, id: createdOrders, order_number: `BK-00${createdOrders}`, order_channel: "delivery" };
        return response({ order: created, lines: [], delivery: null });
      }
      if (url.endsWith("/lines")) {
        const orderId = Number(url.split("/api/orders/")[1].split("/")[0]);
        const current = { ...order, id: orderId, order_number: `BK-00${orderId}`, order_channel: "delivery", total: 12, lines: [line] };
        return response({ order: current, lines: [line], delivery: null });
      }
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    const setField = async (selector: string, value: string) => {
      const input = container.querySelector<HTMLInputElement>(selector)!;
      await act(async () => {
        setInputValue?.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };

    await act(async () => button(container, "Delivery").click());
    await settle();
    await act(async () => button(container, "New delivery").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    await act(async () => button(container, "Review order").click());
    await settle();
    await setField("#customer-name", "Mika");
    await setField("#delivery-address", "12 Mabini Street, Cebu City");
    await setField("#delivery-contact", "09171234567");
    await setField("#delivery-contact-name", "Mika");

    await act(async () => button(container, "Back to order type").click());
    await act(async () => button(container, "Delivery").click());
    await settle();
    await act(async () => button(container, "New delivery").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    await act(async () => button(container, "Review order").click());
    await settle();

    expect(container.querySelector<HTMLInputElement>("#customer-name")!.value).toBe("");
    expect(container.querySelector<HTMLInputElement>("#delivery-address")!.value).toBe("");
    expect(container.querySelector<HTMLInputElement>("#delivery-contact")!.value).toBe("");
    expect(container.querySelector<HTMLInputElement>("#delivery-contact-name")!.value).toBe("");
    await act(async () => root.unmount());
  });

  it("keeps promotion retries idempotent and renders the discounted order pricing", async () => {
    const line = { id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 };
    const appliedOrder = {
      ...order,
      status: "open",
      subtotal: 12,
      original_subtotal: 12,
      discount_amount: 2.4,
      discounted_subtotal: 9.6,
      total: 10.56,
      lines: [line],
      promotion: { applied_id: 11, code: "WELCOME20", name: "Welcome 20", discount_amount: 2.4, discounted_subtotal: 9.6 },
      tax: { policy: "exclusive", rate: "10.00", name: "VAT", taxable_subtotal: 9.6, tax_amount: 0.96, total: 10.56 },
    };
    const requests: Array<{ url: string; options?: RequestInit }> = [];
    let promotionAttempts = 0;
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      requests.push({ url, options });
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/api/promotions")) return response([{ code: "WELCOME20", name: "Welcome 20", type: "percentage", value: 20, can_apply: true }]);
      if (url.endsWith("/lines")) return response({ order: { ...order, id: 7, total: 12, subtotal: 12 }, lines: [line] });
      if (url.includes("/api/orders/") && url.endsWith("/promotions") && options?.method === "POST") {
        promotionAttempts += 1;
        if (promotionAttempts === 1) return Promise.reject(new Error("Connection closed before the response"));
        return response({ ...appliedOrder, order: { ...appliedOrder, promotion: appliedOrder.promotion } });
      }
      if (url.includes("/api/orders/") && url.endsWith("/promotions/11") && options?.method === "DELETE") return response({ ...appliedOrder, promotion: null, order: { ...appliedOrder, promotion: null, discount_amount: 0, discounted_subtotal: 12, total: 13.2 }, tax: { ...appliedOrder.tax, taxable_subtotal: 12, tax_amount: 1.2, total: 13.2 } });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;

    expect(requests.some(({ url }) => url.endsWith("/api/promotions"))).toBe(false);
    await act(async () => button(container, "Start order").click());
    await settle();
    expect(requests.some(({ url }) => url.endsWith("/api/promotions"))).toBe(true);
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();

    const code = container.querySelector<HTMLInputElement>("#promotion-code")!;
    await act(async () => { setInputValue?.call(code, "WELCOME20"); code.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Apply promotion").click());
    await settle();
    await act(async () => button(container, "Apply promotion").click());
    await settle();

    const promotionRequests = requests.filter(({ url, options }) => url.includes("/api/orders/") && url.endsWith("/promotions") && options?.method === "POST");
    expect(promotionRequests).toHaveLength(2);
    expect(JSON.parse(String(promotionRequests[0].options?.body))).toEqual({ code: "WELCOME20" });
    expect(promotionRequests[0].options?.headers).toEqual(expect.objectContaining({ "Idempotency-Key": expect.any(String) }));
    expect(promotionRequests[1].options?.headers).toEqual(expect.objectContaining({ "Idempotency-Key": promotionRequests[0].options?.headers && (promotionRequests[0].options?.headers as Record<string, string>)["Idempotency-Key"] }));
    expect(container.textContent).toContain("WELCOME20");
    expect(container.textContent).toContain("Discounted subtotal");
    expect(container.textContent).toContain("₱2.40");
    expect(container.textContent).toContain("₱9.60");
    expect(container.textContent).toContain("₱10.56");

    await act(async () => button(container, "Remove promotion").click());
    await settle();
    expect(requests.some(({ url, options }) => url.includes("/api/orders/") && url.endsWith("/promotions/11") && options?.method === "DELETE")).toBe(true);
    expect(container.textContent).not.toContain("WELCOME20");
    await act(async () => root.unmount());
  });

  it("keeps replacement available while a promotion is applied", async () => {
    const appliedOrder = { ...order, id: 7, subtotal: 12, total: 10.56, original_subtotal: 12, discounted_subtotal: 9.6, discount_amount: 2.4, promotion: { applied_id: 11, code: "WELCOME20", name: "Welcome 20", discount_amount: 2.4, discounted_subtotal: 9.6 }, tax: { policy: "exclusive", rate: "10.00", name: "VAT", taxable_subtotal: 9.6, tax_amount: 0.96, total: 10.56 }, lines: [{ id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }] };
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/promotions")) return response([{ code: "WELCOME20", name: "Welcome 20", can_apply: true }, { code: "SAVE10", name: "Save ten", can_apply: true }]);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/lines")) return response({ order: { ...order, id: 7, total: 12, subtotal: 12 }, lines: [{ id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }] });
      if (url.endsWith("/promotions") && options?.method === "POST") return response({ ...appliedOrder, order: appliedOrder });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => button(container, "Start order").click()); await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click()); await settle();
    const code = container.querySelector<HTMLInputElement>("#promotion-code")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => { setInputValue?.call(code, "WELCOME20"); code.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Apply promotion").click()); await settle();
    expect(container.querySelector<HTMLInputElement>("#promotion-code")).not.toBeNull();
    expect(container.textContent).toContain("Replace promotion");
    await act(async () => root.unmount());
  });

  it("disables promotion entry when promotion availability cannot be loaded", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/api/promotions")) return Promise.reject(new Error("Promotions unavailable"));
      if (url.endsWith("/lines")) return response({ order: { ...order, id: 7, total: 12, subtotal: 12 }, lines: [{ item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }] });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => button(container, "Start order").click()); await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click()); await settle();
    expect(container.querySelector<HTMLInputElement>("#promotion-code")?.disabled).toBe(true);
    await act(async () => root.unmount());
  });

  it("shows a read-only promotion state when the operator lacks permission", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/api/promotions")) return response([{ code: "MANAGER10", name: "Manager ten", can_apply: false, status: "active" }]);
      if (url.endsWith("/lines")) return response({ order: { ...order, total: 12, subtotal: 12 }, lines: [{ item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }] });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => button(container, "Start order").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();

    expect(container.textContent).toContain("Promotion access is read-only for this operator.");
    expect(container.querySelector<HTMLButtonElement>("button[aria-label=\"Apply promotion\"]")?.disabled).toBe(true);
    await act(async () => root.unmount());
  });

  it("keeps a promotion error visible and preserves the basket", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/api/promotions")) return response([{ code: "EXPIRED", name: "Expired", can_apply: true }]);
      if (url.endsWith("/lines")) return response({ order: { ...order, id: 7, total: 12, subtotal: 12 }, lines: [{ item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }] });
      if (url.includes("/api/orders/") && url.endsWith("/promotions")) return response({ detail: "Promotion has expired" }, false);
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => button(container, "Start order").click());
    await settle();
    await act(async () => container.querySelector<HTMLElement>('[aria-label="Add Adobo to order"]')!.click());
    await settle();
    const code = container.querySelector<HTMLInputElement>("#promotion-code")!;
    const setInputValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    await act(async () => { setInputValue?.call(code, "EXPIRED"); code.dispatchEvent(new Event("input", { bubbles: true })); });
    await act(async () => button(container, "Apply promotion").click());
    await settle();

    expect(container.textContent).toContain("Promotion has expired");
    expect(container.textContent).toContain("Adobo");
    expect(container.textContent).toContain("Choose items");
    await act(async () => root.unmount());
  });
});
