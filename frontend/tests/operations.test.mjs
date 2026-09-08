import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");

test("inventory and purchasing stay behind the secondary operations route", () => {
  assert.match(app, /\["operations", "Operations"\]/);
  assert.match(app, /api\/inventory\?warehouse_id=/);
  assert.match(app, /api\/warehouses/);
  assert.match(app, /api\/purchases/);
  assert.match(app, /api\/audit-events/);
  assert.doesNotMatch(app, /useEffect\(\(\) => \{ void loadMenu\(\); \}, \[\]\);/);
  assert.match(app, /if \(!menu\.length\) await loadMenu\(\);/);
});

test("operations UI exposes safety-critical inventory and receipt controls", () => {
  assert.match(app, /Move stock with a reason/);
  assert.match(app, /Low-stock visibility/);
  assert.match(app, /received_quantity/);
  assert.match(app, /Authorized over-receipt/);
  assert.match(app, /Manager\/admin reason/);
  assert.match(app, /Receive selected/);
  assert.match(app, /Close purchase/);
});

test("operations layout has narrow-screen rules for forms and purchase cards", () => {
  assert.match(styles, /\.operations-stack/);
  assert.match(styles, /\.purchase-form/);
  assert.match(styles, /@media \(max-width: 640px\)/);
  assert.match(styles, /\.receipt-form \{ align-items: stretch; flex-direction: column;/);
});
