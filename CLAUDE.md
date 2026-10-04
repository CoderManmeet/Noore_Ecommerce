# CLAUDE.md — standing rules for this repository

Read this file, docs/ROADMAP.md and docs/BUILD_LOG.md in full before starting any phase.
Feature specs and phase order live in docs/ROADMAP.md (including the data-model map,
state-machine tables, bug register and removal proposals in its appendices).
History and every past decision live in docs/BUILD_LOG.md.

## 1. Project identity

Single-brand Indian D2C store. One owner, own manufacturing, NO vendors, NO marketplace
sellers, NO commissions. Never introduce multi-vendor concepts. The codebase started as a
Udemy multivendor course project; vendor-named code still exists (see ROADMAP Appendix E)
and is being retired, not extended.

- Backend: Django 4.2.7 + Django REST Framework 3.14, SimpleJWT. Python 3.11.
- Frontend: React 18 + Vite 4, Zustand, Axios. Node 20 LTS.
- Database: SQLite locally (`backend/db.sqlite3`); PostgreSQL required in production and
  for the concurrency test. Selected by `DATABASE_URL`.
- Market: India. Currency must be INR (legacy code still shows USD — see ROADMAP G1).
- Payments: Razorpay (primary, being integrated). Stripe and PayPal are legacy, hardened,
  and will be removed once Razorpay is live.
- Messaging: Meta WhatsApp Cloud API (direct).

## 2. Environment (Windows, PowerShell)

Repo root contains `backend/`, `frontend/`, `docs/`. The folder path may contain spaces:
always quote paths.

Backend (run from `backend\`):

    .\venv\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    python manage.py migrate
    python manage.py runserver                  # http://127.0.0.1:8000
    python manage.py run_worker                 # job worker, separate terminal
    python manage.py run_worker --once          # process one batch and exit
    python -m pytest -q                         # full suite
    python -m pytest tests/test_security.py -q  # one file
    python -m pytest -q -k "some_test_name"     # one test

Concurrency test (PostgreSQL only; skips on SQLite by design):

    $env:DATABASE_URL = "postgres://ecom:ecom@127.0.0.1:5432/ecom"
    python -m pytest inventory/tests/test_inventory.py -k concurrent -q
    Remove-Item Env:DATABASE_URL

The Postgres user needs CREATEDB (pytest creates a test database).

Frontend (run from `frontend\`):

    npm install
    npm run dev                                 # http://localhost:5173
    npm run build                               # production build must succeed
    npx playwright test                         # once phase G0 has added Playwright

Owner account setup after creating a superuser:

    python manage.py claim_shop --list
    python manage.py claim_shop --email you@example.com

(then log out and back in: the dashboard is driven by the `vendor_id` JWT claim.)

`backend/.env` must exist; `DJANGO_SECRET_KEY` is required. Every variable is documented
in `backend/.env.example`. Dev email goes to the terminal (console backend).

Traps:
- `backend/pytest.ini` has explicit `testpaths`. A test file in a NEW app is silently NOT
  collected until its directory is added there. Always check the collected count.
- Five frontend files import `../plugin/AddToCart`; the file is `addToCart.jsx`. Works on
  Windows, breaks Linux builds (fixed in G0).
- Tests must never write into `backend/media/` (fixed in G0 via MEDIA_ROOT override).

## 3. Architecture facts — never violate these

- MONEY is integer paise in all new code: `core.money.to_paise`, `from_paise`, `format_inr`
  (float is rejected). Already paise: `catalog.ProductVariant.price_paise/mrp_paise`,
  `inventory.Batch.cost_per_unit_paise`. STILL LEGACY Decimal rupees until phase G1, do not
  touch outside G1: `Product.price/old_price/shipping_amount`, every money field on
  `Cart`, `CartOrder`, `CartOrderItem`, plus `Coupon.discount` (int %), `Tax.rate` (int %),
  `ConfigSettings.service_fee_*`.
- STOCK is derived from the append-only ledger `inventory.StockMovement`. Read with
  `inventory.services.on_hand_qty`, `available_qty`, `batch_on_hand`. Write ONLY through
  `record_movement`, `receive_production`, `reserve`, `release`, `release_for_cart`,
  `release_for_order`, `attach_reservations_to_order`, `consume_for_order`,
  `expire_due_reservations`. Allocation is FEFO via `allocatable_batches`. Never store or
  increment a stock counter. `Product.stock_qty` is STALE and must not be read for logic.
  Channels go through `inventory.adapters.get_adapter(channel)`; only WEBSITE exists.
- ORDER STATUS changes go ONLY through `store/order_state.py`: `set_payment_status`,
  `set_order_status`, `set_delivery_status`, `cancel_order`, `mark_paid`, `can_dispatch`.
  Never assign `payment_status`, `order_status` or `delivery_status` directly. Transition
  tables are in ROADMAP Appendix C.
- BACKGROUND WORK goes through `core.jobs`: `@job("name")`, `@periodic("name",
  every_seconds=N)`, `enqueue(name, payload, run_after=aware_dt, dedupe_key=...)`.
  Delivery is at-least-once, so every handler must be idempotent. No Celery, no Redis.
- EXTERNAL EVENTS (webhooks, payment confirmations, inbound messages) are claimed once with
  `core.idempotency.claim_event(provider, event_id)` inside the same
  `transaction.atomic()` as the side effect.
- AUDIT: `core.audit.record(action, instance, before=..., after=..., reason=...)`; attribute
  system work with `core.audit.acting_as(user_or_None, label="system:...")`.
  `core/signals.py` already auto-audits tracked fields on Product, CartOrder and
  CartOrderItem (see `TRACKED_FIELDS`) — do not double-audit those. Append-only tables
  subclass `core.models.AppendOnlyModel`.
- OWNER = Django staff user (`is_staff=True`). Owner endpoints use
  `core.permissions.IsStaffOwner` (or `PublicReadStaffWrite` for public-read resources).
- CUSTOMER DATA endpoints use `core.permissions.ensure_self_or_staff(request, user_id)` and
  `ensure_order_access(request, order)`. DRF defaults to `IsAuthenticated`; a public view
  must declare `permission_classes = (AllowAny,)` explicitly. Rate-limit with
  `throttle_scope` = auth | otp | checkout | review | webhook.
- TIME: DB is UTC (`USE_TZ=True`). Business rules use `settings.BUSINESS_TIME_ZONE`
  (Asia/Kolkata) via `core.timeutils.business_now`, `business_today`, `to_business`,
  `require_aware`. Never create a naive datetime.
- PHONES: `core.phone.to_e164` / `try_to_e164`; log only `core.phone.mask(...)`.
- SERIALIZERS: model serializers extend `core.serializers.SafeDepthModelSerializer`. Never
  expose a raw User; use `core.serializers.PublicUserSerializer` for others and
  `userauths.serializer.UserSerializer` only for the signed-in user's own data.
- LOGGING: `logging.getLogger(__name__)`; handlers mask PII via
  `core.logmask.PIIMaskingFilter`. Never `print()`. Never log phones, addresses, payment ids
  or message bodies at INFO.
- FRONTEND API calls use the single instance in `frontend/src/utils/axios.js` (it attaches
  and refreshes the JWT). Never create another Axios instance. URLs live in
  `frontend/src/utils/constants.js` (overridable by `VITE_*` env vars).

## 4. The 12 absolute rules

1. FILE-FIRST. Never modify a file you have not read in full this session. If a file you
   need does not exist, say so and stop; never invent its contents.
2. NO PLACEHOLDERS. No "rest of code here", no TODO stubs, no pseudocode, no ellipses.
3. FULL FILES. When you change a file, the result must be the complete, runnable file.
4. ADDITIVE BY DEFAULT. Never delete or rename a model, field, endpoint or component
   without the owner's written approval. Propose removals; do not perform them.
5. NO SECRETS IN CODE. Every credential, key, token, webhook secret and phone-number id
   comes from the environment and is documented in `.env.example`. Never print a secret.
6. MONEY IS INTEGER PAISE. Never float. Never silently change legacy money storage.
7. UTC IN THE DATABASE, Asia/Kolkata FOR BUSINESS RULES. No naive datetimes.
8. EVERY WEBHOOK AND EXTERNAL CALL IS IDEMPOTENT. Store the provider event id with a
   unique constraint; duplicates must change nothing.
9. EVERY STATE CHANGE IS AUDITED with actor, timestamp, before and after.
10. MIGRATIONS ARE SEPARATE AND REVERSIBLE. One per logical change. Never edit an applied
    migration. Document apply and rollback commands.
11. NOTHING SHIPS UNTESTED. Every change has a test that fails before it and passes after.
12. IF UNSURE, ASK. Never fabricate a provider API request, response or webhook payload.

## 5. Git discipline

- Never work on `main`. One branch per phase: `phase/<id>-<slug>` (e.g. `phase/G0-sync`).
- Commit after each logical unit with a clear message.
- Before ANY migration, back up the database:

      New-Item -ItemType Directory -Force -Path backups | Out-Null
      Copy-Item backend\db.sqlite3 "backups\db-$(Get-Date -Format 'yyyyMMdd-HHmmss').sqlite3"

  `backups/` is git-ignored.
- NEVER: run `migrate <app> zero`, delete `db.sqlite3`, force-push, rewrite history, or
  run any destructive shell command (rm -r, Remove-Item -Recurse, git reset --hard,
  git clean) without asking the owner first.

## 6. Definition of done (every phase)

1. `python -m pytest -q` is fully green; state the exact count (passed / skipped).
2. Every new test was demonstrated to FAIL before the change (show it).
3. `npm run build` succeeds.
4. `npx playwright test` passes (from G0 onward), and the phase extends the smoke suite.
5. `docs/BUILD_LOG.md` gets a new section with all ten headings: phase completed; files
   created; files modified; migrations (with apply and rollback commands); env vars; tests
   (with command and count); manual verification steps; assumptions made (exhaustive);
   known gaps; not done and why.
6. Branch committed. Then STOP and wait for the owner's approval.

## 7. Stop conditions — stop and ask the owner when

- a provider payload, request or response shape is unknown;
- a change would alter what any customer is charged;
- a change would delete or rename an existing field, model or endpoint;
- a test cannot be made to pass honestly (never weaken or skip a test to go green);
- the local repo does not match docs/BUILD_LOG.md;
- a legal or compliance interpretation is required.

## 8. Prohibited dark patterns (CCPA Guidelines, 2023)

None of these may be implemented, even if asked for as a "growth" feature:
false urgency (fake timers, false scarcity), basket sneaking (pre-ticked add-ons, items
added without consent), confirm shaming, forced action, subscription traps (hard
cancellation), interface interference, bait and switch, drip pricing (costs revealed late),
disguised advertisement, nagging, trick questions, SaaS billing traps, rogue malware.
Every price, fee and discount is shown before the customer commits. Cancellation is as
easy as sign-up.

## 9. Pointers

Feature specs and phase order live in docs/ROADMAP.md. History lives in
docs/BUILD_LOG.md. Read both before starting any phase.
