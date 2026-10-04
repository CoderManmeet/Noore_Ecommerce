# BUILD LOG

Single-brand D2C conversion of the Django + React ecommerce codebase.
Newest phase first. Every phase ends with the ten sections required by the brief.

---

## Decisions taken on the owner's behalf (27 Sep 2026)

The owner delegated all Phase 0 questions ("do what you feel would be best, keep me informed").
These are the decisions. Each can be reversed; the cost of reversing is noted.

| # | Question | Decision | Why | Cost to reverse |
|---|---|---|---|---|
| D1 | Which repo | The uploaded Udemy "Completed Source Code" | Only codebase available | n/a |
| D2 | Foundation phase before Feature 1 | **Yes**, split into F-A (platform + security) and F-B (catalog, inventory, orders) | Live-verified security holes and no stock model | n/a |
| D3 | Database | SQLite stays the local default; **PostgreSQL required for production** and for the Feature 10 concurrency test (that test will be skipped on SQLite, never faked). Selected via `DATABASE_URL`. `psycopg2` replaced by `psycopg2-binary` | Zero-friction Windows dev; honest concurrency testing | Low |
| D4 | Job runner | **DB-backed outbox** (`core.Job`) + `python manage.py run_worker`. No Redis, no Celery | Celery is not supported on Windows; one less service to run and pay for; works on SQLite and Postgres | Medium: handlers are plain idempotent functions, so they can be moved onto Celery later without rewriting them |
| D5 | Ledger / batch ordering | Stock ledger core (Feature 10) and `Batch` (Feature 5) move into **F-B** | Features 1, 3, 5, 6 all move stock; building them on `stock_qty` would be thrown away | n/a |
| D6 | Variants | One `ProductVariant` per product backfilled in F-B. Existing `Size`/`Color` rows are **not** converted yet | The frontend never uses size price (it always sends `product.price`), so sizes are cosmetic today | Low |
| D7 | Money | New tables are **integer paise only**. Legacy Decimal columns are untouched until a dedicated, reversible money-migration phase | Rule 6: never silently change money storage | n/a |
| D8 | Stripe + PayPal | **Kept and hardened** until Razorpay is live, then proposed for removal | Removing them now leaves no way to pay | Low |
| D9 | Owner identity | The owner and their team are Django **staff users** (`is_staff=True`). All vendor-dashboard endpoints are staff-only | Single brand: "vendor dashboard" = owner dashboard | Low |
| D10 | Guest checkout | **Allowed** (carts and orders work without login) | Required for Feature 4 phone-captured carts; standard for Indian D2C | Low |
| D11 | Multi-vendor residue | **Nothing removed.** Removal proposals R1-R21 stand; scheduled after Phase 5 | Rule 4, and the vendor dashboard is the only product-management UI | n/a |
| D12 | Marketplace service fee (5% on every order) | **Not changed in code.** Owner should set `Settings > service fee percentage` to 0 in Django admin | It is pricing data, not code; changing it silently changes customer totals | n/a |
| D13 | GST / tax bug | Not fixed yet (documented). Fixed in the pricing work with the paise migration | Changing tax changes every total | n/a |

**Still blocked on the owner (cannot be decided for you, rule 12):** Razorpay integration docs/samples and account capabilities; WhatsApp Cloud API templates, rate card and webhook samples. These block Phase 1 features [1] and [2], not F-B.

---

## Decisions taken on the owner's behalf (3 Oct 2026, phases G1 and G2)

The owner's instruction for this session: "build it from what source code you have, just fix
it as you feel". The ZIP supplied was the **Phase F-B snapshot** (80 passed, 1 skipped); the
G0 work described in the roadmap was not in it. These are the calls made. Each is reversible.

| # | Question | Decision | Why | Cost to reverse |
|---|---|---|---|---|
| E1 | G0 is missing from the supplied code | Built G1 and G2 on the F-B snapshot and re-did only the G0 items they depend on: the `AddToCart` import casing, MEDIA_ROOT test isolation, a default variant for every new product, paid-order stock holds, the pincode input, and a Playwright smoke suite. **If a separate G0 branch exists elsewhere it will conflict with this code; keep one, not both** | Nothing else to build on | Medium (a merge) |
| E2 | G1 Step 0 | Ran on the supplied `db.sqlite3` after applying its pending F-A/F-B migrations: 4 products, 4 default variants, **0 mismatches**. The result is trivially clean because the variants were created by the backfill moments earlier; it says nothing about any other database | Only database available | n/a |
| E3 | If a price mismatch exists on another database | Not auto-resolved. From G1 on the two can no longer diverge (signals keep them in step), but an old mismatch stays until the owner picks a winner | Choosing silently would change what a customer is charged | n/a |
| E4 | Existing demo amounts (dollars) | Re-labelled as rupees with no conversion. The one legacy order keeps its old service fee and tax as history | Demo data | None |
| E5 | `ProductVariant.options` did not exist | Added as a JSON column (G2), backfilled from the `size` / `color` text columns, which stay | The roadmap builds the picker over it | Low |
| E6 | Existing coupons | Become PERCENT, one use per customer, no total cap, no minimum, no expiry (the roadmap defaults) | Keeps their meaning | Edit in admin |
| E7 | Support email and WhatsApp number | Placeholders, read from `VITE_SUPPORT_EMAIL` / `VITE_WHATSAPP_NUMBER` | Not supplied | Set two env vars |
| E8 | Money column naming | Every legacy Decimal column gets a twin named `<column>_paise`. The roadmap's "subtotal / discount / shipping / tax / unit price / line total" are therefore `sub_total_paise`, `saved_paise`, `shipping_amount_paise`, `tax_fee_paise`, `price_paise`, `total_paise`. No second set of differently-named columns was added | Two columns for one number is a drift risk; one naming rule makes the mirror check mechanical | Low |
| E9 | Mirror writes (A5) | Enforced in `save()` of Cart, CartOrder and CartOrderItem (`store/money_mirror.py`): whichever side is written, the other follows; paise wins if both change | Legacy code, Django admin and old fixtures still write Decimal only | Low |
| E10 | "Do not touch vendor-named code" vs the roadmap's dashboard requirements | `backend/vendor/` is **untouched**. The dashboard price edit reaches the variant through a signal on `Product`; `stock_qty` is made read-only in the serializer. In `frontend/src/views/vendor/` only the roadmap-mandated minimum was changed: "$" to rupees, ledger availability instead of `stock_qty`, and a JS bug that blocked editing any product whose stock was 0. Nothing renamed or removed | Both instructions satisfied | Low |
| E11 | Shipping on order lines | Shipping is one charge per order. `CartOrderItem.shipping_amount` is 0 from G1 on, so the dashboard's revenue figure (`sub_total + shipping_amount` per line) no longer includes shipping | The flat fee cannot be honestly split across lines | Low |
| E12 | Tax base for the carve-out | The whole payable total (goods after discount, plus shipping). Rate is 0 today, so nothing is affected | Needs a CA's confirmation before the rate is ever set (see Known gaps) | One line |
| E13 | Abandoned drafts and coupon caps | A redemption counts while its order is alive and still carries that coupon. Unpaid drafts are expired by a new hourly job after `ORDER_DRAFT_TTL_HOURS` (48), which frees stock, coupon and cart. Card payment is refused for a draft older than TTL minus 25 h | Otherwise an abandoned checkout holds a customer's one coupon use forever | Low |
| E14 | A cart is one cart id | `cart-list` and `cart-detail` now both return exactly the lines of the given cart id (which is what an order is created from). Previously the list merged every cart the user ever had and the totals covered a different subset | The cart, its totals and the order must agree | Low |
| E15 | Stock for dashboard-created products | The `stock_qty` typed when a product is **created** becomes its opening batch in the ledger (as the F-B backfill did). After that, stock is added by adding a Batch in Django admin, which now books the quantity into the ledger | F-B left no way to receive stock from a UI | Low |
| E16 | Seed coupon | `seed_noore` also creates `WELCOME10` (10% off, one per customer) for local testing | The smoke suite needs a coupon | Delete it |

---

## Decisions taken on the owner's behalf (4 Oct 2026, phase G4.5)

The owner supplied a v0 export (`noore-ecommerce-v0-storefront.zip`) and asked for it to be
joined to this backend.

| # | Question | Decision | Why | Cost to reverse |
|---|---|---|---|---|
| J1 | Use the v0 app itself, or its design? | **Its design, ported into the existing storefront.** The v0 export is a Next.js 16 / React 19 mock: every product, price, cart line, order and address in it is hard-coded, nothing calls an API, and it has no product page, no shop page, no search and no account-link page. Wiring it up would have meant rewriting all the store logic in a second framework and running a second server. Instead its colours, type, layout and components were rebuilt on the pages that already work | Keeps the cart, coupons, Razorpay, COD, reviews, reorder, the tests and the deploy setup | Medium |
| J2 | Styling technology | Tailwind CSS 4 (what v0 uses) added to the Vite app. One theme file, `frontend/src/theme/noore.css`, holds every colour and typeface as named tokens; no component contains a hex code | The roadmap asks for one theme file so the skin can change without touching components | Low |
| J3 | Bootstrap | No longer loaded on every page. It is loaded only while the admin area or one of the few un-redesigned account pages is open (`layouts/LegacyStyles.jsx`) | Otherwise Bootstrap restyles the new storefront | Low |
| J4 | v0's numbers and claims | Not used. v0 shows free shipping above Rs 2,500, Rs 180 shipping, a NOORE10 code, a newsletter, a journal, Instagram and Pinterest, and says the candles are "natural soy wax", "cotton wick" and "made in India". The storefront shows the real shipping figures from the server, has no newsletter or journal (nothing behind them), and makes no ingredient or origin claim | Shipping must match what checkout charges; product claims are the owner's to make and stand behind | Add copy when supplied |
| J5 | Logo and favicon | The v0 export's icon files are v0's own logo, so they were not used. The logo is the wordmark "NOORE" in the design's serif; the favicon is a simple "N" on the brand's dark colour (`frontend/public/favicon.svg`) | No Noore logo file was supplied | Replace one file |
| J6 | "Do not touch vendor-named code" | Lifted for this phase only as far as the roadmap's G4.5 requires, since the owner started G4.5 by sending the design. Dashboard files were **not** renamed or moved: the routes moved to `/admin-area/`, and old `/vendor/...` and `/owner/...` addresses redirect staff there. `backend/vendor/` is untouched | Smallest change that meets the acceptance | Low |
| J7 | Who is staff, in the browser | The sign-in token now carries `is_staff`. It only decides whether the "Admin" link is shown; every owner endpoint still checks the database | The header needs to know without an extra request | Low |
| J8 | The public "shop by seller" page (`/vendor/<slug>/`) | No longer routed. It is a marketplace page with no place in a single-brand store | Roadmap R21 | Re-add one route |
| J9 | Pages not redesigned | Wishlist, account settings, notifications, forgot/reset password, and the legacy Stripe success and invoice pages keep their old Bootstrap look inside the new header and footer. The whole admin area keeps its look | v0 gave no design for most of them; they work | Per page |

---

## PHASE G4.5 — Brand and storefront (COMPLETED, with placeholders listed)

### 1. PHASE COMPLETED

**G4.5**, branch `phase/G4.5-brand`.

- **The storefront now looks like Noore**: cream, ink and clay palette, serif headings, the v0
  layout for header, footer, home, cart, checkout, order pages and forms.
- **New pages**: home (hero, collection, story strip, shipping and payment facts), shop with
  search and sorting, About, a proper not-found page.
- **Redesigned pages**: product (photo gallery with thumbnails, size picker, price, stock,
  reviews), cart, checkout, order confirmation, sign in, register, create-account link, sign
  out, my orders, order detail (with progress steps), policies, contact.
- **Listing photos share one ratio** (4:5) and a missing photo shows a plain block, never a
  broken-image icon.
- **No marketplace wording**: the header "Vendor" menu, seller names, the seller tab and seller
  shop links are gone from everything a shopper can reach.
- **Admin area**: the dashboard lives at `/admin-area/`. Staff see one "Admin" link. Everyone
  else sees no dashboard link, and dashboard addresses show the not-found page.
- **Bug D17 fixed**: an ordinary customer is never sent to a shop sign-up page.
- **Title, favicon and description** are Noore's.

### 2. FILES CREATED

- `frontend/src/theme/noore.css` — the one theme file
- `frontend/postcss.config.js`, `frontend/public/favicon.svg`
- `frontend/src/layouts/LegacyStyles.jsx`
- `frontend/src/views/ui/noore.jsx` — `PageIntro`, `BackLink`, `Field`, `Loading`, `Photo`, `ProductCard`
- `frontend/src/views/base/NotFound.jsx`, `frontend/src/views/policy/About.jsx`
- `frontend/e2e/brand.spec.js`

### 3. FILES MODIFIED

- `frontend/index.html` — title, description, favicon; Bootstrap no longer loaded globally
- `frontend/src/main.jsx`, `frontend/src/App.jsx` (rewritten: storefront, legacy and admin-area layouts and routes)
- `frontend/src/views/base/StoreHeader.jsx`, `StoreFooter.jsx` (rewritten)
- `frontend/src/views/shop/home.jsx`, `Products.jsx` (rewritten as home and shop), `ProductDetail.jsx`, `Cart.jsx`, `Checkout.jsx`, `OrderConfirmation.jsx` (same logic, new markup)
- `frontend/src/views/auth/login.jsx`, `register.jsx`, `logout.jsx`, `ClaimAccount.jsx`
- `frontend/src/views/customer/Orders.jsx`, `OrderDetail.jsx`, `BuyAgainButton.jsx`
- `frontend/src/views/policy/PolicyPage.jsx`, `Contact.jsx`
- `frontend/src/store/auth.js` — `is_staff`, `full_name`
- `frontend/package.json`, `package-lock.json` — `tailwindcss`, `@tailwindcss/postcss`, `postcss` (dev), `lucide-react`
- `frontend/playwright.config.js`, `frontend/e2e/storefront.spec.js`, `frontend/e2e/checkout.spec.js` — new button and field names
- `backend/userauths/serializer.py` — `is_staff` claim in the sign-in token
- `backend/tests/test_launch.py` — test for that claim

No longer routed, left in place (removal proposals, rule 4): `views/shop/Search.jsx`,
`views/vendor/Shop.jsx`, `views/auth/private.jsx`, `views/auth/dashboard.jsx`.

### 4. MIGRATIONS ADDED

None.

### 5. ENV VARS ADDED

None. (`VITE_STORE_NAME`, `VITE_SUPPORT_EMAIL` and `VITE_WHATSAPP_NUMBER` from G2 are now used throughout the header, footer and titles.)

### 6. TESTS ADDED

Playwright `frontend/e2e/brand.spec.js`, 7 tests; the whole suite is **14 passed** in real Chromium:

    npx playwright test

- A logged-out crawl follows every internal link from the home page and fails if "vendor" appears in any page's text, title, link, image description or label. It visited the home page, shop, every product, every policy, About, Contact, cart and sign-in.
- Every page has the Noore title, favicon and logo; the announcement bar shows the real free-shipping threshold.
- A signed-in customer sees no admin link, and `/admin-area/...`, `/vendor/...` (including `/vendor/register/`) and `/owner/...` all show the not-found page without redirecting.
- A signed-out visitor gets the not-found page for the same addresses.
- Staff click "Admin", land on `/admin-area/dashboard/`, open all eleven dashboard screens without a script error, and old `/vendor/...` and `/owner/...` addresses redirect to the new ones.
- Home, About, shop and product page at phone width (390) and desktop width (1280): a heading is visible, nothing overflows sideways, and listing photos share the 4:5 ratio.

The existing 7 browser tests (pricing, COD, Razorpay hand-off, owner flow, reorder, review) pass unchanged in behaviour against the new pages.

Backend: 1 new test (the staff claim, and that the API does not trust it).

    python -m pytest -q   ->  178 passed, 2 skipped (180 collected)

Shown failing first: before this phase `brand.spec.js` fails on its first assertions (the page title was "Django React Ecommerce", the header had a "Vendor" menu, `/admin-area/` did not exist).

### 7. MANUAL VERIFICATION STEPS

    cd backend
    .\venv\Scripts\Activate.ps1
    python -m pytest -q
    python manage.py runserver

    cd frontend
    npm install
    npm run build
    npm run dev

`npm install` is required: Tailwind and the icon set are new.

1. http://localhost:5173 : the Noore home page. Open a candle, pick a size, add to bag, go through checkout.
2. Shrink the window to phone width: the menu collapses, nothing scrolls sideways.
3. Sign in as an ordinary customer: no "Admin" link. Type `/vendor/dashboard/` in the address bar: not-found page.
4. Sign in as the owner: "Admin" appears in the header and opens `/admin-area/dashboard/`.
5. To change the look: edit a colour in `frontend/src/theme/noore.css` (for example `--color-clay`) and every page follows.

### 8. ASSUMPTIONS MADE

1. Decisions J1 to J9.
2. Fonts are the design's system fonts (Georgia for headings, Arial for text); no web font is downloaded.
3. The home page hero uses the first featured product's photo; "the collection" shows up to eight featured products, or all products if none is featured.
4. Listing cards link to the product page ("Choose a size"); adding to the bag happens there, where the size is chosen.
5. The product page shows details and reviews stacked on one page instead of in tabs.
6. Search lives at `/shop?query=`; the old `/search?query=` address still works.
7. The wishlist button on the product page is shown only to signed-in customers.
8. "My orders" shows a plain-language status (Placed, Being packed, On its way, Delivered, Cancelled, Refunded).
9. API addresses still contain the word "vendor" (for example `/api/v1/vendor/...`). They are visible only in the browser's network tab; the roadmap makes renaming them a separate decision.

### 8b. FOLLOW-UP (4 Oct 2026): the shop sign-up redirect

Reported by the owner: opening `/admin-area/product/new/` as a freshly created superuser
landed on a "Register Vendor Account" form. Cause: fifteen dashboard pages still carried the
marketplace line `if (vendor_id === 0) window.location.href = '/vendor/register/'`, and a new
superuser does not own the shop until `claim_shop` is run. G4.5 had stopped ordinary customers
reaching that form, but not staff.

- The redirect is removed from all fifteen pages, and the shop sign-up route is gone
  (`views/vendor/VendorRegister.jsx` stays in the repo as a removal proposal, rule 4).
- A staff account with no shop now gets `views/owner/ShopNotReady.jsx`, which names the
  `claim_shop` command, instead of any form. The owner-order and review screens, which need no
  shop, still open.
- Every dashboard link now points at `/admin-area/...` directly, so clicking no longer bounces
  through a redirect. Old addresses typed by hand still redirect staff.
- New browser test: a staff account whose token says it owns no shop sees the explanation, stays
  on the address it asked for, and never sees a sign-up form. Suite: 15 passed.

### 9. KNOWN GAPS

- **About page and policy pages are placeholder copy** and say so on the page.
- **No real logo, favicon artwork or product photos.** The seeded products have no photo, so listings show plain blocks until photos are uploaded.
- **Home page marketing lines** ("Light the beautiful moment", "Made for the in-between") come from the v0 design; replace them if they are not the brand's voice.
- Wishlist, account settings, notifications, password reset and the whole admin area are not redesigned (J9). Inside the admin area, Bootstrap pages sit under the Noore header; their look differs slightly from before because Bootstrap is now loaded on demand.
- The admin area's own links still point at `/vendor/...` and redirect; there is a brief flash on each click.
- No newsletter, journal or social links (J4).
- The built CSS and JS are larger than before (one bundle for storefront and admin area).

### 10. NOT DONE AND WHY

- **Using the v0 Next.js project as the frontend**: J1.
- **Renaming or deleting dashboard files, or renaming API paths**: rule 4 and the roadmap's stop condition.
- **Redesigning the admin area**: not in the roadmap.
- **Real copy, logo and photos**: the owner supplies them.

---

## Decisions taken on the owner's behalf (3 Oct 2026, phase G5 part A)

The owner said to continue. G4.5 is still on hold (it needs the design decision and assets), so
this session built every part of G5 that needs nothing from the owner. The rest of G5 ("part B")
needs a domain, a server, live Razorpay keys and an email provider.

| # | Question | Decision | Why | Cost to reverse |
|---|---|---|---|---|
| H1 | Error reporting | Emails to `ERROR_REPORT_EMAILS` from a small handler in `core/error_email.py`: masked message and traceback only, one email per distinct error per five minutes. No third-party service, no new dependency | Django's built-in error email includes the request body and settings, which would leak customer data; a hosted service needs an account the owner has not chosen | Swap the handler |
| H2 | Shared cache | Django's database cache, on by default when `DEBUG` is off. Needs `createcachetable` once | The roadmap names it; no Redis to run | One env var |
| H3 | HSTS | On in production, starting at one hour. Raising it to a year is a runbook step | It cannot be undone quickly if HTTPS breaks | One env var |
| H4 | Link previews for product pages | In production the web server sends `/detail/<slug>` to Django, which returns the built storefront page with the product's title, description, price and image in the `<head>` | The storefront is a single-page app; without this every shared link previews as a blank generic page | Remove one route |
| H5 | Health check | `GET /api/v1/health/`; `?strict=1` also fails when the worker has not finished a job for five minutes | A dead worker silently stops emails and payment reconciliation | Low |
| H6 | `npm audit` | Applied every non-breaking fix and moved `react-router-dom` 6.10.0 to 6.30.6 (same major). 56 findings became 39. The remaining ones need major upgrades and are listed under Known gaps | The suite and build pass after the changes | `git revert` |
| H7 | Swagger / ReDoc pages | Left in place. In production the web server does not route to them, so they are not reachable | Rule 4: not removed without approval | n/a |
| H8 | Deployed-site smoke test | `E2E_BASE_URL=https://... npx playwright test` runs only `e2e/production.spec.js`, which needs no seed data and places one COD order named "SMOKE TEST - please cancel" | The roadmap's "Playwright against production with a COD order that is then cancelled" | Low |

---

## PHASE G5 (part A) — Launch preparation (COMPLETED; part B needs the owner)

### 1. PHASE COMPLETED

**G5 part A**, branch `phase/G5a-launch-prep`. Everything in G5 that does not need a domain,
server, live keys or the owner's accounts.

- **Production settings**: HTTPS redirect, secure cookies, HSTS, proxy-aware scheme, clickjacking
  protection. Django's own deployment check passes.
- **PostgreSQL proven**: the whole suite passes on PostgreSQL 16.2 with nothing skipped, including
  the two concurrency tests that had never been run (stock for the last unit; a capped coupon).
- **Rate limits shared between server processes** (bug D14).
- **Deployment files** in `deploy/`: Caddy configuration, systemd units for web, worker and the
  nightly backup, backup and restore scripts, a production env template.
- **Backups**: nightly database and media, 14 days kept, off-site copy when configured; a restore
  script that restores into a scratch database and prints row counts.
- **Health check** for uptime monitors, **error emails** with personal data masked.
- **Search engines and sharing**: `robots.txt`, `sitemap.xml`, per-page browser titles, and
  product links that preview with the product's own title, price and image.
- **`npm audit`** triaged (bug D16): 56 findings down to 39.
- **Runbook** `docs/DEPLOY.md`: install, deploy, roll back, back up, restore, rotate a secret,
  monitor, go-live checklist.
- A **deployed-site smoke test**.

### 2. FILES CREATED

- `backend/core/health.py`, `backend/core/seo.py`, `backend/core/error_email.py`
- `backend/tests/test_launch.py`
- `deploy/Caddyfile`, `deploy/noore-web.service`, `deploy/noore-worker.service`, `deploy/noore-backup.service`, `deploy/noore-backup.timer`
- `deploy/backup.sh`, `deploy/restore.sh`, `deploy/backup.env.example`, `deploy/env.production.example`
- `docs/DEPLOY.md`
- `frontend/src/utils/usePageTitle.js`, `frontend/e2e/production.spec.js`

### 3. FILES MODIFIED

- `backend/backend/settings.py` — production security block, `CACHES`, error-report logging handler, `WORKER_STALE_AFTER_SECONDS`, `FRONTEND_INDEX_PATH`
- `backend/backend/urls.py` — `/robots.txt`, `/sitemap.xml`, `/detail/<slug>`
- `backend/api/urls.py` — `/api/v1/health/`
- `backend/.env.example` — the new variables
- `frontend/playwright.config.js` — `E2E_BASE_URL` mode
- `frontend/package.json`, `frontend/package-lock.json` — security updates (H6)
- `frontend/src/views/shop/ProductDetail.jsx`, `Cart.jsx`, `Checkout.jsx`, `OrderConfirmation.jsx`, `frontend/src/views/policy/PolicyPage.jsx`, `Contact.jsx` — page titles

### 4. MIGRATIONS ADDED

None. One new setup command for production only, which creates the cache table (it is not a
Django migration and holds no business data):

    python manage.py createcachetable

Undo: `DROP TABLE django_cache;` and set `DJANGO_CACHE=locmem`.

### 5. ENV VARS ADDED

Backend, all optional except where marked: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
`SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`, `DJANGO_CACHE`,
`ERROR_REPORT_EMAILS` (**needs the owner's address in production**),
`ERROR_REPORT_MIN_INTERVAL_SECONDS`, `WORKER_STALE_AFTER_SECONDS`, `FRONTEND_INDEX_PATH`
(set in production).

Deployment: `SITE_ADDRESS`, `APP_ROOT` (Caddy); `BACKUP_DIR`, `MEDIA_DIR`, `BACKUP_KEEP_DAYS`,
`BACKUP_REMOTE` (**needs the owner's value**), `ADMIN_DATABASE_URL` (restore script).

Smoke suite: `E2E_BASE_URL`.

### 6. TESTS ADDED

`backend/tests/test_launch.py`, 12 tests. Shown failing first: against the G3/G4 commit, 11 fail
and 1 passes (the one that only checks development keeps its cache).

    python -m pytest tests/test_launch.py -q   ->  12 passed
    python -m pytest -q                        ->  177 passed, 2 skipped   (SQLite; 179 collected)

On PostgreSQL 16.2 (local server in the build container):

    $env:DATABASE_URL = "postgres://ecom:ecom@127.0.0.1:5432/ecom"
    python -m pytest -q                        ->  179 passed, 0 skipped

Covers: production settings are secure by default and `manage.py check --deploy --fail-level
WARNING` passes; rate-limit counters are stored in the shared database cache and a sixth request
is refused; errors are emailed once, masked, and a broken mail server never raises; the health
check for database, cache and worker, and it is never rate-limited; `robots.txt` hides private
areas; the sitemap lists published products and public pages only; product pages get escaped
title, description, canonical link, price and image, the app still boots, and unknown or
unpublished products get the plain page.

Playwright: 7 passed (local suite). Deployed-site spec: 2 passed against the local
production-like stack through Caddy.

### 7. MANUAL VERIFICATION STEPS

Nothing changes in day-to-day development; the usual commands still work. To see the new pieces:

    cd backend
    .\venv\Scripts\Activate.ps1
    python -m pytest -q
    python manage.py runserver

Then open http://127.0.0.1:8000/api/v1/health/ , http://127.0.0.1:8000/robots.txt and
http://127.0.0.1:8000/sitemap.xml . With the worker running in a second terminal,
http://127.0.0.1:8000/api/v1/health/?strict=1 answers ok; stop the worker, wait five minutes, and
it answers 503.

Production is in `docs/DEPLOY.md`.

**Drills run in the build session** (local production-like stack, scratch data):

| Drill | Result |
|---|---|
| Caddy configuration | `caddy validate`: valid. Storefront, deep links, API, admin, static, `/detail/...`, `robots.txt`, `sitemap.xml` all 200; a missing asset 404 |
| Stop web and worker | health check 502; started again, `?strict=1` ok |
| Backup | 0.53 s; database dump 200 KB, media 3.4 MB |
| Restore into a scratch database | under 1 s; products 3, variants 9, orders 1, stock movements 9, audit rows 18, migrations 88, identical to the live counts |

These are on a tiny scratch database on the build machine. They prove the scripts work; they are
**not** the production restore drill the roadmap requires. That is done on the real server.

### 8. ASSUMPTIONS MADE

1. Decisions H1 to H8.
2. One server, Ubuntu 24.04, paths under `/srv/noore`, service user `noore`, PostgreSQL on the same machine, Caddy in front.
3. Media stays on the server's disk (roadmap A7) and is in the nightly backup.
4. The off-site copy uses `rclone`, so the owner can choose any storage provider.
5. The sitemap has no last-modified dates (products record only a creation date).
6. Link-preview pages are produced only for published products; anything else gets the unchanged app page.
7. `og:image` is the product's main image at its uploaded size.
8. The health check exposes only booleans and one number; nothing secret or personal.
9. Gunicorn runs 3 workers; a small VPS is assumed.
10. The systemd units were written from the standard unit format and not executed (no systemd in the build container).

### 9. KNOWN GAPS

- **Not deployed.** No domain, server, HTTPS certificate, live keys or real email were available. `docs/DEPLOY.md` ends with exactly what is and is not proven.
- **`npm audit`: 39 findings remain**, none in what a shopper's browser can be attacked through as far as the advisories describe:
  - 34 in the CKEditor 40 packages (and `lodash-es` beneath them). The editor is used only on the owner's add/edit product screens. The offered fix is a major downgrade to version 39; the real fix is an upgrade to a current CKEditor, which is its own piece of work.
  - `vite` 4 and `esbuild` (5 findings): development-server issues. They do not ship in the built site. The fix is a major upgrade to Vite 8.
  - `react-router` 6 (2 moderate): an open redirect through a backslash in a link target, and a server-rendering issue. This app does not server-render and never builds a link from user-typed text. The fix is a major upgrade to version 7.
- The Swagger and ReDoc pages still exist (H7).
- No CDN and no image resizing; product photos are served as uploaded.
- Throttle counters in the database cache are not cleaned up automatically beyond Django's own culling (300 entries by default).
- `CLAUDE.md` remains the owner's unchanged copy.

### 10. NOT DONE AND WHY (G5 part B, needs the owner)

- Buying the domain; pointing DNS at a server.
- The server itself, and running `docs/DEPLOY.md` on it.
- Razorpay live keys, the live webhook, and one real order paid, dispatched, delivered and refunded.
- Email provider, SPF and DKIM; confirming mail lands in an inbox.
- The off-site backup destination, and the restore drill on production data with timings.
- A reboot test on the real server.
- Final photos, prices, MRP, weights, policy copy; real unit cost on each batch (bug D15).
- The CA or lawyer's answers on product declarations, published contact details and privacy.
- G4.5 branding: still waiting for the design decision.

---

## Decisions taken on the owner's behalf (3 Oct 2026, phases G3 and G4)

The owner's instruction: "you just start building", and to combine phases. G3 and G4 were
built together in one session. G4.5 (branding) and G5 (launch) were not started: G4.5 was
explicitly put on hold by the owner and needs a design decision, G5 needs a domain and a server.

| # | Question | Decision | Why | Cost to reverse |
|---|---|---|---|---|
| F1 | Razorpay documentation (rule 12) | Read from Razorpay's own published pages on 3 Oct 2026, not from memory: `razorpay.com/docs/developer-tools/integrations/standard-checkout` (create order, checkout options, payment signature, payment states, webhook events) and `razorpay.com/docs/webhooks/validate-test` (webhook signature, `x-razorpay-event-id`, tunnel advice). The sources and every shape used are listed at the top of `backend/store/payments/razorpay.py` | The owner said to start; the roadmap allows "current official documentation pages" | n/a |
| F2 | Which event means "paid" | `payment.captured` only. The documentation calls `captured` the state in which it is "safe to deliver". `payment.authorized`, `order.paid` and every other event are acknowledged and ignored | Unambiguous in the documentation | One constant |
| F3 | Webhook handling | Verified and applied inside the request, in one database transaction, with no call out to Razorpay (so it answers well inside Razorpay's 5-second limit and does not depend on the worker). The documentation's "discard events older than 5 minutes" is **not** applied: it would also discard Razorpay's own retries after any downtime. Replay is prevented instead by claiming each Razorpay order id exactly once | A customer who has paid must not be stranded by a slow or restarted server | Low |
| F4 | Fields read from the webhook | `payload.payment.entity.{id, order_id, amount, currency}`. If any is missing the event is refused (400) rather than guessed; the reconcile job then confirms the order from the Fetch Order API, whose response shape is fully documented | Fail closed | Low |
| F5 | Capture | Orders are created with `"capture": "automatic"` (a documented Create Order parameter) so an authorised payment is captured without relying on a dashboard setting | An uncaptured payment is auto-refunded by Razorpay | One line |
| F6 | "UPI first inside the Razorpay window" | **Not done.** The pages read do not describe how to order payment methods, and nothing was invented. Razorpay's default order is used | Rule 12 | Add when the owner supplies that page |
| F7 | Owner screens | New pages under `frontend/src/views/owner/` and new endpoints under `/api/v1/owner/` (in `backend/store/owner_views.py`). `backend/vendor/` is untouched; `vendor/Sidebar.jsx` gained two links. The old "Orders" screen still lists paid orders only, so the new "Handle orders" screen is the one to use | COD orders awaiting cash never appeared on the old screen | Low |
| F8 | Late payment with no stock left | The order is marked paid (the money really was received) **and** flagged `needs_attention`; a flagged order cannot be shipped until the owner clears the flag. A payment for an order that had already expired or been cancelled is flagged and left expired/cancelled | "Never silently marked paid and unshippable" | Low |
| F9 | A finished order and the browser's cart id | Once an order is paid or placed as COD, the same browser cart starts a new order. Previously the cart id stayed tied to the paid order and the next checkout was refused | The storefront keeps one cart id per browser | Low |
| F10 | Customer order history | Shows paid, COD awaiting cash, refunded and cancelled orders. Unpaid checkout drafts are not shown | A COD order was invisible to its own customer | Low |
| F11 | Guest account link when the email already has an account | The verified guest orders are attached to that account, but its password is **not** changed by the link | The link proves the mailbox, but silently resetting a password is what "forgot password" is for | Low |
| F12 | Reorder | Signed-in owner of the order only. A guest order's id alone cannot be used to copy its contents; the guest creates an account first | The order id is a checkout capability, not an identity | Low |
| F13 | Rejected reviews | Stay in the database (status REJECTED) and still count as that customer's one review for the product | Stops a rejected spammer simply re-posting | Low |
| F14 | Review-request email | Sent once, `REVIEW_REQUEST_DELAY_DAYS` after **every line** of the order is delivered, to guests as well (who are pointed at their orders page and the account link) | "Once per order" | Low |
| F15 | Smoke-suite accounts | `python manage.py seed_e2e` creates an owner and a customer with a fixed throwaway password. It refuses to run unless DEBUG is on **and** the database file is `e2e.sqlite3` | The suite must sign in; a known password must never reach a real database | Delete the command |

---

## PHASE G4 — Reviews and one-tap reorder (COMPLETED)

### 1. PHASE COMPLETED

**G4**, built together with G3 on branch `phase/G3-G4-payments-reviews`.

- **Verified reviews.** Only a signed-in customer with a delivered line for the product can
  review it, once. The product page shows the form only to them and tells everyone else why not.
- **Moderation.** New reviews wait in the owner's "Review moderation" screen. Only approved
  reviews are public or count towards the star rating. The screen says rejecting is for abuse
  and spam, not low ratings. Each decision is audited.
- **Existing reviews** were marked approved by a migration, so nothing vanished.
- **One review-request email** per order, 7 days after delivery. No reminders.
- **Buy again** on the order list and order page: puts the order's items back in the cart at
  today's prices and stock, says what was reduced or unavailable, and opens the cart. It never
  places an order.

### 2. FILES CREATED

- `backend/store/migrations/0037_review_moderation_fields.py`, `0038_approve_existing_reviews.py`, `0039_review_one_per_user_per_product.py`
- `backend/tests/test_reviews_reorder.py`
- `frontend/src/views/owner/OwnerReviews.jsx`
- `frontend/src/views/customer/BuyAgainButton.jsx`

### 3. FILES MODIFIED

- `backend/store/models.py` — `Review.order_item`, `status`, `moderated_by`, `moderated_at`, unique rule; rating and count use approved reviews only; `active` follows `status`
- `backend/store/views.py` — `review_eligibility`, `ReviewEligibilityView`, review creation rules, public list of approved reviews only, `put_in_cart` (the shared cart path), `ReorderView`
- `backend/store/owner_views.py` — moderation queue and approve/reject
- `backend/store/jobs.py` — `store.queue_review_requests` (hourly)
- `backend/store/emails.py` — the review-request email
- `backend/store/admin.py` — review status column and filter
- `backend/api/urls.py`, `backend/backend/settings.py`, `backend/.env.example`
- `backend/conftest.py` — `delivered_order` fixture; `backend/tests/test_security.py` — the review test now gives the reviewer a delivered order
- `frontend/src/views/shop/ProductDetail.jsx`, `frontend/src/views/customer/Orders.jsx`, `OrderDetail.jsx` (also fixes a hard-coded order number in its heading), `frontend/src/App.jsx`, `frontend/src/views/vendor/Sidebar.jsx`

### 4. MIGRATIONS ADDED

| Migration | What | Reverse |
|---|---|---|
| `store.0037_review_moderation_fields` | four columns on Review | drops them |
| `store.0038_approve_existing_reviews` | existing reviews become APPROVED | back to PENDING |
| `store.0039_review_one_per_user_per_product` | checks for duplicates (stops with a clear message if any), then adds the unique rule | removes the rule |

Apply: `python manage.py migrate`. Roll back G4 only: `python manage.py migrate store 0036`.
Verified on a copy of the supplied database (2 reviews, both approved after apply, both kept after rollback).

### 5. ENV VARS ADDED

- `REVIEW_REQUEST_DELAY_DAYS` (optional, default `7`)

### 6. TESTS ADDED

`backend/tests/test_reviews_reorder.py`, 9 tests. Shown failing first against the G2 commit
(`ImportError: cannot import name 'queue_review_requests'`).

    python -m pytest tests/test_reviews_reorder.py -q   ->  9 passed

Covers: no delivered line gives 403 (never bought, not yet delivered, someone else's order);
pending and rejected reviews are never public and never move the average; a low rating that
is approved does move it; a second review is refused (API and database); moderation is staff
only and audited; the eligibility answer for each case; one review-request email, not before
the delay; reorder of a three-line order with one line sold out adds two and reports the
third, at today's prices, holding stock, placing no order, safe to press twice; short stock is
reduced and a discontinued variant is skipped; reorder is refused for other users and guests.

Playwright: the reorder-from-order-history scenario is the last part of
`frontend/e2e/checkout.spec.js` (see G3, section 6).

### 7. MANUAL VERIFICATION STEPS

After the G3 steps below: sign in as a customer whose order you delivered, open the product,
Review tab, submit. It does not appear. As the owner open Review moderation, approve it; it
appears and the stars update. On My Orders press Buy again; the cart opens with today's prices.

### 8. ASSUMPTIONS MADE

1. Decisions F12 to F14.
2. "Delivered line" means an order line with delivery status Delivered on an order that is not cancelled and belongs to the signed-in user.
3. Editing or deleting one's own review is not offered.
4. Reorder sets each line to the order's quantity (it does not add to what is already in the cart).
5. The legacy vendor review screens still work but are not the moderation queue.

### 9. KNOWN GAPS

- No reply-to-review and no photos.
- The review-request email needs the worker running.
- Django admin can still change a review's status directly (it is then not written to the audit log).

### 10. NOT DONE AND WHY

- Review reminders: the roadmap says none.
- Reorder placing the order itself: the roadmap forbids it.

---

## PHASE G3 — Razorpay test mode and COD (COMPLETED)

### 1. PHASE COMPLETED

**G3**, branch `phase/G3-G4-payments-reviews`.

- **Checkout has a payment choice**: "UPI / Card / Netbanking" (default, Razorpay) or "Cash on delivery". No COD fee.
- **Online payment.** The server creates the Razorpay order for the stored total, the browser
  opens Razorpay, and the customer lands on a "Confirming your payment" page. The order becomes
  paid **only** when Razorpay's signed server notification (webhook) arrives, with the right
  amount and currency. A forged, repeated or mismatched notification changes nothing.
- **Safety net.** A background job asks Razorpay about orders still unconfirmed after 3 minutes, so a missed webhook cannot strand a paid order.
- **Cash on Delivery.** The order is placed with nothing charged and its stock kept. The owner
  presses **Confirm COD** after speaking to the customer; only then can it be shipped. On
  delivery the owner presses **Mark cash collected**.
- **Owner "Handle orders" screen**: confirm COD, add courier and tracking, mark packing / shipped / arrived / delivered, cancel, record a refund. Stock leaves the ledger exactly once, on dispatch.
- **Order emails**, each sent once: order placed, payment received, shipped (with tracking), cancelled.
- **Guests can create an account** from the confirmation page; the link goes to the order's email and attaches that email's orders once used.
- **Stripe and PayPal** are switched off (code and tests remain).
- `CartOrder.oid` is now unique (bug D12).

### 2. FILES CREATED

- `backend/store/payments/__init__.py`, `base.py`, `razorpay.py`, `legacy.py`
- `backend/store/payment_views.py`, `backend/store/owner_views.py`
- `backend/store/emails.py`, `backend/store/account_claim.py`
- `backend/templates/email/order_update.txt`, `order_update.html`
- `backend/store/migrations/0035_cartorder_payment_fields.py`, `0036_cartorder_oid_unique.py`
- `backend/core/management/commands/seed_e2e.py`
- `backend/tests/test_payments.py`
- `frontend/src/utils/razorpay.js`
- `frontend/src/views/shop/OrderConfirmation.jsx`, `frontend/src/views/auth/ClaimAccount.jsx`
- `frontend/src/views/owner/OwnerOrders.jsx`, `OwnerOrderDetail.jsx`
- `frontend/e2e/checkout.spec.js`

### 3. FILES MODIFIED

- `backend/store/models.py` — `payment_provider`, `razorpay_order_id`, `razorpay_payment_id`, `cod_confirmed_at`, `cod_confirmed_by`, `needs_attention`, `delivered_at`; `oid` unique
- `backend/store/order_state.py` — `place_cod_order`, `confirm_cod`, `advance_order_delivery`; paid-with-no-stock sets `needs_attention`
- `backend/store/views.py` — Stripe and PayPal refuse unless enabled; a finished order frees the cart (F9)
- `backend/store/jobs.py` — `store.reconcile_pending_payments` (every 2 minutes)
- `backend/customer/views.py` — order history shows placed orders (F10)
- `backend/store/apps.py`, `backend/store/admin.py`, `backend/api/urls.py`, `backend/backend/settings.py`, `backend/.env.example`
- `backend/conftest.py` — `legacy_providers` fixture; `backend/tests/test_security.py`, `backend/tests/test_pricing.py` — the five Stripe/PayPal tests switch those providers on
- `frontend/src/views/shop/Checkout.jsx` — payment-method selector, Razorpay hand-off, COD
- `frontend/src/App.jsx`, `frontend/src/views/vendor/Sidebar.jsx`
- `frontend/playwright.config.js`, `frontend/e2e/storefront.spec.js`

### 4. MIGRATIONS ADDED

| Migration | What | Reverse |
|---|---|---|
| `store.0035_cartorder_payment_fields` | seven columns on CartOrder | drops them |
| `store.0036_cartorder_oid_unique` | checks for duplicate order ids (stops with a clear message if any), then makes `oid` unique | removes the constraint |

Apply: `python manage.py migrate`. Roll back G3 and G4: `python manage.py migrate store 0034`.
Verified on a copy of the supplied database: no duplicate order ids; apply, roll back, re-apply clean.

### 5. ENV VARS ADDED

Backend (`backend/.env.example`):

- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` — **need the owner's test keys**
- `RAZORPAY_WEBHOOK_SECRET` — **needs the owner's value** (chosen when adding the webhook; not the key secret)
- `RAZORPAY_API_BASE` (default `https://api.razorpay.com`)
- `ENABLED_PAYMENT_PROVIDERS` (default `razorpay,cod`)
- `PAYMENT_RECONCILE_AFTER_MINUTES` (default `3`)
- `STORE_NAME` (default `Noore Candles`)
- `ACCOUNT_CLAIM_LINK_HOURS` (default `48`)

No frontend variable: the public key id reaches the browser from the server with each payment.

### 6. TESTS ADDED

`backend/tests/test_payments.py`, 20 tests. Shown failing first against the G2 commit
(`ImportError: cannot import name 'reconcile_pending_payments'`).

    python -m pytest tests/test_payments.py -q   ->  20 passed
    python -m pytest -q                          ->  165 passed, 2 skipped (167 collected)

No test contacts Razorpay. The HTTP call is stubbed with the documented order entity, and
webhooks are signed in the test exactly as documented.

Covers every acceptance line: a forged, unsigned or wrongly-keyed webhook is rejected and
changes nothing; the same webhook twice (and a second event for the same payment) marks paid
once and sends one email; wrong amount or currency is rejected; returning from checkout with a
valid signature leaves the order unpaid, and a signature for a spoofed order id fails; without
a webhook the order stays unpaid until the reconcile job confirms it (not when Razorpay says
unpaid or part-paid); a COD order cannot be dispatched before Confirm COD and can after; stock
leaves the ledger exactly once, prepaid and COD; Stripe and PayPal are off by default and
their own tests still pass; no secret appears in any response. Also: late payment re-reserves,
or flags the order; COD refused cleanly when stock has gone; owner endpoints are staff only;
guest account link end to end, tampered and expired links refused.

Playwright, **7 passed in real Chromium** (`npx playwright test`): the four G1/G2 tests, plus
COD checkout end to end with the guest account link; the online-payment hand-off (our server's
"start" answer and Razorpay's script are stubbed, and the options passed to Razorpay are
checked); and one long scenario: customer orders COD, owner is refused shipping, confirms COD,
ships, delivers, collects cash, customer buys again and writes a review that waits for moderation.

### 7. MANUAL VERIFICATION STEPS

    New-Item -ItemType Directory -Force -Path backups | Out-Null
    Copy-Item backend\db.sqlite3 "backups\db-$(Get-Date -Format 'yyyyMMdd-HHmmss').sqlite3"
    cd backend
    .\venv\Scripts\Activate.ps1
    python manage.py migrate
    python -m pytest -q
    python manage.py runserver

Second terminal (emails, payment reconcile, draft expiry all need this):

    cd backend
    .\venv\Scripts\Activate.ps1
    python manage.py run_worker

Third terminal: `cd frontend`, `npm install`, `npm run build`, `npm run dev`.

**Cash on Delivery (no keys needed).** Add a candle, check out, choose Cash on delivery, Place
order. Sign in as the owner, Handle orders, open it: Mark shipped is refused; Confirm COD;
Mark shipped; Mark delivered; Mark cash collected. The worker terminal prints each email.

**Razorpay test mode.**

1. Razorpay dashboard, Test Mode, Account & Settings, API Keys, Generate Key. Put the key id and secret in `backend/.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. Restart the server.
2. Razorpay needs a public HTTPS address for the webhook. Its documentation says `localhost` cannot be used, that `ngrok.io` and several other tunnel domains are blocked, and suggests **zrok**. Install zrok, enable it once with your zrok account token, then run: `zrok share public http://127.0.0.1:8000`. Copy the https address it prints.
3. Add that host to `DJANGO_ALLOWED_HOSTS` in `backend/.env` and restart the server.
4. Razorpay dashboard, Test Mode, Account & Settings, Webhooks, Add New Webhook. URL: `https://<your zrok host>/api/v1/payments/razorpay/webhook/`. Secret: a long random string, also put in `backend/.env` as `RAZORPAY_WEBHOOK_SECRET`. Event: `payment.captured`. In test mode the dashboard asks for the OTP `754081`.
5. Check out with "UPI / Card / Netbanking". In the Razorpay window use UPI id `success@razorpay`, or card `4100 2800 0000 1007` with any future expiry and CVV.
6. The page says "Confirming your payment", then "Payment received". The order is paid in Handle orders.
7. Missed-webhook check: stop zrok, pay again, wait three minutes with the worker running. The order still becomes paid.

### 8. ASSUMPTIONS MADE

1. Decisions F1 to F11 and F15.
2. A Razorpay order is created per stored total; if the total changes (coupon) a new one is created and the old one is abandoned. Retries after a failed attempt reuse the same Razorpay order, as the documentation advises.
3. The Razorpay `receipt` is the order's `oid`; `notes.order_oid` carries it too.
4. Reconcile treats a fetched order as paid only when `status` is `paid` and `amount_paid` equals the stored total in INR.
5. Checkout options sent to the browser are limited to documented ones: `key`, `amount`, `currency`, `name`, `description`, `order_id`, `prefill`, `notes`, plus the `handler`.
6. COD moves the order to payment status `pending`; delivery does not mark it paid, the owner does.
7. Shipping actions apply to every line of the order at once.
8. "Order placed" for an online payment is emailed when the customer returns from Razorpay, not when the window opens.
9. Refunds are issued in the Razorpay dashboard and recorded here by the owner; no refund API is called.
10. The account link is a signed token valid 48 hours; nothing is stored for it.
11. Nothing sensitive is logged: no signatures, secrets, webhook bodies, emails or phone numbers.

### 9. KNOWN GAPS

- **Not tested against real Razorpay.** The build container cannot reach Razorpay and has no keys. Everything is tested against the documented shapes; the owner's first test-mode payment (section 7) is the real proof. If Razorpay's webhook lacks `currency` on the payment entity, webhooks will be refused and the reconcile job will confirm payments about three minutes late: tell me and it is a one-line change.
- **PostgreSQL concurrency tests still not run** (see G1).
- **The worker must be running** for emails, the reconcile job and draft expiry.
- UPI is not forced to appear first in the Razorpay window (F6).
- No refund API, no partial refunds, no returns flow.
- The legacy "Orders" and "Order detail" dashboard screens are unchanged and show paid orders only.
- Order status can still be edited directly in Django admin, bypassing the state machine.
- `CLAUDE.md` is still the owner's unchanged copy and now lags behind G1 to G4.

### 10. NOT DONE AND WHY

- **G4.5 branding**: on hold by the owner's instruction; needs the design decision first.
- **G5 launch readiness**: needs a domain, a server and live Razorpay keys.
- **Removing Stripe/PayPal**: rule 4; switched off, not removed.

---

## PHASE G2 — Storefront basics (COMPLETED)

### 1. PHASE COMPLETED

**G2 — Storefront basics**, built on top of G1 in the same session. Branch name used
locally: `phase/G2-storefront`.

What a shopper and the owner get:

- **Size picker.** The product page shows one row of buttons per option (today: Size). Picking
  200 g shows the 200 g price, MRP, stock and SKU, and adds the 200 g candle to the cart. It
  is built from `ProductVariant.options`, so a second option such as Colour needs data only.
- **Honest price.** A struck-through MRP and "N% off" appear only when MRP is really above
  the price; the percentage is rounded down. A settings flag can later require proof from the
  recorded price history instead.
- **Price history.** Every price or MRP change, from the dashboard, Django admin or the
  shell, writes one permanent row with who did it. Rows cannot be edited or deleted.
- **Honest stock.** "In stock", "Only N left" (only when N is real and 5 or fewer) or "Sold
  out" with add-to-cart disabled. A sold-out size does not block the other sizes.
- **Shipping line** on the product page and in the cart, including "Add Rs X more for free
  shipping", computed by the pricing function.
- **Policy pages**: Shipping, Returns and Refunds, Privacy, Terms, and Contact, linked from
  the footer and from checkout. The copy is clearly-marked placeholder text.
- **Stock can no longer be typed into drift.** `Product.stock_qty` is read-only in Django
  admin and in the dashboard edit screen; both show ledger availability instead. Adding a
  Batch in admin now receives its stock.
- **`python manage.py seed_noore`**: three placeholder scents in three sizes with stock.

### 2. FILES CREATED

- `backend/catalog/display.py` — `strikethrough_for`, `lowest_prior_price`, `stock_status`
- `backend/catalog/management/__init__.py`, `backend/catalog/management/commands/__init__.py`
- `backend/catalog/management/commands/seed_noore.py`
- `backend/catalog/migrations/0003_productvariant_options.py`
- `backend/catalog/migrations/0004_backfill_variant_options.py`
- `backend/catalog/migrations/0005_pricehistory.py`
- `backend/catalog/migrations/0006_opening_price_history.py`
- `backend/catalog/tests/test_storefront.py`
- `frontend/src/views/policy/policies.js` — the placeholder copy, one place to replace it
- `frontend/src/views/policy/PolicyPage.jsx`, `frontend/src/views/policy/Contact.jsx`
- `frontend/playwright.config.js`, `frontend/e2e/storefront.spec.js`
- `docs/ROADMAP.md`, `CLAUDE.md` — the owner's uploaded copies, added to the repo unchanged

### 3. FILES MODIFIED

- `backend/catalog/models.py` — `ProductVariant.options`; new `PriceHistory`
- `backend/catalog/signals.py` — price-history signal
- `backend/catalog/admin.py` — options and MRP columns; read-only `PriceHistory` admin
- `backend/inventory/admin.py` — adding a Batch books its stock; variant and quantity read-only afterwards
- `backend/store/admin.py` — `stock_qty` read-only, ledger availability column, variants inline on the product
- `backend/store/serializers.py` — variant `options`, `stock`, `strikethrough`, `weight_grams`; product `variants` (active only), `available_qty`, `price_from_paise`; `stock_qty` ignored on update
- `backend/store/views.py` — cart line's size/colour text taken from the variant's options
- `backend/backend/settings.py`, `backend/.env.example` — three storefront settings
- `backend/pytest.ini` — `catalog/tests` added to `testpaths`
- `backend/conftest.py` — every test gets a throwaway `MEDIA_ROOT`
- `backend/.gitignore`, `frontend/.gitignore` — smoke-suite database and Playwright output
- `frontend/package.json`, `frontend/package-lock.json` — `@playwright/test` 1.56.0 (dev), `test:e2e` script
- `frontend/src/App.jsx` — `/policy/:slug`, `/contact`
- `frontend/src/utils/constants.js`, `frontend/.env.example` — support email, WhatsApp number, store name
- `frontend/src/views/shop/ProductDetail.jsx` — rewritten: picker, price, stock, shipping line; legacy Size/Color rows no longer rendered; the swapped size/colour arguments are gone
- `frontend/src/views/shop/Checkout.jsx` — policy links
- `frontend/src/views/shop/Products.jsx`, `Search.jsx` — "From Rs X", "Sold out" badge, null-safe vendor/brand
- `frontend/src/views/customer/Wishlist.jsx`, `frontend/src/views/vendor/Shop.jsx` — null-safe brand
- `frontend/src/views/base/StoreFooter.jsx` — policy links, support email, wa.me link
- `frontend/src/views/vendor/Products.jsx`, `UpdateProduct.jsx`, `AddProduct.jsx` — ledger availability; stock field read-only on edit (E10)

### 4. MIGRATIONS ADDED

| Migration | What | Reverse |
|---|---|---|
| `catalog.0003_productvariant_options` | adds `options` JSON column | drops it |
| `catalog.0004_backfill_variant_options` | fills `options` from `size` / `color` where set | empties only values it could have written |
| `catalog.0005_pricehistory` | creates `PriceHistory` | drops the table |
| `catalog.0006_opening_price_history` | one opening row per existing variant | deletes only rows labelled `system:migration` |

Apply (from `backend\`, after the backup in section 7):

    python manage.py migrate

Roll back G2 only:

    python manage.py migrate catalog 0002

Verified on a copy of the supplied database: apply, roll back, re-apply all clean; 4 opening
rows written; rollback removed the table and the column and left the 4 variants in place.

### 5. ENV VARS ADDED

Backend (`backend/.env.example`), all optional:

- `STRIKETHROUGH_REQUIRES_PRICE_HISTORY` (default `False`)
- `PRICE_HISTORY_WINDOW_DAYS` (default `30`)
- `LOW_STOCK_THRESHOLD` (default `5`)

Frontend (`frontend/.env.example`):

- `VITE_SUPPORT_EMAIL` — **needs the owner's value**; default is the placeholder `support@example.com`
- `VITE_WHATSAPP_NUMBER` — **needs the owner's value**; digits only with country code; default placeholder `910000000000`
- `VITE_STORE_NAME` (default `Noore Candles`)

Smoke suite only: `E2E_PYTHON`, `E2E_API_PORT` (8011), `E2E_WEB_PORT` (5183).

### 6. TESTS ADDED

`backend/catalog/tests/test_storefront.py`, 16 tests:

    python -m pytest catalog/tests -q        ->  16 passed
    python -m pytest -q                      ->  136 passed, 2 skipped (138 collected)

The 2 skips are the PostgreSQL-only concurrency tests (see Known gaps).

Shown failing first: the file was run against the G1 commit, where it fails at import
(`ModuleNotFoundError: No module named 'catalog.display'`), and before this phase
`catalog/tests` was not in `testpaths` at all (122 collected then, 138 now).

Covers: an opening history row per variant; exactly one row per price change with the actor
from the dashboard, from a user context and from the shell; no row for unrelated saves; rows
cannot be updated or deleted; flag off and flag on (including a short price spike that must
not manufacture a discount, and an MRP-only edit); percent rounded down; stock indicator at,
below and above the threshold and sold out; the product API per variant; 200 g adds the 200 g
variant; a sold-out variant refused while siblings are accepted; `stock_qty` not editable
from the dashboard or admin; a Batch added in admin receives stock once; `seed_noore`
refuses outside DEBUG and is idempotent.

Playwright (`frontend/e2e/storefront.spec.js`), 4 tests, **run in a real Chromium in this
session: 4 passed**:

    npx playwright test

Pick a size and add it to the cart; add to cart, apply a coupon and check INR totals in the
cart and at checkout (no "$", "USD", PayPal, tax or service-fee row); Rs 999+ ships free;
all four policy pages and the contact page open from the footer.

### 7. MANUAL VERIFICATION STEPS

Windows PowerShell, from the repo root.

    New-Item -ItemType Directory -Force -Path backups | Out-Null
    Copy-Item backend\db.sqlite3 "backups\db-$(Get-Date -Format 'yyyyMMdd-HHmmss').sqlite3"
    cd backend
    .\venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    python manage.py migrate
    python manage.py seed_noore
    python -m pytest -q
    python manage.py runserver

Second terminal:

    cd frontend
    npm install
    npm run build
    npm run dev

Then at http://localhost:5173 :

1. Open a seeded candle. Click 200 g: price Rs 799, struck Rs 949, "15% off", "In stock".
2. Add it to the cart. The cart line says "200 g" and Rs 799; the summary says shipping Rs 79
   and "Add Rs 200 more for free shipping".
3. Footer: open each of the four policies and Contact. Each policy shows the placeholder notice.
4. Django admin, Catalog, Product variants: change a price. Catalog, Price history shows one
   new row with your user. Try to edit that row: you cannot.
5. Django admin, Inventory, Batches: add a batch of 5 for a variant. Its availability rises by 5.
6. Django admin, Products: `stock_qty` is greyed out.

Smoke suite (venv activated, from `frontend\`, first time only `npx playwright install chromium`):

    npx playwright test

### 8. ASSUMPTIONS MADE

1. Option names are free text; the picker shows them as stored ("Size"). The cart line's
   legacy `size` text is taken from the option named exactly `Size`, colour from `Colour` or `Color`.
2. Option values of one product form a consistent set (every variant has the same option
   names). If a combination does not exist, the picker jumps to a variant that has the chosen value.
3. A sold-out size stays selectable (so its price can be seen) but cannot be added.
4. "Only N left" counts what other shoppers can still buy, so it already excludes units held
   in carts, including the viewer's own.
5. The exact available quantity is still present in the public API (`available_qty`, as it
   was since F-B); only the page chooses not to display it above the threshold.
6. Flag on: the "current price period" starts at the first history row with the current
   selling price (an MRP-only edit does not restart it). The reference is the lowest price in
   force during the window before that moment, including a price already in force when the
   window opened. With no earlier price on record nothing is struck.
7. Opening history rows are dated at migration time, because that is when recording began.
8. `queryset.update()` and raw SQL bypass signals and are not recorded in the price history.
   Nothing in this codebase changes a variant price that way.
9. Listing pages show "From Rs X" (lowest active variant) and add the default variant from
   the card; choosing a size happens on the product page.
10. Policy pages read the shipping charge and threshold live from the server settings, so
    those two numbers are real even though the surrounding copy is placeholder.
11. `seed_noore` attaches products to the first shop (`Vendor`) if one exists, so they show
    in the owner dashboard; it creates no shop. Seed products have no image file.
12. The smoke suite uses its own database (`backend/e2e.sqlite3`) and ports, and needs
    `python` on PATH to be the project's interpreter.

### 9. KNOWN GAPS

- **Policy copy is placeholder** and says so on every page. `PLACEHOLDER_COPY` in
  `frontend/src/views/policy/policies.js` must be set to `false` when the real text goes in.
- **Support email and WhatsApp number are placeholders** until the two `VITE_` variables are set.
- Footer "About us" lorem ipsum, the MDBootstrap copyright line, the header and the
  "Vendor" tab/links are untouched: that is G4.5.
- No dashboard screen for managing sizes or receiving stock; both are done in Django admin.
- The product description is shown as plain text, as before; HTML typed in the dashboard
  editor would show its tags.
- `CLAUDE.md` section 3 still describes G1 as future work ("STILL LEGACY Decimal rupees
  until phase G1") and its trap list mentions the two things fixed here. It was added to the
  repo unchanged; the owner should approve an update.

### 10. NOT DONE AND WHY

- **G4.5 branding and vendor-reference removal**: explicitly excluded by the owner.
- **Razorpay, COD selector, reviews moderation, reorder**: G3 and G4.
- **Real policy text**: the owner supplies it.
- **PostgreSQL concurrency run**: PostgreSQL could not be installed in the build container
  (package download returned 404). The tests exist and skip on SQLite by design.

---

## PHASE G1 — Pricing (COMPLETED)

### 1. PHASE COMPLETED

**G1 — Pricing**: one server-side function decides what a customer pays, in INR, in integer
paise. Branch name used locally: `phase/G1-pricing`.

- **Rupees everywhere.** No "$" or "USD" in the storefront, the order emails or the
  dashboard. `ConfigSettings.currency_sign` is the rupee sign.
- **One pricing function**, `store/pricing.py` `quote()`, used by the cart, order creation
  and the coupon endpoint. Totals sent by the browser are ignored.
- **Shipping**: flat Rs 79 per order, free when the subtotal after discount is Rs 999 or more.
- **Coupons**: percentage or flat rupees; minimum order; start and expiry date; total cap;
  per-customer cap (by account, or by email / phone for guests). The discount is spread over
  every line. Each refusal has its own message. Uses are recorded in `CouponRedemption`.
- **No service fee, no added tax.** Prices are tax-inclusive; the checkout says "Inclusive
  of all taxes". A carve-out formula is in place for when a tax rate is set.
- **Paise columns** beside every Decimal money column on Cart, CartOrder and CartOrderItem,
  backfilled, with the Decimal columns kept in step as a mirror.
- **Payments**: Stripe charges in `inr` from the stored paise total. PayPal is hidden.
- Also (G0 items this phase needed, see E1): the `AddToCart` import casing (the frontend did
  not build on Linux before), a default variant and opening stock for every new product,
  paid orders keep their stock after the checkout hold lapses, a PIN code field in the cart.

Step 0 result: see decision E2.

### 2. FILES CREATED

- `backend/store/pricing.py` — `quote()`, coupon checks, `apply_quote_to_order`, `record_redemption`
- `backend/store/money_mirror.py` — `MoneyMirrorMixin`, `set_money`, `assert_mirrors`, `mirror_mismatches`
- `backend/store/jobs.py` — `store.expire_stale_order_drafts` (hourly)
- `backend/catalog/signals.py` — Product and default variant kept in step
- `backend/store/migrations/0029` to `0034`, `backend/addon/migrations/0003` to `0005` (section 4)
- `backend/tests/test_pricing.py`
- `frontend/src/utils/money.js` — `formatINR(paise)`, `formatRupees`, `rupeesToPaise`, `percentOff`

### 3. FILES MODIFIED

- `backend/store/models.py` — paise columns, `CartOrder.coupon_code`, coupon rule fields, `CouponRedemption`
- `backend/addon/models.py` — `shipping_flat_paise`, `free_shipping_threshold_paise`, `tax_rate_bps`; currency defaults
- `backend/store/views.py` — cart, cart totals, order creation, coupon endpoint and Stripe all go through `quote()`; every read of `service_fee_*` and `Tax.rate` removed; the `qty x rate` tax path deleted
- `backend/store/order_state.py` — a paid order's stock is secured (`hold_for_order`)
- `backend/inventory/services.py` — new `hold_for_order`
- `backend/core/signals.py` — `total_paise` tracked on `CartOrder`
- `backend/store/apps.py`, `backend/catalog/apps.py` — register the job and the signals
- `backend/store/admin.py` — coupon rule columns; read-only redemption admin
- `backend/backend/settings.py`, `backend/.env.example` — `ORDER_DRAFT_TTL_HOURS`
- `backend/templates/email/customer_order_confirmation.html`, `vendor_order_sale.html` — "$" to the rupee sign
- `backend/conftest.py` — `product` fixture uses the automatic default variant; suite-wide mirror check
- `backend/inventory/tests/test_inventory.py` — the PostgreSQL race test uses the automatic default variant
- `backend/tests/test_security.py`, `backend/core/tests/test_core.py` — **two expectations changed on purpose**: per-line shipping of Rs 6 is now Rs 0 with Rs 79 on the order; the audited total after a 10% coupon on Rs 100 is Rs 169 (100 - 10 + 79), and `total_paise` appears in the audit row
- `frontend/src/views/plugin/addToCart.jsx` — optional variant id; no price sent
- `frontend/src/views/shop/Cart.jsx`, `Checkout.jsx` — rewritten: server totals, discount row, shipping or "Free", coupon apply/remove, PIN code, no tax or service-fee row, PayPal removed from the page
- `frontend/src/views/shop/ProductDetail.jsx`, `Products.jsx`, `Search.jsx`, `Invoice.jsx`, `PaymentSuccess.jsx`
- `frontend/src/views/customer/Orders.jsx`, `OrderDetail.jsx`, `Notifications.jsx`
- `frontend/src/views/vendor/Dashboard.jsx`, `Earning.jsx`, `OrderDetail.jsx`, `Products.jsx`, `Shop.jsx`, `AddProduct.jsx`, `UpdateProduct.jsx` — currency display only (E10)

### 4. MIGRATIONS ADDED

| Migration | What | Reverse |
|---|---|---|
| `store.0029_cart_paise_columns` | 6 paise columns on Cart | drops them |
| `store.0030_cartorder_paise_columns` | 7 paise columns and `coupon_code` on CartOrder | drops them |
| `store.0031_cartorderitem_paise_columns` | 8 paise columns on CartOrderItem | drops them |
| `store.0032_backfill_paise_columns` | fills paise from each Decimal twin (exact, half-up) | no-op: Decimal columns were never changed |
| `store.0033_coupon_rules` | `kind`, `flat_off_paise`, `min_order_paise`, `max_total_uses`, `max_uses_per_customer`, `valid_from`, `valid_until` | drops them |
| `store.0034_couponredemption` | `CouponRedemption`, unique on (coupon, order) | drops the table |
| `addon.0003_configsettings_pricing_fields` | shipping and tax settings | drops them |
| `addon.0004_currency_inr` | existing rows to the rupee sign / INR | restores "$" / USD |
| `addon.0005_currency_defaults_inr` | model defaults to the rupee sign / INR | restores the old defaults |

Apply:

    python manage.py migrate

Roll back G1 only (roll G2 back first, see its section):

    python manage.py migrate store 0028
    python manage.py migrate addon 0002

Verified on a copy of the supplied database: apply, roll back, re-apply all clean. After
apply: 2 carts, 1 order, 2 order lines, 0 mirror mismatches; config is rupee / INR / 7900 /
99900 / 0. After rollback: no paise columns, "$" / USD restored, order totals untouched.

### 5. ENV VARS ADDED

- `ORDER_DRAFT_TTL_HOURS` (optional, default `48`, keep above 26)

### 6. TESTS ADDED

`backend/tests/test_pricing.py`, 41 tests (40 run, 1 PostgreSQL-only):

    python -m pytest tests/test_pricing.py -q   ->  40 passed, 1 skipped
    python -m pytest -q                         ->  120 passed, 2 skipped at the end of G1

Shown failing first: run against the pre-G1 code the file fails at import
(`ModuleNotFoundError: No module named 'store.jobs'`); none of `store.pricing`,
`store.money_mirror` or the paise columns existed.

Covers every G1 acceptance line: Rs 920 pays Rs 79, Rs 999 ships free, Rs 1,100 with 10% off
pays Rs 79; a tampered client total is ignored and the stored order equals `quote()`; a
percentage coupon discounts every line and the lines sum to the paisa; a flat coupon larger
than the subtotal stops at 0; refusal when unknown, inactive, not started, expired, under
minimum, over the total cap and over the per-customer cap (signed-in and guest by email or
phone), each with its own message; cancelling frees the redemption, as does removing or
replacing the coupon; no service fee even with a 5% fee and an 18% Tax row configured; tax
at 1800 bps is carved out and the total is unchanged; a later price change never alters an
order; Stripe is called with `inr` and the stored paise.

**Mirror check (owner amendment).** `conftest.py` connects a check to every save of Cart,
CartOrder and CartOrderItem for the whole suite: it walks every money pair and fails the
test if `to_paise(decimal) != paise`. A named test walks create, quantity change, coupon,
payment and cancel. A dedicated test writes a paise value without its mirror
(`queryset.update`) and shows the assertion fail.

Playwright: the G1 scenario is in `frontend/e2e/storefront.spec.js` (see G2, section 6).

### 7. MANUAL VERIFICATION STEPS

Same commands as G2 section 7. Then:

1. Cart with one 200 g candle: Subtotal Rs 799, Shipping Rs 79, Total Rs 878.
2. Coupon `WELCOME10`: Discount -Rs 79.90, Total Rs 798.10. Coupon `NOPE`: "This coupon code is not valid."
3. Add a 300 g candle: Shipping becomes "Free".
4. Fill the address and go to checkout: same figures, "Inclusive of all taxes", no tax or
   service-fee row, no PayPal button, card button reads "Pay Rs ... by card".
5. Django admin, Coupons: set "Max total uses" to 1 on a coupon, use it on one order, try it
   from another browser with another email: "This coupon has been fully redeemed."
6. Dashboard, edit a product's price: Django admin, Catalog, Product variants shows the new price.
7. Worker: `python manage.py run_worker --once` runs the draft-expiry job among the others.

### 8. ASSUMPTIONS MADE

1. Decisions E3 to E16 above.
2. Order column meanings from G1 on: `sub_total` item subtotal before discount; `saved` the
   discount; `shipping_amount` the order's shipping; `tax_fee` tax carved out (0 today);
   `service_fee` 0; `initial_total` subtotal plus shipping; `total` what the customer pays.
   On a line: `price` unit price; `sub_total` price x qty; `saved` its share of the discount;
   `total` sub_total minus saved; `shipping_amount` and `service_fee` 0.
3. Rows written before G1 keep their old meaning and old numbers.
4. PERCENT rounds down to a whole paisa; the split across lines is largest-remainder, ties
   to the earlier line.
5. A coupon is looked up by code, case-insensitively, among active coupons; the legacy
   per-vendor match is gone. If two active coupons share a code the newest wins.
6. A redemption counts unless its order is Cancelled, or its payment is cancelled or
   expired, or the order no longer carries that coupon. A failed or refunded payment still counts.
7. Signed-in customers are matched by account only; guests by lower-cased email or E.164 phone.
8. A guest's per-customer cap can only be checked once they give contact details, so the
   cart preview may accept a code that order creation then refuses; the customer is told
   before the checkout page opens and the order is created without the discount.
9. Re-posting a cart updates its unpaid draft from the cart as it is now. If the request
   has no `coupon_code` key the draft keeps its coupon; a blank value removes it.
10. Applying a coupon on the checkout page re-prices from the unit prices stored on the order.
11. `redemption.discount_paise` is the discount at the moment of first use; the order's
    `saved_paise` is the current figure.
12. The cart-totals response no longer has the float keys `shipping`, `tax`, `service_fee`,
    `sub_total`, `total`; it has integer `*_paise` keys. No endpoint, model or field was
    removed or renamed.
13. `ConfigSettings` defaults apply when no settings row exists.
14. Paying when the hold has lapsed re-reserves if stock is there; if not, the order is
    still marked paid and an `order.stock_shortfall` audit row is written for the owner.
15. Stripe's `currency` value `inr` and an integer `unit_amount` in the smallest unit are
    the only provider details changed; no payload was invented.
16. Built and tested on Python 3.12 and Node 22 (the container's); the project targets 3.11 and 20.

### 9. KNOWN GAPS

- **Guest coupon evasion (accepted by the owner).** A guest can get round the per-customer
  cap by checking out with a different email **and** a different phone number. The cap is
  reliable only for signed-in customers. `max_total_uses` still bounds the total cost of a
  coupon, so **set it on every coupon that matters**.
- **PostgreSQL concurrency tests not run.** `ConcurrentCouponTest` (new) and the F-B
  stock race test skip on SQLite. PostgreSQL could not be installed in the build container.
  Run them once locally with the commands in `CLAUDE.md` section 2 (`-k concurrent`, and
  `python -m pytest tests/test_pricing.py -k capped -q`).
- **Draft expiry needs the worker.** Without `run_worker`, an abandoned checkout keeps its
  coupon use until the job runs.
- **A total of Rs 0 cannot be paid by card** (the endpoint says so). Only reachable if
  shipping is set to 0 and a flat coupon covers the subtotal.
- **Tax base needs a CA** before `tax_rate_bps` is ever set above 0 (E12). This is a
  compliance interpretation; nothing is charged differently today.
- **Order emails** now show rupees but still list "Tax" and "Service fee" rows (both 0.00)
  and no discount row.
- **Django admin can still edit order statuses directly** (`list_editable`), bypassing the
  state machine. Pre-existing; not changed here.
- **Nothing in the dashboard moves an order's delivery status**, so stock does not leave
  the ledger on dispatch yet (a G0 item not rebuilt here).
- **PayPal backend path** still exists and still compares in USD; it is unreachable from
  the storefront and returns 503 without credentials.
- Legacy `CouponUsers`, `Coupon.used_by`, `CartOrder.coupons` and `CartOrderItem.coupon`
  are no longer written; `CouponRedemption` and `coupon_code` replace them.
- Dashboard revenue excludes shipping (E11).

### 10. NOT DONE AND WHY

- **Razorpay, COD selector**: G3.
- **Variant picker, price history**: G2 (done above).
- **Removing** `service_fee_*`, `Tax`, the Decimal columns, Stripe or PayPal: rule 4;
  they stay as removal proposals.
- **Resolving a real price mismatch**: none found in the supplied database (E2, E3).

---

## PHASE F-A.1 — Owner dashboard access (COMPLETED)

Follow-up to F-A after the owner reported that a newly created superuser could only see the
customer account pages.

**Cause.** The storefront's owner dashboard is driven by the `vendor_id` claim inside the login
token. A freshly created superuser owns no `Vendor` row, so the claim is `0` and
`Dashboard.jsx` redirects to `/vendor/register/`. Separately, the seeded shop (id 10) — which
owns all four demo products — was still attached to the seed account `desphixs@gmail.com`, so
even registering a new shop would have produced an empty dashboard. This is seed-data
ownership, not a defect introduced by F-A.

**FILES CREATED**

| Path | Purpose |
|---|---|
| `backend/core/management/commands/claim_shop.py` | `python manage.py claim_shop` — lists shops and attaches the brand's shop (with its products, orders, coupons and reviews) to a staff account. Refuses non-staff accounts, refuses to run before `migrate`, releases any shop the user already held, runs in one transaction, and writes a `shop.claimed` audit row |

**FILES MODIFIED** — none.

**MIGRATIONS ADDED** — none.

**ENV VARS ADDED** — none.

**TESTS** — no new automated test; verified manually end to end (see below). `python -m pytest -q` still reports 39 passed.

**MANUAL VERIFICATION PERFORMED**

On a copy of the seeded database: created a fresh `admin@gmail.com` superuser, confirmed its
token carried `vendor_id: 0`, ran `claim_shop --list` (six shops, only id 10 holding products),
ran `claim_shop --email admin@gmail.com`, confirmed the token then carried `vendor_id: 10`, and
called all nine owner dashboard endpoints with that account's JWT — every one returned HTTP 200
with real data (4 products, 1 order, revenue 1329.00) and no credential fields. Also confirmed
the command aborts with a readable message when run before `migrate`, and that the failure
rolls back cleanly, leaving ownership unchanged.

**ASSUMPTIONS MADE**

1. The brand's shop is the one holding the most products when `--shop-id` is not given.
2. Claiming a shop does not move products from other shops unless `--move-products` is passed.
3. The five empty seed shops are left in place (rule 4); they are covered by removal proposal R1.
4. The `vendor_id` token claim remains the mechanism for showing the dashboard, so a fresh login is required after claiming.

**KNOWN GAPS**

- The dashboard is still reached through the nav item labelled "Vendor", and `/vendor/register/` is still linked. Both are renamed or removed when the multi-vendor residue goes.
- `Dashboard.jsx` redirects to `/vendor/register/` whenever `vendor_id` is 0, including for ordinary customers, who then hit a 403 on that page. Cosmetic; folded into the residue removal.

---

## PHASE F-A — Platform & security baseline (COMPLETED)

### 1. PHASE COMPLETED

Foundation work only; no customer-facing feature from the 12. Acceptance criteria met:

- Every credential leak found in Phase 0 is closed and covered by a regression test.
- Default-deny API: every view explicitly opts into public access.
- Every customer-data endpoint enforces ownership; every owner endpoint enforces staff.
- Prices, shipping and cart ownership are decided by the server.
- Payment confirmations cannot be replayed across orders.
- Secrets moved out of code; `.env.example` documents every variable.
- Append-only audit log for price, stock, order and delivery state changes (rule 9).
- Idempotency store for webhooks/external confirmations (rule 8).
- Job outbox + worker (prerequisite for Features 1, 4, 5, 8, 10, 11).
- Money (paise) and Asia/Kolkata time helpers (rules 6, 7).
- PII-masking logging (security section).
- Test harness with 39 passing tests; 19 security tests proven to fail on the baseline.

**Critical findings discovered and fixed during this phase (all LIVE-VERIFIED before fixing):**

| Severity | Finding |
|---|---|
| CRITICAL | `GET /api/v1/products/` (public) returned the superuser's **password hash, OTP and password-reset token** via `product.vendor.user` (DRF `depth=3` auto-expanded the User model with all fields) |
| CRITICAL | `GET /api/v1/user/profile/<id>/` (anonymous) returned any user's password hash, OTP and reset token |
| CRITICAL | `POST /api/v1/user/password-change/` accepted only `user id + OTP`; combined with the leaks above this was **anonymous takeover of any account including the admin** |
| HIGH | `GET /api/v1/checkout/<oid>/` returned the buyer's password hash |
| HIGH | Public review lists exposed every reviewer's email and phone |
| HIGH | Anonymous read of any customer's orders, wishlist, notifications; anonymous edit of any profile |
| HIGH | Anonymous product create/update/delete, coupon CRUD, shop edit, order tracking edit |
| HIGH | Cart price and shipping taken from the request body |
| HIGH | Reviews could be posted as any user |
| HIGH | PayPal: amount/currency never verified, PayPal order id reusable across orders; Stripe: any paid session id could mark any order paid |
| MEDIUM | PayPal OAuth access token printed to stdout; password, OTP and reset token printed by the password-change view and logged to the browser console |
| MEDIUM | Password-reset OTP generated with `random` (not cryptographic); reset link host hardcoded to localhost |
| LOW | Guest cart id generated with `Math.random`; first call returned `null` |

### 2. FILES CREATED

| Path | Purpose |
|---|---|
| `backend/core/__init__.py` | Package marker |
| `backend/core/apps.py` | App config; registers audit signals and built-in jobs on startup |
| `backend/core/models.py` | `AuditLog` (append-only), `ProcessedEvent` (idempotency, append-only), `Job` (outbox); `AppendOnlyModel` base that blocks save/update/delete of existing rows |
| `backend/core/audit.py` | Current-actor context (`set_actor`, `acting_as`) and `record()` helper |
| `backend/core/signals.py` | Writes one audit row per tracked-field change on `Product`, `CartOrder`, `CartOrderItem` (covers API, admin, shell) |
| `backend/core/authentication.py` | `AuditingJWTAuthentication`: JWT auth that sets the audit actor |
| `backend/core/middleware.py` | `RequestActorMiddleware`: resets actor per request; attributes admin (session) changes |
| `backend/core/permissions.py` | `IsStaffOwner`, `PublicReadStaffWrite`, `ensure_self_or_staff()`, `ensure_order_access()` |
| `backend/core/serializers.py` | `SafeDepthModelSerializer` (depth-expanded Users become `PublicUserSerializer`), `PublicUserSerializer` |
| `backend/core/idempotency.py` | `claim_event(provider, event_id)` exactly-once claim |
| `backend/core/jobs.py` | `@job`, `@periodic`, `enqueue()` with dedupe key, atomic claim, retry with backoff, DEAD after max attempts, stale-job reaper |
| `backend/core/builtin_jobs.py` | Periodic `core.reap_stale_jobs` (every 5 min) |
| `backend/core/management/commands/run_worker.py` | `python manage.py run_worker [--once]` |
| `backend/core/money.py` | `to_paise`, `from_paise`, `format_inr`; rejects float |
| `backend/core/timeutils.py` | Asia/Kolkata helpers; rejects naive datetimes |
| `backend/core/logmask.py` | `PIIMaskingFilter` masking emails, phones, JWT/Bearer tokens |
| `backend/core/admin.py` | Read-only admin for audit log, processed events and jobs |
| `backend/core/migrations/0001_audit_idempotency_jobs.py` | Creates the three core tables |
| `backend/core/tests/test_core.py` | 18 platform tests |
| `backend/tests/test_security.py` | 21 security regression tests |
| `backend/conftest.py` | pytest fixtures (users, JWT clients, product, orders) |
| `backend/pytest.ini` | pytest configuration |
| `backend/requirements-dev.txt` | Test dependencies |
| `backend/.env.example` | Every backend variable, documented |
| `frontend/.env.example` | Frontend overrides, documented |
| `docs/BUILD_LOG.md` | This file |

(`__init__.py` markers under `core/management`, `core/management/commands`, `core/migrations`, `core/tests`, `tests` also created.)

### 3. FILES MODIFIED

| Path | What changed and why |
|---|---|
| `backend/backend/settings.py` | `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` (now includes `localhost`), CSRF/CORS origins read from env; `CORS_ALLOW_ALL_ORIGINS` replaced with an allow-list; `core` app + `RequestActorMiddleware` added; DRF default permission is now `IsAuthenticated` with `AuditingJWTAuthentication`; throttling (anon, user, auth, otp, checkout, review, webhook); email backend and sender from env (course author's personal address removed); Stripe/PayPal keys optional; `PAYPAL_API_BASE`, `BUSINESS_TIME_ZONE`, `PASSWORD_RESET_TOKEN_MINUTES`, job settings; `LOGGING` with PII masking; secure cookies when not DEBUG. Jazzmin and SimpleJWT settings unchanged |
| `backend/requirements.txt` | Added `django-tinymce==4.1.0` (required by two existing migrations; missing before), `psycopg2` -> `psycopg2-binary==2.9.9` (installs on Windows), pinned `Pillow==10.4.0` and `django-import-export==4.4.1` (were unpinned), `setuptools<81` (drf-yasg needs `pkg_resources`) |
| `backend/.env` | Now holds local-dev values including a freshly generated `DJANGO_SECRET_KEY`, console email backend, and empty payment keys (the old `<add-your-key>` placeholders would have been treated as real keys) |
| `backend/.gitignore` | `.env` is now ignored |
| `backend/userauths/serializer.py` | `UserSerializer` limited to id, email, username, full_name, phone (was `__all__`: password hash, OTP, reset token, permissions). `ProfileSerializer.user` made read-only (a user could previously re-point a profile to another account). Added `PublicProfileSerializer` |
| `backend/userauths/views.py` | Profile: owner or staff only. Password-reset request: identical response for known/unknown emails, returns no account data, OTP from `secrets`, reset token is a signed 30-minute JWT with `purpose=password_reset`, link uses `SITE_URL`, email failure no longer 500s. Password change: requires user id + OTP + the matching unexpired single-use reset token, validates password strength, constant-time compares; all debug prints removed. Throttle scopes on login, register, reset |
| `backend/store/serializers.py` | All model serializers now extend `SafeDepthModelSerializer`; `VendorSerializer.user` and `ReviewSerializer.profile` use public serializers |
| `backend/store/views.py` | Every view declares its permission. Cart: price and shipping from DB, quantity validated against stock, owner from JWT, body `user` must match caller. Cart list/detail/delete: `user_id` in URL must be the caller. Create order: owner from JWT, required-field validation, empty cart rejected. Checkout/coupon/payment-success: a registered buyer's order is only accessible to that buyer or staff. PayPal: amount and currency must equal the order total, PayPal order id claimed once via `ProcessedEvent`, row-locked status transition, 15 s timeouts, token no longer printed. Stripe: session id must equal the one created for the order, claimed once, 503 when keys absent. Reviews: login required, written as caller, rating 1-5 validated. Cart totals summed as Decimal. Missing products return 404 instead of 500. Existing behaviours intentionally preserved and flagged: tax formula, first-item-only coupon, vendor emails |
| `backend/customer/views.py` | Orders, order detail, wishlist, notifications, settings: login required and `user_id` must be the caller (or staff). Settings now updates the caller's own profile (it previously looked up `Profile` by the user id as a profile primary key, i.e. edited the wrong profile) |
| `backend/vendor/views.py` | All owner-dashboard endpoints require staff (`IsStaffOwner`), including the three function-based chart views and five views that had no permission at all. Public shop page: read by anyone, write by staff only. Shop product listing stays public. Vendor register attaches the shop to the signed-in staff user (ignores `user_id` in the body). Owner profile settings look up the profile by user. All debug prints removed. No logic otherwise changed |
| `frontend/src/utils/axios.js` | Request interceptor attaches the JWT to every API call and refreshes it when expired, with a single in-flight refresh shared by concurrent requests. This is why 38 components did not need editing |
| `frontend/src/utils/useAxios.js` | Now returns the shared instance (the old version read `response.data.access` from an object that had no `data`, so every refreshed request sent `Bearer undefined`) |
| `frontend/src/utils/auth.js` | Page-load session restore uses the shared single-flight refresh (avoids two rotations of the same refresh token and a surprise logout); a failed restore continues as guest instead of leaving the app blank; cookies get `SameSite=Lax` |
| `frontend/src/utils/constants.js` | Values overridable via `VITE_API_BASE_URL`, `VITE_SERVER_URL`, `VITE_PAYPAL_CLIENT_ID`; defaults unchanged |
| `frontend/src/views/plugin/cartID.jsx` | Cart id from `crypto.getRandomValues`; returned on first call |
| `frontend/src/views/auth/forgotPassword.jsx` | Shows the server's generic message; handles errors/throttling; no longer logs the response |
| `frontend/src/views/auth/createPassword.jsx` | No longer logs OTP, reset token and new password to the console; shows server validation errors (previous `try/catch` around a promise never caught anything) |
| `frontend/.gitignore` | Ignores `.env` and `.env.local` |

### 4. MIGRATIONS ADDED

| Name | What it does | Apply | Roll back |
|---|---|---|---|
| `core.0001_audit_idempotency_jobs` | Creates `core_auditlog`, `core_processedevent` (unique provider+event_id), `core_job` (unique dedupe_key) with indexes | `python manage.py migrate core` | `python manage.py migrate core zero` |

Rollback and re-apply verified on a copy of the seeded database. No existing table was altered.

### 5. ENV VARS ADDED

All in `backend/.env.example` with comments.

| Name | Purpose | Example | Required |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Django signing key (was hardcoded) | 64 random chars | **Yes** |
| `DJANGO_DEBUG` | Debug mode | `False` | No (default False) |
| `DJANGO_ALLOWED_HOSTS` | Served hostnames | `127.0.0.1,localhost` | No |
| `CSRF_TRUSTED_ORIGINS` | Admin form origins | `http://127.0.0.1:8000` | No |
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API | `http://localhost:5173` | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `BUSINESS_TIME_ZONE` | Timezone for business rules | `Asia/Kolkata` | No |
| `DJANGO_EMAIL_BACKEND` | Email backend | `django.core.mail.backends.console.EmailBackend` | No (default Mailgun) |
| `DEFAULT_FROM_EMAIL` | Sender address | `noreply@yourbrand.in` | No |
| `PAYPAL_API_BASE` | PayPal API host | `https://api-m.sandbox.paypal.com` | No |
| `PASSWORD_RESET_TOKEN_MINUTES` | Reset link lifetime | `30` | No |
| `THROTTLE_ANON`, `THROTTLE_USER`, `THROTTLE_AUTH`, `THROTTLE_OTP`, `THROTTLE_CHECKOUT`, `THROTTLE_REVIEW`, `THROTTLE_WEBHOOK` | Rate limits | `10/min` | No |
| `JOB_MAX_ATTEMPTS` | Retries before DEAD | `5` | No |
| `JOB_WORKER_SLEEP_SECONDS` | Idle poll interval | `5` | No |
| `JOB_STALE_AFTER_SECONDS` | Orphaned-job timeout | `600` | No |
| `VITE_API_BASE_URL`, `VITE_SERVER_URL`, `VITE_PAYPAL_CLIENT_ID` | Frontend overrides | see `frontend/.env.example` | No |

Changed from required to optional: `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET_ID` (payment endpoints return 503 when blank). `MAILGUN_API_KEY`, `MAILGUN_SENDER_DOMAIN` now read through `environs` (were `os.environ.get`).

### 6. TESTS ADDED

Run from `backend/` with the venv active:

```
pip install -r requirements-dev.txt
python -m pytest -q
```

Result: **39 passed**.

`tests/test_security.py` (21 tests) was also run against the untouched baseline commit: **19 failed, 2 passed**. The two that pass on the baseline are regression guards, not bug reproductions: a guest order has no buyer to leak, and in a fresh test database profile ids happen to equal user ids.

| Test | Proves |
|---|---|
| `test_public_catalog_endpoints_never_expose_credentials` | No password/OTP/reset token/permission key anywhere in 7 public endpoints |
| `test_reviews_do_not_expose_reviewer_email_or_phone` | Review lists show name and avatar only |
| `test_checkout_of_guest_order_does_not_expose_credentials` | Guard for the checkout serializer |
| `test_profile_endpoint_is_owner_only` | 401 anonymous, 403 other user, 200 self without secrets |
| `test_password_reset_request_returns_no_account_data` | Same body for known and unknown emails; no account data |
| `test_password_change_rejects_otp_without_valid_reset_token` | The takeover path is closed |
| `test_password_reset_full_flow_is_single_use` | Legit flow works once; link cannot be reused |
| `test_customer_orders_are_owner_only` | Order list/detail IDOR closed |
| `test_wishlist_notifications_and_settings_are_owner_only` | IDOR closed on three more endpoints; profile hijack and wishlist-for-victim blocked |
| `test_settings_update_changes_the_callers_own_profile` | Settings edit hits the right profile |
| `test_registered_buyers_order_is_hidden_from_other_users` | A logged-in buyer's order is not readable by others via its oid |
| `test_cart_price_and_shipping_come_from_the_database` | Tampered `price: 1.00` is stored as 56.00 |
| `test_cart_cannot_be_created_for_another_user` | Body `user` must be the caller |
| `test_order_cannot_be_created_on_behalf_of_another_user` | Body `user_id` must be the caller |
| `test_review_requires_login_and_is_written_as_the_caller` | No anonymous or impersonated reviews |
| `test_owner_dashboard_endpoints_are_staff_only` | 401/403/200 matrix on 7 owner endpoints |
| `test_anonymous_users_cannot_create_products_or_coupons` | No anonymous catalog/coupon writes |
| `test_public_shop_page_is_readable_but_not_writable` | Public read, staff-only write |
| `test_stripe_session_from_another_order_cannot_mark_order_paid` | Stripe cross-order replay blocked |
| `test_paypal_order_id_cannot_be_replayed_against_a_second_order` | PayPal replay blocked (409) |
| `test_paypal_payment_for_a_smaller_amount_is_rejected` | Underpayment rejected |
| `core/tests/test_core.py` (18 tests) | Price change writes exactly one audit row with before/after and actor; unchanged save writes none; system changes have null actor; API change attributed to JWT user; audit rows cannot be updated or deleted (instance and queryset); event claimed once; job dedupe; not run early; naive datetime rejected; no double claim; retry with backoff then DEAD with PII-masked error; periodic scheduling idempotent; stale jobs reclaimed; `run_worker --once`; paise conversion exact and float rejected; IST offset; log masking |

### 7. MANUAL VERIFICATION STEPS

Backend terminal (PowerShell, from `backend\`):

1. `.\venv\Scripts\Activate.ps1`
2. `pip install -r requirements-dev.txt`
3. `python manage.py migrate` -> expect `Applying core.0001_audit_idempotency_jobs... OK`
4. `python -m pytest -q` -> expect `39 passed`
5. Make sure your admin account is staff (superusers already are).
6. `python manage.py runserver`
7. Open `http://127.0.0.1:8000/api/v1/products/` and press Ctrl+F for `password` -> no match.
8. Open `http://127.0.0.1:8000/api/v1/user/profile/11/` in a private window -> `401`.
9. `http://localhost:8000/api/v1/products/` now works (was `400`).

Frontend terminal (from `frontend\`): `npm run dev`, then in the browser:

10. Browse the home page and a product page while logged out -> works.
11. Add to cart as a guest -> works; cart shows the database price.
12. Register a new customer -> auto-login works; `Account > Orders`, `Wishlist`, `Notifications`, `Settings` load.
13. Log in as your superuser -> vendor dashboard loads (stats, products, orders, coupons).
14. Log in as the normal customer and open `http://localhost:5173/vendor/dashboard/` -> dashboard data does not load (403 in the Network tab).
15. Forgot password with your email -> the password-reset email (with the link) prints in the **backend terminal** (console email backend). Open the link, set a new password, log in with it. Open the same link again -> error.
16. Third terminal: `python manage.py run_worker` -> prints `worker started`; within 5 minutes `Django admin > Core platform > Jobs` shows a DONE `core.reap_stale_jobs` row.
17. In Django admin change a product's price -> `Core platform > Audit logs` shows one `product.updated` row with before/after and your user.

### 8. ASSUMPTIONS MADE

1. The uploaded ZIP is the repository to convert.
2. The owner and all brand staff are Django staff users; being staff grants full access to every owner endpoint (no finer roles yet).
3. A guest order is addressable by anyone holding its random 10-letter `oid` (about 9.5 x 10^13 possibilities) so guests can pay and view their invoice. Once an order has a registered buyer, only that buyer or staff can use its `oid`.
4. The Stripe checkout endpoint remains reachable without a JWT because the frontend reaches it with a plain HTML form POST; the amount always comes from the database.
5. The PayPal v2 order response contains `purchase_units[0].amount.currency_code` and `.value`. Verification **fails closed** if that shape is absent. This is the only external payload shape assumed in this phase; please confirm against a real sandbox capture before relying on PayPal.
6. Guest carts remain addressable by `cart_id` (now cryptographically random, 30 chars) without login.
7. Cart price = `product.price`. Size-specific prices in the `Size` table are ignored, which matches what the frontend always sent.
8. Adding more than `stock_qty` to a cart is rejected. `stock_qty` is still never decremented (fixed in F-B), so this only guards obviously impossible quantities today.
9. Password-reset links are valid for 30 minutes and single-use. The email address remains in the URL path of the reset-request endpoint (frontend contract unchanged); it will appear in web-server access logs.
10. Throttle counters use Django's default local-memory cache: per process, reset on restart. Production with multiple processes needs a shared cache (flagged in Known Gaps).
11. The audit actor for anonymous API calls is recorded as `anonymous`; for the worker as `system:worker`; with no request as `system`.
12. Audit tracks these fields only: Product `price, old_price, shipping_amount, stock_qty, status`; CartOrder `payment_status, order_status, total`; CartOrderItem `delivery_status, tracking_id, delivery_couriers, qty, total`. Deletes of these models are also audited.
13. Append-only is enforced in the ORM (model and queryset). A database-level guard (Postgres trigger or revoked UPDATE/DELETE grants) is not in place.
14. The `run_worker` process is expected to run continuously in production (systemd, Supervisor, Render worker) or be invoked with `--once` from cron / Windows Task Scheduler every minute.
15. The job outbox gives at-least-once delivery; every future job handler will be written to be idempotent.
16. JWT claims unchanged (still include `vendor_id`) so the frontend's owner-dashboard routing keeps working.
17. CORS is now an allow-list of `http://localhost:5173` and `http://127.0.0.1:5173`. The production storefront origin must be added via `CORS_ALLOWED_ORIGINS`.
18. Development email goes to the terminal (`console` backend) via `.env`; production defaults to Mailgun if `DJANGO_EMAIL_BACKEND` is unset.
19. The committed `backend/.env` was replaced with development values and is now git-ignored. If the repo is under git: `git rm --cached backend/.env`.
20. Python 3.11 is the target runtime; tests were run on Python 3.12 with `setuptools<81`.

### 9. KNOWN GAPS

- **Customers who are not staff can no longer open the vendor dashboard or register as a vendor.** Intended for single-brand; the frontend still shows those links (removed with the residue later).
- The `vendor/register` page 403s for non-staff users.
- Throttling uses a per-process cache; configure a shared cache (Redis or Django's database cache) before running multiple app processes.
- `select_for_update()` in the payment confirmation is a no-op on SQLite (SQLite serialises writes anyway). Real row locking needs PostgreSQL.
- `Meta.depth` is still mutated per request inside several existing serializers (existing pattern). Concurrent POST/GET requests in one process can briefly see the wrong depth. Safe from a security standpoint now (nested users are always public-safe); it is a correctness wart to remove when those serializers are rewritten.
- Frontend behaviour after these changes was verified by a successful production build and by reading every changed call path, **not** by an automated browser test. Steps 10-17 above are the end-to-end check.
- PayPal and Stripe verification were tested with mocked provider responses only.
- `ProductDetail.jsx` passes size and colour to `addToCart` in swapped order (existing bug; size is stored as colour). Not fixed in this phase.
- Five files import `../plugin/AddToCart` while the file is `addToCart.jsx`: works on Windows, breaks Linux/Netlify builds. Not fixed (would be a rename outside this phase's scope).
- Existing correctness bugs left as-is and documented in code: tax computed as `qty x rate` instead of `price x rate`; coupons discount only the first matching item and are infinitely reusable; `CartOrder.oid` is not unique; `/create-order/` creates a new order on every call (fixed in F-B).
- `npm audit` reports 56 vulnerabilities in frontend dependencies (existing); not addressed in this phase.

### 10. NOT DONE AND WHY

- **Phase F-B** (next): `ProductVariant`, `Batch`, stock ledger + reservations with expiry, FEFO allocator, order `payment_method` / `channel` / `pincode` / `phone_e164`, order state machine, one order draft per cart. Deliberately split out so the security fixes could ship and be verified on their own.
- **Money migration** (legacy Decimal -> paise): separate reversible phase per rule 6.
- **Features 1 and 2:** blocked on Razorpay docs/samples and WhatsApp Cloud API templates, rate card and webhook samples (rule 12).
- **Removal of multi-vendor residue:** proposals R1-R21 stand, not approved, not done.

---

## PATCH F-A.1 — Product edit from the owner dashboard (COMPLETED)

### 1. PHASE COMPLETED
Bug fix, no new feature. Editing a product from the owner dashboard returned
`400 {"image": ["The submitted data was not a file. Check the encoding type on the form."]}`.

**Pre-existing, not caused by Phase F-A.** The same request was replayed against the untouched
baseline commit and produced the identical 400.

Cause: the edit screen loads a product and posts every field back. `image` arrives as the URL
string the API served (`http://127.0.0.1:8000/media/user_11/11.jpg`), and `FileField` only
accepts uploads. Three further defects were found in the same path:

- The whole update was a **full** update, so any field the form omitted was reset.
- Specifications, colours, sizes and the gallery were deleted and recreated on every save. The
  screen posts `gallery[N][image]` as the literal string `"undefined"`, so a successful save
  would have **wiped the gallery**.
- `category` was posted as `"[object Object]"` and silently ignored, so the category dropdown
  never did anything.
- On success the screen called `response.json()` on an Axios response, which has no such
  method, so a successful save still logged `Error submitting form` to the console.

### 2. FILES CREATED
| Path | Purpose |
|---|---|
| `backend/tests/test_product_update.py` | 7 regression tests for the product edit path |

### 3. FILES MODIFIED
| Path | What changed and why |
|---|---|
| `backend/vendor/views.py` | `ProductUpdateAPIView` rewritten. Update is now partial. Read-only/computed keys the form echoes back are dropped. An `image` value that is not an upload is ignored, so the stored image is kept. `category` is accepted as an id and ignored when it is the echoed object. Nested image values that are existing media URLs are resolved to their storage path, validated to exist, and attached after the row is created (a path string cannot pass `FileField` validation). A nested section is replaced only when the request carried usable entries for it, so editing a price can no longer wipe the gallery. `get_object` uses `get_object_or_404` (was `.get()`, a 500 on a bad id) |
| `frontend/src/views/vendor/UpdateProduct.jsx` | Sends `image` only when the user picked a new file; sends `category` as an id; skips read-only keys; sends existing colour/gallery image URLs back instead of `undefined`; removes the per-field `console.log` of the whole product; removes the invalid `response.json()`; shows the server's validation message on failure instead of only logging it; navigates after the success dialog |

### 4. MIGRATIONS ADDED
None.

### 5. ENV VARS ADDED
None.

### 6. TESTS ADDED
`cd backend && python -m pytest -q` -> **46 passed** (39 from F-A plus 7 below).

| Test | Proves |
|---|---|
| `test_price_edit_succeeds_when_image_is_echoed_back_as_a_url` | The reported 400 is gone |
| `test_price_edit_keeps_the_existing_product_image` | Editing a price does not clear the image |
| `test_price_edit_does_not_wipe_gallery_colors_sizes_or_specifications` | Nested data survives, including the colour's existing image |
| `test_a_new_image_upload_still_replaces_the_product_image` | Uploading a new image still works |
| `test_category_can_be_changed_by_id_and_is_untouched_when_echoed_back` | Category is editable and not clobbered |
| `test_product_edit_is_still_staff_only` | 401 anonymous, 403 customer (F-A guarantee intact) |
| `test_a_traversal_path_in_an_image_field_is_rejected` | `media/../../etc/passwd` in an image field is refused |

### 7. MANUAL VERIFICATION STEPS
1. Restart the backend and reload the frontend (hard refresh, Ctrl+Shift+R).
2. Owner dashboard -> Products -> edit a product -> change only the price -> Update.
3. Expect "Product Updated Successfully" and a redirect to the product list; the new price shows.
4. Re-open the same product: the image, gallery, colours, sizes and specifications are unchanged.
5. Change the category, save, re-open: the new category is selected (this never worked before).
6. Upload a new main image, save: the new image shows on the product page.
7. Browser console during a successful save: no errors, and no product field dump.

### 8. ASSUMPTIONS MADE
1. An image value that is not an upload means "keep what is stored", never "clear the image".
   The edit screen has no delete-image control, so no intent to clear can be expressed.
2. An existing image URL is only honoured when the file exists in storage; anything else is
   dropped. This blocks pointing a product at an arbitrary path.
3. A nested section (specifications, colours, sizes, gallery) is replaced only when the request
   carries at least one usable entry. Clearing a section entirely is therefore not possible from
   this screen and is done in Django admin. This is deliberate: the screen's `"undefined"`
   placeholder is indistinguishable from a genuine "delete everything".
4. `category` is writable by id. It remains read-only inside `ProductSerializer` (`depth=3`),
   so the view assigns it explicitly after validation.
5. Nested rows are still deleted and recreated rather than matched and updated, so their ids
   change on every save. Preserved from the original design; a rewrite is out of scope here.

### 9. KNOWN GAPS
- `AddProduct.jsx` (create) was not changed; it posts real `File` objects and works.
- Nested row ids are not stable across saves (see assumption 5).
- Verified by automated API tests and a production frontend build, not by a browser test.

### 10. NOT DONE AND WHY
- No change to `ProductSerializer`'s per-request `Meta.depth` mutation (flagged in F-A Known Gaps);
  it will be removed when that serializer is rewritten for variants in F-B.
- Phase F-B not started; this patch was pulled forward because it blocks day-to-day use.

---

## PHASE F-B — Catalog, inventory and order state (COMPLETED)

### 1. PHASE COMPLETED

Foundation work, part two. Still no customer-facing feature from the 12; this builds the
data model those features need. Acceptance criteria met:

- **Variants exist.** Every product has a sellable unit carrying SKU, price (paise) and stock.
- **Stock is a ledger.** Available stock is derived from append-only `StockMovement` rows.
  No mutable integer is incremented anywhere.
- **Stock actually moves.** It is held when an item enters a cart, transferred to the order
  at checkout, consumed on dispatch, and released on cancel or expiry. Before this phase
  stock never changed at all.
- **Batches and FEFO.** Allocation takes the soonest-expiring batch first, splits across
  batches when needed, and refuses batches inside the minimum-shelf-life window.
- **Reservations expire**, so abandoned checkouts give stock back (periodic job, 60s).
- **Order state machine.** Illegal transitions are rejected; every change is audited.
- **COD cannot be dispatched unconfirmed** — enforced in the service layer, ready for Feature 1.
- **One order per checkout.** Re-submitting the same cart returns the existing draft.
- **Channel seam.** `ChannelAdapter` with `WEBSITE` as the only implementation; orders carry `channel`.
- 80 tests passing, 1 skipped (see Known Gaps).

Bugs found and fixed on the way: the cart was never cleared after payment (so a returning
customer saw old items and could re-reserve stock), and `CartOrderItem` had no link to what
was actually sold beyond free-text size/colour.

### 2. FILES CREATED

| Path | Purpose |
|---|---|
| `backend/catalog/models.py` | `ProductVariant`: SKU, price/MRP in paise, options, perishable flag, one-default-per-product constraint |
| `backend/catalog/admin.py` | Variant admin showing price, on-hand and available |
| `backend/catalog/apps.py`, `catalog/__init__.py` | App wiring |
| `backend/catalog/migrations/0001_initial.py` | Creates `catalog_productvariant` |
| `backend/catalog/migrations/0002_backfill_default_variants.py` | One default variant per existing product; price converted to paise |
| `backend/inventory/models.py` | `Batch`, `StockMovement` (append-only ledger), `StockReservation`, `Channel`, `MovementKind` |
| `backend/inventory/services.py` | Availability, FEFO/FIFO allocation, reserve/release/consume, expiry, alerts, batch reconciliation |
| `backend/inventory/adapters.py` | `ChannelAdapter` seam; `WebsiteChannelAdapter` only |
| `backend/inventory/jobs.py` | Periodic `inventory.expire_reservations` (every 60s) |
| `backend/inventory/admin.py` | Batch admin; read-only ledger and reservation admin |
| `backend/inventory/apps.py`, `inventory/__init__.py` | App wiring |
| `backend/inventory/migrations/0001_initial.py` | Creates batch, movement, reservation tables |
| `backend/inventory/migrations/0002_backfill_opening_stock.py` | Opening batch + ADJUSTMENT movement per variant from `Product.stock_qty` |
| `backend/store/order_state.py` | Order/payment/delivery state machine; COD dispatch guard; stock hooks |
| `backend/core/phone.py` | Indian phone normalisation to E.164 and log masking |
| `backend/inventory/tests/test_inventory.py` | 40 tests for F-B |
| `backend/store/migrations/0028_variant_channel_cod_fields.py` | Order and cart field additions |

### 3. FILES MODIFIED

| Path | What changed and why |
|---|---|
| `backend/store/models.py` | Added to `CartOrder`: `payment_method`, `channel`, `pincode`, `phone_e164`, `idempotency_key` (unique). Added to `CartOrderItem`: `variant`. Added to `Cart`: `variant`, `updated_at` (drives Feature 4 abandonment). Two new choice lists. **No existing field changed or removed** |
| `backend/store/views.py` | Cart: resolves the variant, reserves stock through the ledger, replaces its own hold when quantity changes, releases on line delete, and checks authorisation before touching stock. Checkout: one draft per cart, validates `payment_method`, stores pincode and normalised phone, links each line to its variant, and transfers cart holds to the order. Payment success: routes through the state machine and clears the paid cart |
| `backend/store/serializers.py` | Product responses now include `variants` with live availability and, for perishable goods, the earliest best-before a shopper could receive |
| `backend/backend/settings.py` | Registered `catalog` and `inventory`; added four inventory settings |
| `backend/.env`, `backend/.env.example` | Four inventory variables documented |
| `backend/conftest.py` | The `product` fixture now creates a default variant and opening stock, mirroring the backfill |
| `backend/pytest.ini` | Added `inventory/tests` to testpaths |
| `frontend/src/views/plugin/addToCart.jsx` | Stops sending price and shipping (the server ignores them), and shows the real reason when the server refuses, e.g. "Only 2 left in stock" instead of failing silently |

### 4. MIGRATIONS ADDED

| Name | What it does | Apply | Roll back |
|---|---|---|---|
| `catalog.0001_initial` | Creates `catalog_productvariant` | `python manage.py migrate catalog` | `python manage.py migrate catalog zero` |
| `store.0028_variant_channel_cod_fields` | Adds variant/channel/COD/idempotency fields | `python manage.py migrate store` | `python manage.py migrate store 0027` |
| `catalog.0002_backfill_default_variants` | One default variant per product (data) | `python manage.py migrate catalog` | `python manage.py migrate catalog 0001` |
| `inventory.0001_initial` | Creates batch, movement, reservation tables | `python manage.py migrate inventory` | `python manage.py migrate inventory zero` |
| `inventory.0002_backfill_opening_stock` | Opening batch + movement per variant (data) | `python manage.py migrate inventory` | `python manage.py migrate inventory 0001` |

`python manage.py migrate` applies all five in dependency order.

**Roll back in this order** (inventory first, then catalog, then store), because `Batch.variant`
is `PROTECT` and will refuse to let a variant be deleted while batches exist:

```
python manage.py migrate inventory zero
python manage.py migrate catalog zero
python manage.py migrate store 0027
```

The full rollback-and-reapply cycle was executed on a copy of the seeded database.
Both data migrations only delete rows they created.

### 5. ENV VARS ADDED

| Name | Purpose | Example | Required |
|---|---|---|---|
| `STOCK_ALLOCATION_STRATEGY` | `FEFO` (default) or `FIFO` | `FEFO` | No |
| `STOCK_RESERVATION_TTL_MINUTES` | How long a checkout holds stock | `30` | No |
| `MIN_SHELF_LIFE_ON_DISPATCH_DAYS` | Batches expiring sooner are never auto-allocated | `30` | No |
| `EXPIRY_ALERT_DAYS` | Owner alert horizon for approaching expiry | `45` | No |

### 6. TESTS ADDED

```
cd backend
python -m pytest -q
```

Result: **80 passed, 1 skipped** (39 from F-A, 41 new).

| Group | What the tests prove |
|---|---|
| Variants | One default per product enforced by a DB constraint; backfilled paise price equals the legacy Decimal exactly; several non-default variants allowed |
| Ledger | Available stock equals the sum of movements; wrong-sign and zero movements rejected; movements are append-only; every movement is audited with actor |
| FEFO | Soonest expiry taken first; splits across batches; FIFO mode takes the oldest; a batch inside the shelf-life window is never allocated though it still counts as on hand; an expired batch is never allocated; expiry alerts and expired-unsold reports |
| Reservations | A hold lowers available but not on hand; over-reserving fails and holds nothing; expired holds release stock; consuming an order decrements the right batches **exactly once** when run twice; releasing returns stock |
| Channel seam | Only `WEBSITE` is registered; an unknown channel raises; a new adapter can be added and routes through the same ledger |
| Order state | Illegal transitions rejected; cancelling releases stock; **an unconfirmed COD order cannot be dispatched and its stock does not leave**; a prepaid order's dispatch consumes stock once and not again as it moves to Delivered |
| Checkout | Adding to cart holds stock and refuses more than available; changing quantity replaces the hold instead of stacking; removing a line returns stock; **checking out twice with one cart creates one order**; pincode, payment method, channel, E.164 phone and variant all recorded; holds move from cart to order; invalid payment method rejected |
| Phone | Five Indian formats normalise to `+919876543210`; invalid numbers rejected rather than guessed; masking keeps four digits |

### 7. MANUAL VERIFICATION STEPS

From `backend\` with the venv active:

1. `python manage.py migrate` -> five migrations apply.
2. `python -m pytest -q` -> `80 passed, 1 skipped`.
3. `python manage.py runserver`, and in a second terminal `python manage.py run_worker`.
4. Open `http://127.0.0.1:8000/api/v1/products/`. Each product now has a `variants` array with `sku`, `price` and `available_qty`.
5. Note a product's `available_qty`, add that product to your cart in the storefront, and reload the API. `available_qty` has dropped by the quantity you added, while on-hand has not.
6. Remove the line from the cart. `available_qty` goes back up.
7. Django admin -> **Inventory -> Stock reservations**: your holds are listed with an expiry time.
8. Add something to the cart, then leave it. After `STOCK_RESERVATION_TTL_MINUTES` the worker flips the reservation to EXPIRED and availability returns. (Set the value to `1` in `.env` and restart to see it quickly.)
9. Try to add an absurd quantity (say 99999). The storefront shows "Only N left in stock" instead of failing silently.
10. Complete checkout twice from the same cart without paying. Django admin -> **Orders** shows one order, not two.
11. Open that order: `payment method`, `pincode`, `phone e164` and `channel` are filled, and each line has a `variant`.
12. Django admin -> **Inventory -> Batches**: an `OPENING-<SKU>` batch per product with your old `stock_qty`. **Their best-before is empty — set real dates or write them off before trusting expiry alerts.**
13. Add a real batch (Batches -> Add) with a near best-before date, then place an order: **Stock movements** shows the allocation came from the soonest-expiring batch.
14. Mark an order line as shipped in the admin. If the order is COD and unconfirmed, the service layer refuses (Feature 1 will add the confirm button); for a prepaid order a `SALE_OUT` movement appears and on-hand drops.

### 8. ASSUMPTIONS MADE

1. Every product gets exactly one default variant named "Default", with the product's SKU as the variant SKU (a numeric suffix is added if that SKU is already taken).
2. Existing `Size` and `Color` rows are **not** converted into variants. They stay decorative, exactly as the storefront already treats them. Converting them is a catalogue decision for the owner, not a migration I should make silently.
3. Variant prices are copied into paise, but **the legacy Decimal columns remain the source of truth for pricing**. Nothing reads `price_paise` for checkout yet; that switch happens in the money migration.
4. Opening stock becomes one batch per variant with **no best-before**, because the shelf life of pre-existing stock is unknown, and `cost_per_unit_paise = 0`, because historical cost is unknown. Both must be corrected by the owner before margin (Feature 12) and expiry alerts are meaningful.
5. `Batch.quantity_remaining` is a **derived property, not a stored column** as the brief listed it. A stored counter would be a second source of truth able to drift from the ledger, which contradicts Feature 10's acceptance criterion. Reported as a deliberate deviation.
6. Cart lines reserve stock immediately on add, not at checkout. This is stricter than most Indian D2C stores (which reserve at payment) and can make items look unavailable while others browse. `STOCK_RESERVATION_TTL_MINUTES` (default 30) bounds it; lower it if it feels aggressive.
7. `resolve_variant` matches on free-text size/colour and otherwise falls back to the default variant, because the storefront has no variant picker yet. Products keep one variant until the owner creates more.
8. Minimum shelf life (30 days) and the expiry alert horizon (45 days) are guesses. Set them to your real dispatch policy.
9. An expired or too-fresh batch still counts as **on hand** but is not **available**. Stock that physically exists is never hidden from the ledger; it is only excluded from allocation.
10. `ADJUSTMENT` movements may be positive or negative; all other kinds are sign-checked.
11. Order status values are unchanged. The state machine constrains how they may change; it does not rename them. The transition tables encode my reading of the existing flow and are one edit away if your operations differ.
12. `idempotency_key` is the `cart_id`. One cart yields one order; starting a fresh cart starts a fresh order.
13. Phone normalisation accepts Indian mobile numbers only (10 digits starting 6-9, with optional 0/+91/0091 prefixes). Anything else stores an empty `phone_e164` rather than a guess, so international customers will have no WhatsApp number until this is widened.
14. The paid cart is deleted once payment is confirmed. Reservations already belong to the order, so this does not release stock.
15. Dispatch consumes stock when a line first enters `Shipping Processing`, not at payment. If you pick and pack before marking the order, move the hook.
16. `can_dispatch()` reads `cod_confirmed_at` defensively so it works both before and after the Feature 1 migration; today no COD order can be dispatched at all, because nothing sets that field yet.
17. `Product.stock_qty` is left in place and still shown in the admin, but is now **stale** — it is no longer the source of truth. It will be removed or turned into a derived display in a later phase.

### 9. KNOWN GAPS

- **The concurrency test is skipped on SQLite and has not yet been run on PostgreSQL.** `select_for_update` is a no-op on SQLite, so the test refuses to pass for the wrong reason. PostgreSQL could not be installed in my build environment, so Feature 10's "two concurrent checkouts for the last unit" acceptance criterion is **written but not yet demonstrated**. Run it against Postgres before trusting concurrent checkout: set `DATABASE_URL` to a Postgres URL and run `python -m pytest inventory/tests -k concurrent -q`.
- `Product.stock_qty` and the ledger will drift the moment someone edits `stock_qty` in the admin. Nothing reconciles them yet.
- No owner UI for batches beyond Django admin, and no production-receipt screen.
- Expiry alerts are computed (`batches_nearing_expiry`, `expired_unsold_batches`) but not yet delivered anywhere — that is Feature 5's alerting, in Phase 2.
- The storefront has no variant picker, no stock indicator on the product page and no best-before display yet. The API exposes all three; the UI work belongs with Features 2, 3 and 5.
- Reservations are not yet taken for orders created outside our checkout; the seam exists but no other channel writes to it.
- `perishable` defaults to False on every backfilled variant, so no product shows a best-before until the owner ticks it.
- Frontend verified by production build and by reading each changed path, not by an automated browser test.
- All F-A known gaps still stand.

### 10. NOT DONE AND WHY

- **Money migration** (legacy Decimal -> paise everywhere): still its own phase. Variants carry paise, but checkout maths still uses the legacy Decimal columns, so nothing changed for customers.
- **Tax and coupon bugs** unchanged and still flagged in code; both belong with the pricing work.
- **Features 1 and 2** remain blocked on Razorpay and WhatsApp details from the owner.
- **Removal of multi-vendor residue:** proposals R1-R21 still not approved, still not done.
