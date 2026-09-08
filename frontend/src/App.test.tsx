import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

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
    expect(container.textContent).toContain("$1.20");
    expect(container.textContent).toContain("$13.20");
    await act(async () => root.unmount());
  });

  it("loads tax configuration as a secondary operations view and can save a rule", async () => {
    const configuration = { rules: [], effective_rule: null };
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/tables")) return response([]);
      if (url.endsWith("/api/receipts")) return response([]);
      if (url.endsWith("/api/tax/configuration") && options?.method === "POST") return response({ id: 1 });
      if (url.endsWith("/api/tax/configuration")) return response(configuration);
      return response([]);
    });
    const { container, root } = await renderApp(fetchMock as unknown as typeof fetch);
    await act(async () => button(container, "Operations").click());
    await settle();
    expect(container.querySelector('[aria-label="Tax configuration"]')).toBeTruthy();
    await act(async () => button(container, "Save tax rule").click());
    await settle();
    expect(fetchMock.mock.calls.some(([url, options]) => String(url).endsWith("/api/tax/configuration") && (options as RequestInit)?.method === "POST")).toBe(true);
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
});
