import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CustomerQrApp from "./CustomerQrApp";
import { customerQrTokenFromPath } from "./routing";

const token = "customer-secret-token";
const tablePayload = {
  table: { id: 2, code: "T02", name: "Table 2", seats: 4 },
  session: { id: 2, session_number: "SES-0002", status: "open" },
  menu: [
    { id: 1, sku: "BRG-001", category_id: 1, category_code: "FOOD", category_name: "Food", name: "House Burger", description: "Beef burger with fries", price: 18 },
    { id: 3, sku: "LEM-001", category_id: 2, category_code: "DRINK", category_name: "Drinks", name: "Lemonade", description: "Fresh house lemonade", price: 5 },
  ],
};

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function submittedOrder() {
  return {
    order: {
      id: 2,
      order_number: "ORD-0002",
      status: "awaiting_payment",
      customer_name: "Mika",
      order_channel: "qr",
      subtotal: 18,
      total: 18,
    },
    lines: [{ id: 1, menu_item_id: 1, item_name: "House Burger", quantity: 1, unit_price: 18, line_total: 18 }],
    table: { table_code: "T02", table_name: "Table 2" },
  };
}

describe("CustomerQrApp", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads a session menu without displaying the bearer token", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(tablePayload));

    render(<CustomerQrApp token={token} />);

    expect(await screen.findByText(/Table\s+T02/)).toBeTruthy();
    expect(screen.getByText("House Burger")).toBeTruthy();
    expect(document.body.textContent).not.toContain(token);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      expect.stringContaining(`/api/customer/tables/${token}`),
      expect.objectContaining({ credentials: "omit" }),
    );
  });

  it("submits the selected basket with a bounded retry key and shows payment confirmation", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(tablePayload))
      .mockResolvedValueOnce(jsonResponse(submittedOrder()));

    render(<CustomerQrApp token={token} />);
    await screen.findByText("House Burger");
    fireEvent.click(screen.getByRole("button", { name: "Add House Burger" }));
    fireEvent.change(screen.getByLabelText("Name for pickup"), { target: { value: "Mika" } });
    fireEvent.click(screen.getByRole("button", { name: "Place order" }));

    await screen.findByRole("heading", { name: "Order received" });
    const [, options] = vi.mocked(fetch).mock.calls[1];
    const headers = options?.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers["Idempotency-Key"]).toBeTruthy();
    expect(headers["Idempotency-Key"].length).toBeLessThanOrEqual(128);
    expect(JSON.parse(String(options?.body))).toEqual({
      customer_name: "Mika",
      lines: [{ menu_item_id: 1, quantity: 1 }],
    });
    expect(screen.getByText("ORD-0002")).toBeTruthy();
    expect(screen.getAllByText(/cash payment at the front desk/i).length).toBeGreaterThan(0);
    expect(screen.getByText("awaiting payment", { exact: false })).toBeTruthy();
    expect(document.body.textContent).not.toContain(token);
  });

  it("shows an API error without losing the customer's basket or name", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(tablePayload))
      .mockResolvedValueOnce(jsonResponse({ detail: "This table already has an active order" }, 409));

    render(<CustomerQrApp token={token} />);
    await screen.findByText("House Burger");
    fireEvent.click(screen.getByRole("button", { name: "Add House Burger" }));
    fireEvent.change(screen.getByLabelText("Name for pickup"), { target: { value: "Mika" } });
    fireEvent.click(screen.getByRole("button", { name: "Place order" }));

    expect((await screen.findByRole("alert")).textContent).toMatch(/could not be submitted/i);
    expect(screen.getByDisplayValue("Mika")).toBeTruthy();
    expect(screen.getAllByText("House Burger").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Place order" })).toBeTruthy();
  });

  it("renders a safe closed-token state without echoing the bearer token", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "Invalid or closed table QR token" }, 404));

    render(<CustomerQrApp token={token} />);

    expect(await screen.findByRole("heading", { name: "QR code unavailable" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toMatch(/invalid.*closed/i);
    expect(document.body.textContent).not.toContain(token);
    expect(document.querySelector("script")).toBeNull();
  });

  it("renders customer-provided names as text in the confirmation UI", async () => {
    const unsafeName = "<img src=x onerror=alert(1)>";
    const response = submittedOrder();
    response.order.customer_name = unsafeName;
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(tablePayload))
      .mockResolvedValueOnce(jsonResponse(response));

    render(<CustomerQrApp token={token} />);
    await screen.findByText("House Burger");
    fireEvent.click(screen.getByRole("button", { name: "Add House Burger" }));
    fireEvent.change(screen.getByLabelText("Name for pickup"), { target: { value: unsafeName } });
    fireEvent.click(screen.getByRole("button", { name: "Place order" }));

    await screen.findByRole("heading", { name: "Order received" });
    expect(document.querySelector("img")).toBeNull();
    expect(document.body.textContent).toContain(unsafeName);
  });
});

describe("customer QR route parsing", () => {
  it("only treats a single /qr/<token> path as the public route", () => {
    expect(customerQrTokenFromPath("/qr/abc123")).toBe("abc123");
    expect(customerQrTokenFromPath("/qr/abc123/")).toBe("abc123");
    expect(customerQrTokenFromPath("/")).toBeNull();
    expect(customerQrTokenFromPath("/qr/abc123/orders")).toBeNull();
  });
});
