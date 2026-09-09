---
version: alpha
name: Bakuran POS
description: A calm, precise restaurant point-of-sale interface built for fast service and obvious next actions.
colors:
  primary: "#A9522C"
  ink: "#1C1B19"
  muted: "#6B6862"
  faint: "#96918A"
  canvas: "#FBFAF7"
  surface: "#FFFFFF"
  surfaceSoft: "#F7F5F0"
  line: "#E4E1DC"
  lineStrong: "#D6D1CA"
  accentSoft: "#F8EEE8"
  success: "#4B6B3F"
  successSoft: "#E8EFE3"
  danger: "#A64235"
  textOnAccent: "#FFFFFF"
  textOnSuccess: "#FFFFFF"
typography:
  page-title:
    fontFamily: "Avenir Next, Nunito Sans, SF Pro Display, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.125rem"
    fontWeight: 650
    lineHeight: 1.08
    letterSpacing: "-0.045em"
  section-title:
    fontFamily: "Avenir Next, Nunito Sans, SF Pro Display, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Avenir Next, Nunito Sans, SF Pro Text, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 450
    lineHeight: 1.45
  label:
    fontFamily: "Avenir Next, Nunito Sans, SF Pro Text, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0.01em"
  display-number:
    fontFamily: "Avenir Next, Nunito Sans, SF Pro Display, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "-0.04em"
rounded:
  control: "8px"
  surface: "12px"
  status: "6px"
spacing:
  page: "24px"
  section: "32px"
  compact: "8px"
  row: "14px"
  control: "12px"
elevation:
  surface: "0 3px 8px rgba(42, 32, 24, 0.07), 0 1px 2px rgba(42, 32, 24, 0.04)"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.textOnAccent}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "#8F4325"
    textColor: "{colors.textOnAccent}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "44px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
    height: "44px"
  service-success:
    backgroundColor: "{colors.successSoft}"
    textColor: "{colors.success}"
    rounded: "{rounded.status}"
  status-attention:
    backgroundColor: "{colors.accentSoft}"
    textColor: "{colors.primary}"
    rounded: "{rounded.status}"
  page-canvas:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
  surface-soft:
    backgroundColor: "{colors.surfaceSoft}"
    textColor: "{colors.ink}"
  body-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
  surface-faint:
    backgroundColor: "{colors.faint}"
    textColor: "{colors.ink}"
  divider-surface:
    backgroundColor: "{colors.line}"
    textColor: "{colors.ink}"
  strong-divider-surface:
    backgroundColor: "{colors.lineStrong}"
    textColor: "{colors.ink}"
  status-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.textOnAccent}"
    rounded: "{rounded.status}"
  button-success:
    backgroundColor: "{colors.success}"
    textColor: "{colors.textOnSuccess}"
    rounded: "{rounded.control}"
  work-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
---

## Overview

Bakuran POS is an operational workspace, not a marketing dashboard. The interface should feel warm, premium, and dependable during a busy restaurant shift: quiet at rest, quick to scan, and explicit about the next safe action.

The primary surface is **Monitor + Operate**. Staff should see the live service state first, then act on the attention queue or start an order. Customer QR ordering is a separate, calmer single-column surface and must never expose operator navigation or credentials.

The generated redesign image is a mood and composition reference only. Implement the product's real data, routes, payment gate, and existing API contracts rather than copying a static mockup or inventing analytics.

## Colors

- **Canvas (`#FBFAF7`)** is the warm page background. It creates separation without dark chrome or heavy panels.
- **Surface (`#FFFFFF`)** is reserved for meaningful work surfaces: the queue, order basket, forms, and kitchen tickets.
- **Ink (`#1C1B19`)** carries headings, order numbers, totals, and primary labels.
- **Muted (`#6B6862`)** carries supporting copy and metadata. It must remain readable, never become placeholder-gray decoration.
- **Primary (`#A9522C`)** is the only brand/action accent. Use it for the main `New order` action, active navigation indicator, attention emphasis, and focused controls.
- **Success (`#4B6B3F`)** is reserved for paid, ready, healthy, and online states. Pair it with visible text; never communicate state by color alone.
- **Danger (`#A64235`)** is reserved for recoverable errors and destructive outcomes.
- Do not introduce gradients, purple, neon, rainbow status colors, food photography, or decorative illustrations in the operator surface.

## Typography

Use the available rounded humanist sans stack in the tokens. Do not add a large type ladder or use bold weight for every label.

- Page titles are approximately 34px and establish the page identity without becoming a hero.
- Section titles are approximately 20px.
- Body copy is 14px with comfortable line height.
- Metadata and table labels are 12px.
- Display numbers are reserved for order numbers, totals, and compact live counts.
- Use sentence case for user-facing copy. Keep headings short enough to scan in one or two lines.

## Layout

### Operator shell

Desktop uses a persistent left rail approximately 216px wide, a 1px divider, and a slim utility bar above the workspace. The rail contains the BK mark, `Bakuran` wordmark, grouped navigation, and the current shift/operator context. The main workspace is `min(1180px, available width)` with 24px page padding and a clear 32px rhythm between major regions.

The operator first viewport follows this order:

```text
utility bar: date · register · online state · utilities
page heading: Overview + New order
service strip: Front desk · Kitchen · Pickup · Cash gate
attention queue: order · customer/table · state · next action
quick actions: only useful secondary shortcuts
```

The page intentionally leaves some calm space on the right at wide desktop widths. Do not stretch operational tables to fill empty space with fake charts or metrics.

### Navigation

Group rail items as `Workspace`, `Sell`, `Fulfillment`, and `Operations`. The selected item has a warm neutral background and a restrained primary-color indicator. Badges show real pending counts only. On widths below 900px, replace the rail with a horizontally scrollable, keyboard-accessible top navigation; prevent page-level horizontal overflow. The operator surface is touch-first at tablet widths: controls use a 48px minimum hit area, iPad safe-area insets are respected, and portrait layouts reduce multi-column summaries before content is clipped.

### Service strip

The service strip is the one signature summary element. Use four aligned cells with equal visual weight:

- Front desk — Taking orders
- Kitchen — queued/in motion
- Pickup — ready count
- Cash gate — clear or needs attention

Use real endpoint data where available. Never fabricate revenue, conversion, or other analytics to fill the layout.

### Attention queue

Prefer a clean white table/list over a grid of metric cards. Each row keeps these adjacent: order number, customer or table, status text, elapsed time or item count, and the one next valid action. Use thin dividers, aligned columns, generous row padding, and a responsive card transformation below 720px. The primary action column remains visible and touch-sized.

### New order

The flow remains visibly sequential: `Basket` → `Customer` → `Payment` → `Kitchen & pickup`. On desktop, the menu and basket share the same row, with the basket sticky and visually quieter than the primary action. On mobile, the menu, summary, and basket stack in task order. Keep the amount due and payment action fully visible; unpaid orders must not enter the kitchen.

### Secondary workspaces

QR payments, Kitchen, Ready, Delivery, and Operations use the same shell but remain secondary to starting a counter order. Keep their existing endpoint contracts and state transitions. Do not preload inventory or purchasing data when the operator is only starting a counter order.

### Customer QR surface

Customer QR ordering has no operator rail. Use the same warm palette with a calmer single-column layout, clear table/session context, readable menu items, basket summary, and explicit cash-at-front-desk handoff language. Invalid or closed QR sessions show a safe recovery message without revealing tokens or operator data.

## Elevation & Depth

Use one subtle elevation level for white work surfaces:

```css
0 3px 8px rgba(42, 32, 24, 0.07),
0 1px 2px rgba(42, 32, 24, 0.04)
```

Borders and spacing should do most of the organizational work. Avoid stacked cards, inset shadows, glossy surfaces, glassmorphism, strong dark shadows, and decorative colored rails or accent strips attached to cards/tiles. Accent color belongs to actions, text, and status indicators—not card edges.

## Shapes

Use `8px` for controls and ordinary rows, `12px` for primary work surfaces, and `6px` for compact status treatments. Do not mix arbitrary radii across equivalent components. Every interactive target must have at least a 44px hit area, even when its visual label is compact.

## Components

- **Primary button:** filled primary color, white text, 44px minimum height, one per immediate context. The label names the action: `New order`, `Review & pay`, `Mark ready`, or `Assign driver`.
- **Secondary button:** white or transparent surface with a neutral border. Use for navigation, refresh, and reversible alternatives.
- **Service cell:** quiet white surface with a short label and visible state. Do not turn it into a dashboard KPI card.
- **Queue row:** a semantic list/table row with explicit status text and a single next-action control. Allow long names and addresses to wrap.
- **Status pill:** compact text plus an optional dot. Color reinforces the text; it never replaces it.
- **Order basket:** a sticky work surface on desktop with line items, quantity context, server-provided tax breakdown, total, and one clear continuation action.
- **Kitchen ticket:** order number, customer/table, item summary, elapsed time, payment state, and the next valid transition. Unpaid orders never appear in the kitchen queue.
- **Notice and error banner:** semantic `role="status"` or `role="alert"`, concise message, readable recovery action, and no loss of the last valid view.
- **Iconography:** use restrained text/icon combinations only where they improve scanning. Never use emoji or decorative icon toppers as filler.

## Do's and Don'ts

### Do

- Put the next safe action in front of the staff member.
- Use live server data for queue counts, statuses, totals, tax, order numbers, and receipts.
- Keep status visible as words and preserve keyboard focus order.
- Use semantic buttons, links, headings, landmarks, lists, labels, and live regions.
- Test the same operator route at 1440px, 1280px, 1024px, 768px, and 390px.
- Treat 768px portrait and 1024px landscape as supported iPad operator layouts; verify no page-level horizontal overflow and keep the complete primary action visible.
- Respect `prefers-reduced-motion` and keep motion optional for comprehension.
- Preserve authentication, CSRF, idempotency, cash-only payment, and payment-gated kitchen behavior.

### Don't

- Do not add fake metrics, charts, analytics, gradient decoration, or marketing hero copy.
- Do not preload inventory/purchasing in the counter flow.
- Do not allow an unpaid order into the kitchen queue.
- Do not use color as the only status signal.
- Do not create clickable `div` controls, invisible focus states, clipped payment buttons, or page-level horizontal overflow.
- Do not copy another company's branded UI, use arbitrary one-off radii, or leave legacy dark/amber tokens active in the operator surface.
- Do not run tests or mutation smoke checks against `backend/data/app.db`.
