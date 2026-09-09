import { beforeEach, describe, expect, it } from "vitest";
import { mockApi, resetMockData } from "./mockData";

describe("mock visual data", () => {
  beforeEach(() => resetMockData());

  it("provides populated operator queues and operations data", async () => {
    const kitchen = await mockApi<any[]>("/api/kitchen");
    const ready = await mockApi<any[]>("/api/kitchen?queue=ready");
    const payments = await mockApi<any[]>("/api/payment-queue");
    const inventory = await mockApi<any>("/api/inventory?warehouse_id=1");

    expect(kitchen.length).toBeGreaterThanOrEqual(3);
    expect(ready.length).toBeGreaterThanOrEqual(2);
    expect(payments.length).toBeGreaterThanOrEqual(2);
    expect(inventory.products.length).toBeGreaterThanOrEqual(4);
    expect(kitchen.some((ticket: any) => ticket.status === "preparing")).toBe(true);
    expect(payments.every((order: any) => order.order_channel === "qr")).toBe(true);
    expect(payments.every((order: any) => Number(order.subtotal) > 0)).toBe(true);
  });

  it("supports the visible counter-order progression without touching the backend", async () => {
    const started = await mockApi<any>("/api/counter/orders", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const withLine = await mockApi<any>(`/api/orders/${started.order.id}/lines`, {
      method: "POST",
      body: JSON.stringify({ menu_item_id: 1, quantity: 1 }),
    });
    const confirmed = await mockApi<any>(`/api/orders/${started.order.id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ customer_name: "Mika" }),
    });
    const paid = await mockApi<any>(`/api/orders/${started.order.id}/pay`, {
      method: "POST",
      body: JSON.stringify({ amount: String(confirmed.order.total), method: "cash" }),
    });

    expect(withLine.order.lines).toHaveLength(1);
    expect(confirmed.order.status).toBe("awaiting_payment");
    expect(paid.order.status).toBe("paid");
    expect(paid.ticket.status).toBe("queued");
  });

  it("provides a safe customer QR session and submitted order preview", async () => {
    const session = await mockApi<any>("/api/customer/tables/demo-token");
    const submitted = await mockApi<any>("/api/customer/tables/demo-token/orders", {
      method: "POST",
      body: JSON.stringify({ customer_name: "Mika", lines: [{ menu_item_id: 1, quantity: 2 }] }),
    });

    expect(session.table.code).toBe("T06");
    expect(session.menu.length).toBeGreaterThanOrEqual(4);
    expect(submitted.order.status).toBe("awaiting_payment");
    expect(submitted.lines[0].quantity).toBe(2);
  });

  it("keeps mock kitchen and pickup actions stateful", async () => {
    const started = await mockApi<any>("/api/orders/101");
    const ticket = await mockApi<any>("/api/kitchen/1/start", { method: "POST" });
    const prepared = await mockApi<any>("/api/kitchen/1/ready", { method: "POST" });
    const served = await mockApi<any>("/api/kitchen/1/serve", { method: "POST" });
    const closed = await mockApi<any>(`/api/orders/${started.order.id}/close`, { method: "POST" });

    expect(ticket.status).toBe("preparing");
    expect(prepared.status).toBe("ready");
    expect(served.status).toBe("served");
    expect(closed.order.status).toBe("closed");
    expect(closed.receipt.receipt_number).toBeTruthy();
  });

  it("keeps seeded QR subtotal and total aligned", async () => {
    const payments = await mockApi<any[]>("/api/payment-queue");
    const catalog = await mockApi<any[]>("/api/menu");
    const prices = new Map(catalog.map((item) => [item.name, item.price]));
    for (const order of payments) {
      expect(Number(order.subtotal)).toBe(order.lines.reduce((sum: number, line: any) => sum + line.line_total, 0));
      expect(Number(order.total)).toBe(Number(order.subtotal) + Number(order.tax_amount || 0));
      for (const line of order.lines) expect(line.unit_price).toBe(prices.get(line.item_name));
    }
  });

  it("keeps every seeded kitchen ticket linked to an order", async () => {
    const tickets = [...await mockApi<any[]>("/api/kitchen"), ...await mockApi<any[]>("/api/kitchen?queue=ready")];
    for (const ticket of tickets) {
      const opened = await mockApi<any>(`/api/orders/${ticket.order_id}`);
      expect(opened.order.id).toBe(ticket.order_id);
    }
  });

  it("removes a paid QR order from the payment queue", async () => {
    const before = await mockApi<any[]>("/api/payment-queue");
    const target = before[0];
    await mockApi(`/api/orders/${target.id}/pay`, {
      method: "POST",
      body: JSON.stringify({ amount: String(target.total), method: "cash" }),
    });
    const after = await mockApi<any[]>("/api/payment-queue");
    expect(after.some((order) => order.id === target.id)).toBe(false);
  });

  it("adds a paid delivery order to the delivery board", async () => {
    const started = await mockApi<any>("/api/counter/orders", { method: "POST", body: JSON.stringify({ order_channel: "delivery" }) });
    await mockApi<any>(`/api/orders/${started.order.id}/lines`, {
      method: "POST",
      body: JSON.stringify({ menu_item_id: 1, quantity: 1 }),
    });
    await mockApi(`/api/orders/${started.order.id}/delivery`, {
      method: "POST",
      body: JSON.stringify({ address: "12 Mabini Street", contact: "09171234567", contact_name: "Mika" }),
    });
    const confirmed = await mockApi<any>(`/api/orders/${started.order.id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ customer_name: "Mika" }),
    });
    await mockApi(`/api/orders/${started.order.id}/pay`, {
      method: "POST",
      body: JSON.stringify({ amount: String(confirmed.order.total), method: "cash" }),
    });
    const deliveries = await mockApi<any[]>("/api/delivery");
    expect(deliveries.some((delivery) => delivery.order_id === started.order.id)).toBe(true);
  });

  it("applies the active tax rule to new mock orders", async () => {
    const submitted = await mockApi<any>("/api/customer/tables/demo-token/orders", {
      method: "POST",
      body: JSON.stringify({ customer_name: "Mika", lines: [{ menu_item_id: 1, quantity: 1 }] }),
    });
    expect(submitted.order.tax_policy).toBe("exclusive");
    expect(Number(submitted.order.tax_amount)).toBeGreaterThan(0);
    expect(Number(submitted.order.total)).toBe(Number(submitted.order.subtotal) + Number(submitted.order.tax_amount));
  });

  it("keeps mock inventory mutations visible after reload", async () => {
    const before = await mockApi<any>("/api/inventory?warehouse_id=1");
    const target = before.products[0];
    await mockApi(`/api/stock/adjustment`, { method: "POST", body: JSON.stringify({ product_id: target.product_id, warehouse_id: 1, quantity: 2, reason: "Cycle count" }) });
    await mockApi(`/api/inventory/reorder-level`, { method: "PUT", body: JSON.stringify({ product_id: target.product_id, warehouse_id: 1, reorder_level: 12 }) });
    const after = await mockApi<any>("/api/inventory?warehouse_id=1");
    const updated = after.products.find((product: any) => product.product_id === target.product_id);
    expect(updated.on_hand).toBe(target.on_hand + 2);
    expect(updated.reorder_level).toBe(12);
  });
});
