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
    const paidOrder = { ...order, status: "paid", customer_name: "Mika", lines: [{ id: 1, item_name: "Adobo", quantity: 1, unit_price: 12, line_total: 12 }], ticket: { id: 3, status: "queued" } };
    const fetchMock = vi.fn((url: string, options?: RequestInit) => {
      calls.push(`${options?.method || "GET"} ${url}`);
      if (url.endsWith("/api/menu")) return response(menu);
      if (url.endsWith("/api/counter/orders")) return response({ order, lines: [] });
      if (url.endsWith("/lines")) return response({ order: paidOrder, lines: paidOrder.lines });
      if (url.endsWith("/confirm")) return response({ order: { ...paidOrder, status: "confirmed" }, lines: paidOrder.lines });
      if (url.endsWith("/pay")) return response({ order: paidOrder, lines: paidOrder.lines, ticket: paidOrder.ticket });
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
    const name = container.querySelector<HTMLInputElement>("#customer-name")!;
    await act(async () => { name.value = "Mika"; name.dispatchEvent(new Event("input", { bubbles: true })); name.dispatchEvent(new Event("change", { bubbles: true })); });
    await act(async () => button(container, "Continue to payment").click());
    await settle();
    await act(async () => button(container, "Record cash payment").click());
    await settle();

    expect(calls.some((call) => call.includes("POST http://localhost:5300/api/orders/7/pay"))).toBe(true);
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
});
