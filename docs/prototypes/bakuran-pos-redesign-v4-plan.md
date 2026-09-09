Bakuran POS redesign v4 — design plan

Surface
Operational workspace. The staff member should see the next useful action immediately; customer ordering is a separate, calmer surface.

Reference posture
Apple + Linear: measured spacing, neutral surfaces, quiet navigation, precise alignment, crisp sans typography, thin borders, and minimal elevation. Borrow restraint and rhythm, not branded colors or copied layouts.

Tokens
- Canvas #f7f7f5; surface #ffffff; inset #f1f1ef
- Ink #1d1d1f; muted #6e6e73; line #dededb
- Accent #d45d42 only for primary action/attention; success #4d7658
- Radius 8px for controls and rows; 12px only for primary work surfaces
- Typography: clean system sans stack; 12px metadata, 14px body, 20px section, 34px page title

Composition
Persistent 216px staff rail + 1px divider. Main content max 1180px with 32px/48px rhythm. Use aligned tables and list rows rather than decorative metric cards. A restrained four-column service strip is the one signature element: it reads live desk/kitchen/pickup/cash state without ornament.

Primary wireframe
[quiet rail] | [date/status]
             | [title + one CTA]
             | [service strip]
             | [dense operational table]
             | [secondary quick actions]

Routes/states
Overview, counter order, QR payment queue, kitchen, ready pickup, delivery, operations/inventory, customer QR ordering, invalid QR error, and empty basket. Each is reachable from the rail or in-prototype action.

Interaction/accessibility
Use visible focus rings, 44px minimum actions, sentence-case copy, explicit status text (never color alone), responsive rail-to-scrollable top nav, no auto-play motion, and prefers-reduced-motion. Keep the cash-only payment gate and customer handoff language explicit.

Self-critique before build
Avoid v3's large rounded surfaces and decorative dashboard feel. Use fewer containers, consistent row geometry, one neutral elevation level, and dense-but-readable data alignment. No gradients, purple, emoji, marketing hero, fake metrics, or unnecessary motion.
