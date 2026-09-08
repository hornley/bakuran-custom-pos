import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
  it("requests the ready kitchen queue when Ready is opened", async () => {
    const fetchMock = vi.fn((url: string) => response(url.endsWith("/api/menu") ? menu : []));
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    await act(async () => { button(container, "Ready").click(); });
    await settle();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/kitchen?queue=ready", expect.objectContaining({ credentials: "include" }));
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
    expect(JSON.parse(String(paymentRequests[0].body))).toEqual({ amount: 12, method: "cash" });
    expect(container.textContent).toContain("Order is moving.");
    await act(async () => root.unmount());
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

  it("keeps inventory and purchasing unloaded until Operations is opened", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/warehouses") || url.endsWith("/api/purchases") || url.endsWith("/api/suppliers") || url.endsWith("/api/audit-events")) return response([]);
      if (url.endsWith("/api/catalog")) return response(menu);
      if (url.endsWith("/api/inventory?warehouse_id=1")) return response({ products: [], movements: [] });
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);

    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/inventory"), expect.anything());
    await act(async () => { button(container, "Operations").click(); });
    await settle();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/inventory?warehouse_id=1", expect.objectContaining({ credentials: "include" }));
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:5300/api/purchases", expect.objectContaining({ credentials: "include" }));
    expect(container.textContent).toContain("Move stock with a reason");
    expect(container.textContent).toContain("Low-stock visibility");
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
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/audit-events")) return response([]);
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
    await act(async () => {
      setInputValue?.call(receiptInput, "3");
      receiptInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    expect(receiptRequests[0]).toMatchObject({
      lines: [{ product_id: 1, warehouse_id: 1, quantity: 3 }],
      allow_over_receipt: false,
    });

    const override = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    await act(async () => override.click());
    await settle();
    const reason = container.querySelector<HTMLInputElement>('input[placeholder="Manager/admin reason"]')!;
    await act(async () => {
      setInputValue?.call(reason, "Manager approved supplier variance");
      reason.dispatchEvent(new Event("input", { bubbles: true }));
      setInputValue?.call(receiptInput, "11");
      receiptInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    expect(receiptRequests[1]).toMatchObject({
      lines: [{ product_id: 1, warehouse_id: 1, quantity: 11 }],
      allow_over_receipt: true,
      override_reason: "Manager approved supplier variance",
    });
    await act(async () => root.unmount());
  });

  it("reuses a receipt idempotency key when the response is lost before retry", async () => {
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
        if (receiptRequests.length === 1) return Promise.reject(new Error("Connection closed before the response"));
        return response({ purchase, lines: purchase.lines });
      }
      if (url.endsWith("/api/tables") || url.endsWith("/api/receipts") || url.endsWith("/api/audit-events")) return response([]);
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
    await act(async () => {
      setInputValue?.call(receiptInput, "3");
      receiptInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => button(container, "Receive selected").click());
    await settle();
    await act(async () => button(container, "Receive selected").click());
    await settle();

    expect(receiptRequests).toHaveLength(2);
    expect(receiptRequests[0].idempotency_key).toMatch(/^receipt-/);
    expect(receiptRequests[1].idempotency_key).toBe(receiptRequests[0].idempotency_key);
    await act(async () => root.unmount());
  });
});
