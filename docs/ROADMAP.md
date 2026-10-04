# ROADMAP — Noore Candles store (v2, re-scoped 3 Oct 2026)

This file replaces the previous roadmap. The previous version is kept unchanged at
`docs/archive/ROADMAP-v1.md` and is still the reference for Appendix C and Appendix E.

## What was cut from v1, and why

v1 was sized for an established trading business. Noore Candles is a new, low-volume,
single-owner brand, so everything that costs build time without helping the first hundred
orders is cut or deferred.

| Cut or deferred | Why | Comes back when |
|---|---|---|
| Grievance module with SLA timers | A named contact, an email address and a wa.me link cover this volume | Order volume makes manual handling unreliable |
| GST | Owner is below the registration threshold. Tax rate is 0 and prices are shown "inclusive of all taxes" | Owner registers for GST (after seeing a CA) |
| WhatsApp Cloud API, COD-confirmation messaging, abandoned-cart messaging | Needs Meta business verification, templates and a rate card. Replaced by a plain wa.me link and order emails. COD is confirmed manually by the owner | COD volume makes manual confirmation a chore |
| Subscriptions / UPI AutoPay | No repeat-purchase data yet. One-tap reorder covers it | Reorder data shows a real repeat cycle |
| Margin-and-cohort owner dashboard | The existing owner dashboard plus Django admin is enough. Batch cost stays recorded, so margin can be computed later | Owner asks for it |
| Serviceable-pincode list, COD fee, COD order cap | Not needed until RTO is a measured problem | RTO becomes a problem |
| Multi-vendor residue removal (R1-R20) | Rule 4. It works, and removing it earns nothing before launch. Exception: R21 (vendor references in the storefront) and the header "Vendor" dropdown are pulled forward into G4.5, approved in writing by the owner on 3 Oct 2026 | After launch, with written approval |
| Expiry / best-before features | Candles do not expire. The batch and ledger code stays (it prevents overselling and holds cost). `perishable` stays unticked on every variant so expiry logic is dormant | Never, unless a perishable product is added |

Kept: pricing, prior-price history, Razorpay (test mode first), COD, reviews, reorder,
launch readiness.

## Decisions locked for this roadmap (3 Oct 2026)

| # | Decision |
|---|---|
| P1 | Currency is INR. All pricing logic is integer paise |
| P2 | Shipping is a flat Rs 79 per order. Free when the post-discount subtotal is Rs 999 or more |
| P3 | No COD fee, no COD maximum, no pincode restriction |
| P4 | The marketplace service fee is no longer charged or read. `ConfigSettings.service_fee_*` columns stay in place. Dropping them is a later removal proposal |
| P5 | Tax rate is 0. Prices are shown "inclusive of all taxes". No tax line at checkout |
| P6 | Legacy money: `*_paise` integer columns are added beside each Decimal column on `Cart`, `CartOrder`, `CartOrderItem`, backfilled, and all logic switches to paise |
| P7 | `ProductVariant.price_paise` is the only source of a selling price. `Product.price` is not read for logic |
| P8 | Coupons: percentage or flat rupees off. Per-customer limit, total usage cap, minimum order value, expiry date. Discount applies to the item subtotal before shipping. Free shipping can combine with a coupon |
| P9 | Strike-through shows MRP against selling price. An append-only price history is recorded from day one. A config flag (off by default) can later gate the strike-through on that history |
| P10 | Guest checkout is allowed (phone, email, address). Account creation is offered after purchase |
| P11 | Reviews: verified buyers only (a delivered order line), published only after owner moderation |
| P12 | Stripe and PayPal code stays in place. Both are hidden from checkout once Razorpay test mode works |
| P13 | Messaging: wa.me link in the footer and on the contact page. Order emails only |

Decisions made on the owner's behalf (the owner delegated these; each is cheap to reverse):

| # | Decision | Why | Cost to reverse |
|---|---|---|---|
| A1 | Each scent is its own Product. Size is the variant. The picker is built generically over `ProductVariant.options`, so a second axis (for example colour) needs data only, no code | A scent gets its own page, photos and reviews. One selector is simpler for the shopper | Low |
| A2 | Placeholder seed catalogue, local development only: three scents, each in 100 g at Rs 499 (MRP Rs 599), 200 g at Rs 799 (MRP Rs 949), 300 g at Rs 1,199 (MRP Rs 1,399) | Owner's range was Rs 450 to Rs 1,200 and prices are not final | None. Seed data never reaches production |
| A3 | "Free above Rs 999" is implemented as subtotal >= Rs 999, so an order of exactly Rs 999 ships free | Matches how shoppers read it | One comparison operator |
| A4 | Percentage discounts round down to a whole paisa. An order-level discount is split across lines in proportion to line subtotal (largest remainder), so line totals always sum to the order total | Needed for partial refunds and for GST later | Low |
| A5 | Legacy Decimal money columns are still written as a mirror of the paise value, and never read | Django admin, old emails and the legacy Stripe path stay numerically correct. Nothing silently shows a wrong number | Low |
| A6 | PayPal is hidden from checkout in G1, earlier than P12 says, because it would charge the rupee number in USD. Stripe is switched to `inr` and stays as the temporary test payment path until G3 | The store is not live, and one working test payment path is enough | Low |
| A7 | Hosting: one small VPS in an Indian region running Caddy, gunicorn, `run_worker` and PostgreSQL, with the built frontend served from the same domain. Nightly database and media backup to off-site object storage. Budget roughly Rs 500 to Rs 900 a month; confirm current prices at G5 | Web, worker and database on one box is the cheapest shape for this stack. One origin avoids CORS and cookie problems | Medium |
| A8 | The domain is assumed not yet bought. Buying it is an owner task at the start of G5 | Not confirmed by the owner | None |

## How phases run

Unchanged from CLAUDE.md: one branch per phase (`phase/<id>-<slug>`), database backup
before any migration, full files, reversible migrations, every test shown failing first,
`docs/BUILD_LOG.md` section with all ten headings, then stop for approval.

Every phase starts by running `python -m pytest -q` and `npx playwright test` and recording
the counts as its baseline. The baseline before G0 was 80 passed, 1 skipped.

Phase order: G0 (done) -> G1 -> G2 -> G3 -> G4 -> G4.5 -> G5.

---

## G0 — Sync and repair (DONE, see BUILD_LOG)

Repaired: products created after F-B had no variant; paid orders' reservations expired;
nothing called the state machine so stock never left. Also fixed the `AddToCart` import
casing, added MEDIA_ROOT test isolation, the pincode field, the PostgreSQL concurrency run
and the Playwright smoke suite.

---

## G1 — Pricing

**Goal.** One server-side function decides what a customer pays, in INR, in integer paise.

**Read first.** `store/models.py`, `store/views.py`, `store/serializers.py`,
`catalog/models.py`, `vendor/views.py`, `Cart.jsx`, `Checkout.jsx`, `ProductDetail.jsx`,
and every file that references `service_fee`, `tax`, `currency_sign`, `usd` or `USD`.

**Step 0, before any code.** Compare every default variant's `price_paise` with
`to_paise(product.price)`. F-B copied prices once, and the owner dashboard has edited
`Product.price` since. If any pair differs, list them and stop: which one wins changes what
a customer is charged.

**Schema (additive, one migration per item, all reversible).**

1. `Cart`, `CartOrder`, `CartOrderItem`: one `<name>_paise` integer column beside each
   existing Decimal money column. In addition, where not already covered by that rule:
   `CartOrder.subtotal_paise`, `discount_paise`, `shipping_paise`, `tax_paise`,
   `total_paise`, `coupon_code` (text snapshot); `CartOrderItem.unit_price_paise`,
   `line_subtotal_paise`, `discount_paise`, `line_total_paise`.
2. Data migration: backfill each paise column with `to_paise` of its Decimal twin. Reverse
   is a no-op (the Decimal columns were never changed).
3. `Coupon`: `kind` (PERCENT or FLAT, default PERCENT so existing rows keep their meaning),
   `flat_off_paise`, `min_order_paise`, `max_total_uses` (null = unlimited),
   `max_uses_per_customer` (default 1), `valid_from`, `valid_until` (null = open). The
   existing `discount` integer stays as the percentage.
4. New append-only model `CouponRedemption`: coupon, order, user (nullable), email,
   phone_e164, discount_paise, created_at. Unique on (coupon, order).
5. `ConfigSettings`: `shipping_flat_paise` (default 7900), `free_shipping_threshold_paise`
   (default 99900), `tax_rate_bps` (default 0). Data migration sets `currency_sign` to the
   rupee sign; reverse restores "$".

**The pricing function.** New module `store/pricing.py`, the only place totals are
computed. Cart view, checkout, order creation and (in G3) payment all call it.

    quote(lines, coupon_code=None, customer=None) -> Quote

- `lines` are (variant, qty). Unit price is `variant.price_paise`, read at call time.
- `subtotal = sum(unit_price x qty)`.
- Coupon validity: active, inside its date window, `subtotal >= min_order_paise`, total
  redemptions under `max_total_uses`, this customer's redemptions under
  `max_uses_per_customer`. A customer is matched by user id, or for a guest by normalised
  email or `phone_e164`. Redemptions on cancelled orders do not count.
- `discount`: PERCENT is `subtotal x percent // 100`; FLAT is `min(flat_off_paise, subtotal)`.
  It applies to the whole order, not to the first matching line, and is split across lines
  per A4.
- `shipping = 0` if `subtotal - discount >= free_shipping_threshold_paise`, else
  `shipping_flat_paise`. An empty cart has no shipping.
- `tax`: prices are tax-inclusive. `tax = taxable x rate / (10000 + rate)` in basis points,
  carved out of the price, never added on top. With `tax_rate_bps = 0` this is 0.
- `total = subtotal - discount + shipping`. No service fee. No COD fee.
- An invalid coupon returns the quote without a discount plus a reason the UI can show.

The redemption row is written in the same transaction that creates the order, with the
coupon row locked, so a capped coupon cannot be over-used by two simultaneous checkouts
(covered by the PostgreSQL concurrency test).

The order stores the quote as a snapshot. A later price change never alters an existing
order.

**Other work.**

- Remove every read of `service_fee_*` and of `Tax.rate`. The models and columns stay.
- Delete the `qty x rate` tax code path from logic.
- Owner dashboard create and edit: the price field writes the default variant's
  `price_paise` (and the legacy `Product.price` mirror, per A5).
- Add `total_paise` to `core/signals.py` `TRACKED_FIELDS` for `CartOrder`.
- API responses carry money as integer paise. New frontend helper
  `frontend/src/utils/money.js` with `formatINR(paise)`. Remove every hardcoded "$" from
  `Cart.jsx`, `Checkout.jsx`, `ProductDetail.jsx` and anywhere else found.
- Cart and checkout show: item subtotal, discount (with coupon code), shipping (or "Free"),
  total, and the line "Inclusive of all taxes". No tax row.
- Stripe: currency `inr`, amount from `total_paise`. PayPal: hidden from checkout (A6).

**Acceptance.**

- A tampered client total is ignored; the stored order equals `quote()`.
- Rs 920 cart pays Rs 79 shipping. Rs 999 cart ships free. Rs 1,100 cart with 10% off
  (Rs 990 after discount) pays Rs 79 shipping.
- A percentage coupon discounts every line; line totals sum to the order total to the paisa.
- A flat coupon larger than the subtotal reduces the subtotal to 0, never below.
- A coupon is refused when expired, under minimum, over its total cap, or over the
  per-customer cap (logged-in and guest). Each refusal has its own message.
- Cancelling an order frees its redemption.
- No order contains a service fee. No "$" or "USD" is rendered anywhere in the storefront.
- With `tax_rate_bps` set to 1800 in a test, tax is carved out and the total is unchanged.
- Mirror check (A5): after every order write in the test suite (create, coupon applied,
  quantity change, payment, cancel), a shared assertion walks every money column pair on
  `CartOrder` and `CartOrderItem` and proves `to_paise(decimal_column) == paise_column`. A
  dedicated test writes a paise value without its mirror and shows the assertion fails.
- Migrations apply and roll back cleanly on a copy of the database.
- Playwright: add to cart, apply coupon, see correct INR totals at checkout.

**Known limitation (accepted).** A guest can evade the per-customer coupon cap by checking
out with a different email and phone number. The cap is reliable only for logged-in
customers. `max_total_uses` still bounds the total cost of any coupon, so set it on every
coupon that matters. Record this in the G1 BUILD_LOG section under known gaps.

**Stop and ask.** Any mismatch in Step 0. Any legacy money column whose meaning is unclear.

**Not in G1.** Razorpay, COD selector, variant picker, price history.

---

## G2 — Storefront basics

**Goal.** A shopper can choose a size, see honest stock and price information, and read
the policies before paying.

**Read first.** `catalog/models.py`, `catalog/admin.py`, `inventory/services.py`,
`ProductDetail.jsx`, the product list and home views, `addToCart.jsx`, the footer and
router.

**Schema.**

1. New append-only model `catalog.PriceHistory`: variant, price_paise, mrp_paise,
   effective_from (aware datetime), actor. Written by a signal on every `ProductVariant`
   price or MRP change, so admin, dashboard and shell edits are all captured.
2. Data migration: one opening row per existing variant. Reverse deletes only those rows.
3. Settings: `STRIKETHROUGH_REQUIRES_PRICE_HISTORY` (default False),
   `PRICE_HISTORY_WINDOW_DAYS` (default 30), `LOW_STOCK_THRESHOLD` (default 5).

**Work.**

- Variant picker on the product page, rendered from the variants' `options`: one selector
  per option key (A1). Selecting a variant updates price, MRP, stock status and the SKU sent
  to the cart. The cart request sends the variant id. This also retires the swapped
  size/colour arguments in `ProductDetail.jsx`. Legacy `Size` and `Color` rows are no longer
  rendered; the rows stay.
- Strike-through. Flag off: show MRP struck through and "N% off" whenever
  `mrp_paise > price_paise`. Flag on: show a struck price only when the lowest price in the
  window before the current price took effect is higher than the current price, and strike
  that price. Never show a discount claim that the data does not support.
- Stock indicator from `inventory.services.available_qty`: "In stock", "Only N left" (only
  when N is real and at or below `LOW_STOCK_THRESHOLD`), "Sold out" (add-to-cart disabled).
  No timers, no invented scarcity (CLAUDE.md section 8).
- Shipping line on the product page and cart: "Shipping Rs 79. Free on orders of Rs 999 or
  more", plus in the cart "Add Rs X more for free shipping", computed by `quote()`.
- Policy pages: Shipping, Returns and Refunds, Privacy, Terms, Contact. Linked in the footer
  and from checkout. The copy comes from the owner; the phase stops if it has not been
  supplied. The contact page and footer carry the wa.me link and the support email.
- `Product.stock_qty` becomes read-only in Django admin and the owner dashboard shows
  ledger availability instead, so the stale field can no longer be edited into drift.
- Management command `seed_noore` (idempotent, refuses to run when `DEBUG` is False):
  creates the A2 placeholder catalogue with variants, options and opening stock through
  `inventory.services.receive_production`, with `perishable` False.

**Acceptance.**

- Choosing 200 g shows the 200 g price and adds the 200 g variant to the cart.
- A sold-out variant cannot be added; other sizes of the same candle still can.
- Every price change, from any entry point, writes exactly one history row with the actor.
  History rows cannot be updated or deleted.
- Flag off and flag on each behave as specified, covered by tests.
- "Only N left" matches `available_qty` and never appears above the threshold.
- All five policy pages render and are linked from the footer and checkout.
- Playwright: pick a variant, add to cart, open each policy page.

**Stop and ask.** Policy copy, support email, WhatsApp number, and whether the owner wants
any wording that amounts to a legal claim.

---

## G3 — Razorpay test mode and COD

**Goal.** A customer can pay by UPI, card or netbanking through Razorpay, or choose cash on
delivery. An order becomes "paid" only when Razorpay's webhook says so.

**Blocked on the owner (rule 12).** Before this phase starts, the owner supplies: Razorpay
test key id and secret; the webhook secret; the current official documentation pages (or
captured test-mode samples) for order creation, the checkout options, payment signature
verification, and the webhook events and their payloads. No request, response or webhook
shape is written from memory.

**Read first.** `store/order_state.py`, `store/views.py`, `core/idempotency.py`,
`core/jobs.py`, `inventory/services.py`, `Checkout.jsx`, and the existing Stripe and PayPal
views.

**Schema.**

1. `CartOrder`: `cod_confirmed_at` and `cod_confirmed_by` (nullable), if G0 did not add
   them; `payment_provider`; the provider's order id and payment id fields as named in the
   supplied documentation.
2. `CartOrder.oid`: confirm it is unique. If not, check for duplicates, report them, then
   add a unique constraint.

**Work.**

- Provider seam `store/payments/`: one interface (create payment, verify return, handle
  webhook) with a Razorpay implementation. Stripe and PayPal stay behind it, disabled by
  `ENABLED_PAYMENT_PROVIDERS`, and are not shown at checkout (P12).
- Checkout gets a payment-method selector: "UPI / Card / Netbanking" (default) and "Cash on
  delivery". UPI is presented first inside the Razorpay checkout, configured as the supplied
  documentation describes.
- Prepaid flow: the server creates the provider order for `total_paise` in INR from the
  stored quote; the browser opens the Razorpay checkout; on return the page shows
  "confirming payment" and polls the order. Only the webhook handler calls `mark_paid`,
  after verifying the signature, checking amount and currency against the order, and
  `claim_event` inside the same transaction. A duplicate webhook changes nothing.
- A periodic `core.jobs` job reconciles orders still pending after a few minutes by asking
  the provider for their status, so a missed webhook cannot strand a paid order.
- Late payment: if payment arrives after the stock hold expired, the handler tries to
  reserve again. If stock is gone the order is flagged for the owner to refund; it is never
  silently marked paid and unshippable.
- COD flow: the order is placed with `payment_method = COD` and its reservation is kept (not
  subject to the cart TTL). The owner confirms by phone or WhatsApp, then presses
  "Confirm COD" on the order in the owner dashboard, which sets `cod_confirmed_at` through
  the state machine and is audited. Only then can the order be dispatched. On delivery the
  owner marks it paid through `mark_paid`.
- Refunds are issued by the owner in the Razorpay dashboard and recorded on the order
  through the state machine. No refund API in this phase.
- Order emails through `core.jobs`: order placed (with COD or payment-pending wording),
  payment received, shipped with tracking, cancelled. Each is sent once (dedupe key).
- After purchase, a guest sees "Create an account to track this order". The set-password
  link goes to the order's email address and, once used, attaches that email's guest orders
  to the new account. Orders are never attached to an unverified email.
- Local development needs a public tunnel for the webhook; document the exact steps in
  BUILD_LOG.

**Acceptance.**

- A forged or unsigned webhook is rejected and changes nothing.
- The same webhook delivered twice marks the order paid once and sends one email.
- A webhook whose amount or currency does not match the order is rejected.
- Returning from checkout without a webhook leaves the order unpaid until the webhook or the
  reconcile job confirms it.
- A COD order cannot be dispatched before "Confirm COD" and can after.
- Stock leaves the ledger exactly once per dispatched order, prepaid or COD.
- Stripe and PayPal do not appear at checkout; their code and tests remain.
- No key or secret appears in code, logs or the frontend bundle beyond the public key id.
- Playwright: COD checkout end to end; prepaid checkout up to the provider hand-off.

**Stop and ask.** Any payload shape not in the supplied documentation. Any ambiguity about
which event means "paid".

---

## G4 — Reviews and one-tap reorder

**Goal.** Real buyers can review what they received, and a returning customer can buy the
same order again in one tap.

**Read first.** The existing `Review` model, its serializers and views, the customer order
views, `ProductDetail.jsx`, the account order pages.

**Schema.**

1. `Review`: `order_item` (nullable FK to `CartOrderItem`), `status` (PENDING, APPROVED,
   REJECTED), `moderated_by`, `moderated_at`. Data migration marks existing reviews
   APPROVED so nothing vanishes; the owner can reject demo ones. New reviews start PENDING.
2. Unique constraint: one review per user per product.

**Work.**

- Eligibility: the signed-in user owns an order with a delivered line for that product. The
  server checks; the UI only shows the form when eligible. Guests are prompted to create an
  account through the G3 link.
- Public lists and the product's average rating use APPROVED reviews only, and expose name
  and avatar only (F-A guarantee).
- Owner moderation queue in the owner dashboard: approve or reject, audited. Rejecting is
  for abuse and spam, not for low ratings; the screen says so.
- One review-request email a set number of days after delivery (`REVIEW_REQUEST_DELAY_DAYS`,
  default 7), through `core.jobs`, once per order. No reminders.
- Reorder: `POST` on an order the caller may access adds each line's variant to the cart at
  today's price and today's availability, through the normal cart path (so stock is
  reserved). The response lists what was added, what was reduced and what is sold out or
  discontinued. It never places an order by itself. "Buy again" appears on the order detail
  page and in the account order list.

**Acceptance.**

- A user without a delivered line for the product cannot post a review (403).
- A PENDING or REJECTED review never appears publicly and never affects the average.
- A second review for the same product by the same user is refused.
- Reorder of a three-line order with one line sold out adds two lines and reports the third.
- Reorder uses current prices, not the old order's prices.
- Playwright: reorder from order history lands in a correct cart.

---

## G4.5 — Brand and storefront

**Goal.** The storefront looks and reads like Noore Candles, and a shopper never meets
marketplace language.

**Owner task before this phase starts.** Decide whether the existing v0 Noore Candles
design becomes the storefront skin or this storefront gets its own design. Supply the logo,
favicon, colour palette, typefaces, home and About copy, and product photos. The phase does
not start without this decision.

**Approval on record.** The owner approved in writing on 3 Oct 2026: removing the header
"Vendor" dropdown, moving the owner dashboard to `/admin-area/`, and pulling removal
proposal R21 forward. This satisfies rule 4 for those items only. R1-R20 stay unapproved.

**Read first.** `docs/archive/ROADMAP-v1.md` Appendix E (the exact wording of R21), the
storefront header and footer, the router, `Dashboard.jsx`, every file under the vendor
views folder, `ProductDetail.jsx`, `Products.jsx`, `Cart.jsx`, `Search.jsx`, `index.html`,
and the global styles. If R21 as written covers more or less than the four files named
here, stop and report the difference.

**Schema.** None expected. No backend model, field or endpoint is renamed or removed.

**Work.**

- Branding: page title and meta description, favicon, logo, colour tokens and typography
  applied through one theme file, so the skin can change without touching components.
- Header: remove the "Vendor" dropdown. Staff users see a single "Admin" link; nobody else
  sees any link to the dashboard.
- Owner dashboard moves to `/admin-area/` (distinct from Django's `/admin/`). The route is
  shown only when the signed-in user is staff. This is a convenience gate; the API keeps
  enforcing `IsStaffOwner`, which is the real protection. Old `/vendor/...` routes redirect
  staff to the matching `/admin-area/...` page and show the normal not-found page to
  everyone else.
- D17: `Dashboard.jsx` no longer redirects anyone to `/vendor/register/`. A non-staff
  visitor to a dashboard URL gets the not-found page. The register page is unreachable
  from the storefront.
- R21: strip vendor names, vendor links, "sold by" lines and shop references from
  `ProductDetail.jsx`, `Products.jsx`, `Cart.jsx` and `Search.jsx`.
- Home page, About page, and the product photo layout (gallery on the product page,
  consistent image ratio on listing cards).
- Dashboard screens keep working as they are; restyling them is not in scope.

**Acceptance.**

- Logged out, no occurrence of the word "vendor" (any case) is reachable: not in rendered
  text, link targets, page titles, image alt text or any route a shopper can navigate to.
  A Playwright test crawls every storefront link from the home page and asserts this.
- A logged-in non-staff customer never sees a dashboard link and is never redirected to
  `/vendor/register/`.
- A staff user reaches every dashboard screen under `/admin-area/`; products, orders,
  coupons, COD confirmation and review moderation all still work. Existing dashboard tests
  stay green.
- Title, favicon and logo show Noore Candles on every page.
- Home, About, product list and product page pass the Playwright smoke at mobile and
  desktop widths.

**Stop and ask.** The design decision above. Whether API paths containing `vendor`
(visible only in the browser's network tab, not in the page) must also change: renaming an
endpoint is outside this approval. Anything in R21 that goes beyond the four named files.

---

## G5 — Launch readiness

**Goal.** The store is live on its own domain, taking real payments, with backups that have
been restored at least once.

**Owner tasks, started early because they take days.**

- Buy the domain.
- Complete Razorpay KYC and get live keys.
- Decide the transactional email provider and verify the sending domain (SPF, DKIM).
- Supply final product photos, prices, MRP, weights and policy copy.
- Enter real unit cost on each batch (opening batches have cost 0), so margin is meaningful.
- Ask a CA or lawyer about: mandatory product declarations on the listing (MRP, net
  quantity, maker's address, country of origin), the contact or grievance details that must
  be published, and privacy obligations. These are legal questions and are not decided in
  code.

**Work.**

- Production settings: `DEBUG` False, `ALLOWED_HOSTS`, CSRF and CORS origins, secure
  cookies, HSTS. Every variable in `.env.example`.
- PostgreSQL in production, starting from a fresh database (migrations only), not from the
  seeded SQLite file. The owner creates the shop and real catalogue; `claim_shop` attaches
  it. `seed_noore` cannot run there.
- Server per A7: Caddy with automatic HTTPS, gunicorn, `run_worker` as a service that
  restarts on failure, built frontend served from the same domain, media on disk.
- Shared cache for throttling (Django database cache) so rate limits hold across processes.
- Backups: nightly `pg_dump` plus media to off-site storage, retained 14 days. A restore
  into a scratch database is performed and written up in BUILD_LOG. A backup that has never
  been restored does not count.
- Run the PostgreSQL concurrency test against the production database engine version.
- Razorpay live keys and live webhook. One real low-value order placed, paid, dispatched,
  delivered and refunded.
- Error reporting for the backend and uptime check on the home page and API.
- `npm audit`: triage, fix what touches production code paths, document the rest.
- Deploy runbook in `docs/DEPLOY.md`: deploy, roll back, restore, rotate a secret.
- Robots, sitemap, page titles and social preview for product pages.

**Acceptance.**

- The site loads on the domain over HTTPS; HTTP redirects.
- A real order completes end to end and its emails arrive in an inbox, not spam.
- Restarting the server brings web and worker back without manual steps.
- The restore drill is documented with timings.
- The full pytest suite passes against PostgreSQL. Playwright passes against production
  with a COD order that is then cancelled.

---

## Deferred (not scheduled)

GST invoices and tax lines; WhatsApp Cloud API; subscriptions; grievance module; margin and
cohort dashboard; serviceable pincodes and COD limits; removal of multi-vendor residue
(R1-R20; R21 is done in G4.5); removal of Stripe and PayPal code; dropping `service_fee_*`, `Tax`,
`Product.stock_qty`, legacy Decimal money columns and legacy `Size` / `Color`; shipping
aggregator integration and automatic tracking; a refund API; a database-level append-only
guard; removing the per-request `Meta.depth` mutation in serializers.

Each of these needs its own written approval and its own phase.

---

## Appendix A — Standing rules summary

See CLAUDE.md. Where this roadmap and CLAUDE.md disagree, stop and ask.

## Appendix B — Data-model map (after G0)

| Area | Models | Money | Notes |
|---|---|---|---|
| Catalogue | `store.Product`, `catalog.ProductVariant` | Variant: paise. Product: legacy Decimal, not read after G1 | One default variant per product. `perishable` stays False |
| Inventory | `inventory.Batch`, `StockMovement` (append-only), `StockReservation` | `cost_per_unit_paise` | Stock is derived from the ledger |
| Orders | `store.Cart`, `CartOrder`, `CartOrderItem` | Legacy Decimal; paise columns added in G1 | Status only through `store/order_state.py` |
| Pricing | `store.Coupon`, `ConfigSettings`, `Tax`; from G1 `CouponRedemption`; from G2 `catalog.PriceHistory` | Paise for new fields | `Tax` and `service_fee_*` unread after G1 |
| Platform | `core.AuditLog`, `ProcessedEvent`, `Job` | n/a | Audit and idempotency are append-only |
| Legacy | `vendor.*`, `Size`, `Color`, Stripe and PayPal views | n/a | Left in place |

## Appendix C — Order state-machine tables

Unchanged. The tables are in `docs/archive/ROADMAP-v1.md`, Appendix C, and the enforced
version is `backend/store/order_state.py`. If the two differ, the code is what runs: stop
and report the difference. G3 adds the COD-confirmed step and must update the archived
table's successor here when it does.

## Appendix D — Bug register

| # | Bug | Fixed in |
|---|---|---|
| D1 | Currency is USD (Stripe, PayPal, `currency_sign`, hardcoded "$") | G1 |
| D2 | Tax computed as qty x rate | G1 |
| D3 | Coupon discounts the first line only, is reusable without limit, usage unrecorded | G1 |
| D4 | 5% service fee added to every order | G1 |
| D5 | Checkout maths uses legacy Decimal rupees | G1 |
| D6 | Default variant price can differ from `Product.price` | G1, Step 0 |
| D7 | No variant picker; `ProductDetail.jsx` passes size and colour swapped | G2 |
| D8 | No stock indicator, no policy pages | G2 |
| D9 | `Product.stock_qty` can be edited in admin and drift from the ledger | G2 |
| D10 | No Razorpay, no COD, no payment-method selector | G3 |
| D11 | Nothing sets `cod_confirmed_at`, so no COD order can be dispatched | G3 |
| D12 | `CartOrder.oid` uniqueness not guaranteed | G3 |
| D13 | Reviews are unmoderated and not tied to a purchase | G4 |
| D14 | Throttle counters are per process | G5 |
| D15 | Opening batches have unit cost 0 | G5, owner data task |
| D16 | 56 `npm audit` findings | G5 |
| D17 | `Dashboard.jsx` redirects ordinary customers to `/vendor/register/` | G4.5 |
| D18 | Serializers mutate `Meta.depth` per request | Deferred |
| D19 | Phone normalisation accepts Indian mobiles only | Accepted (India-only store) |
| D20 | Nested rows get new ids on every product save | Accepted |

## Appendix E — Vendor-named code and removal proposals

Proposals R1-R21 are listed in `docs/archive/ROADMAP-v1.md`, Appendix E. R21 (vendor
references in the storefront) was approved by the owner on 3 Oct 2026 and is performed in
G4.5, together with removing the header "Vendor" dropdown. R1-R20 are unchanged and not
approved; nothing in this roadmap performs any of them. New candidates raised by this
re-scope, to be added to that list when it is next reviewed: `ConfigSettings.service_fee_*`,
the `Tax` model, legacy Decimal money columns, legacy `Size` and `Color`, Stripe and PayPal
code.
