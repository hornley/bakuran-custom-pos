import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeliveryBoard } from "./App";

describe("delivery board", () => {
  it("renders delivery-specific metadata, assignment history, and dispatch actions", () => {
    const html = renderToStaticMarkup(
      <DeliveryBoard
        busy={false}
        drivers={[{ id: 1, name: "Ari Santos" }, { id: 2, name: "Ben Cruz" }]}
        deliveries={[{
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
        }]}
        onAction={() => undefined}
      />,
    );

    expect(html).toContain("12 Mabini Street, Cebu City");
    expect(html).toContain("Ari Santos · active");
    expect(html).toContain("Out for delivery");
    expect(html).toContain("Ben Cruz");
  });
});
