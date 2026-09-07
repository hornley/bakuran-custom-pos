# Counter UI Simplification Implementation Plan

Date: 2026-09-07
Spec: `docs/superpowers/specs/2026-09-07-counter-ui-simplification-design.md`

## Scope

Frontend-only changes in `frontend/src/App.tsx` and `frontend/src/styles.css`. Preserve the existing backend contracts and secondary operational routes.

## Steps

1. Replace the large hero copy with a compact `Counter` header and two concise entry actions. **Done**
2. Remove manual counter/table language from the primary manual flow while keeping QR table context read-only for QR orders. **Done**
3. Add explicit non-destructive back handlers, including the visible `Back to order type` action above the stepper. **Done**
4. Keep basket and customer-name state when moving backward. Do not reverse payment or kitchen state. **Done**
5. Keep QR orders behind the `QR orders` / awaiting-payment route and retain connected queue selection. **Done**
6. Replace menu rows with a responsive product-card grid while keeping the basket visible. **Done**
7. Update CSS to support the compact header, two entry actions, back-action placement, product grid, and responsive layout without new dependencies. **Done**
8. Validate with TypeScript/Vite production build, live frontend HTTP/source checks, and backend regression tests to confirm no API behavior changed. **Done**

## Acceptance mapping

- Compact initial screen: served App.tsx contains `Counter`, `New order`, and `QR orders`, and excludes the removed hero phrases.
- No table requirement: manual confirmation contains no table field or table-number prompt.
- QR connection: awaiting-payment route and existing queue endpoints remain wired.
- Back navigation: each reversible screen renders its specified back action and state handlers only change client navigation/state.
- Regression safety: backend pytest and frontend build pass.
