# Putting the store online for free

A showcase deployment that costs nothing: the storefront on Vercel, the backend on Render, the
database on Neon, product photos on Cloudinary. No credit card, no domain.

Allow about an hour the first time.

**What "free" means here.** These tiers are meant for demos and side projects, and most of them
forbid running an actual business on them. This is right for a portfolio piece. The day Noore
takes real money, move to a small paid server with `docs/DEPLOY.md`; nothing you do here is
wasted.

**The one rough edge.** A free Render service goes to sleep after 15 minutes with no visitors.
The next visitor waits 30 to 50 seconds while it wakes. Open the site yourself a minute before
you show it to anyone.

---

## Before you start

| You need | Where | Cost |
|---|---|---|
| A GitHub account with this project pushed to a repository | github.com | Free |
| A Render account | render.com | Free, no card |
| A Neon account | neon.tech | Free, no card |
| A Cloudinary account | cloudinary.com | Free, no card |
| A Vercel account | vercel.com | Free, no card |

Sign in to all four with the same GitHub account; it makes every step shorter.

### Push the project to GitHub first

If it is not on GitHub yet, from the project folder in PowerShell:

    cd "C:\Users\91788\Downloads\noore_ecom_final\Completed Source Code"
    git init
    git add .
    git commit -m "Noore Candles store"

Then on github.com: **New repository**, name it `noore-store`, **Private**, **Create**. GitHub
shows two lines to run; they look like this:

    git remote add origin https://github.com/YOURNAME/noore-store.git
    git push -u origin main

Check on GitHub that `backend/`, `frontend/`, `render.yaml` and `docs/` are all there.

**`backend/.env` and `backend/db.sqlite3` are deliberately not pushed** (`.gitignore` excludes
them). That is correct: secrets must never go into a repository, and the online store gets its
own empty database.

---

## Step 1 — The database (Neon)

1. Go to neon.tech and sign in with GitHub.
2. **Create project**. Name: `noore`. Region: pick the one nearest India (Singapore or Mumbai if
   offered). Postgres version: leave the default.
3. On the project page, find **Connection string** and copy it. It looks like:

       postgresql://noore_owner:AbC123@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/noore?sslmode=require

4. Paste it into a notepad file. You will need it in step 3. **Treat it like a password.**

> Why not Render's own free database? It is deleted 30 days after it is created, data and all.
> Neon's free database has no expiry.

---

## Step 2 — Photo storage (Cloudinary)

1. Go to cloudinary.com, sign up, and skip any survey.
2. On the dashboard, find **API Environment variable**. It looks like:

       CLOUDINARY_URL=cloudinary://419455555555555:aBcDeF-gHiJkLmNoPqRsTuVwXyZ@dxyz1234

3. Copy **everything after `CLOUDINARY_URL=`** into your notepad file.

> Without this, every product photo disappears the first time the backend restarts: free Render
> services have no disk of their own.

---

## Step 3 — The backend (Render)

1. Go to render.com, sign in with GitHub.
2. **New** > **Blueprint**. Choose your `noore-store` repository. Render finds `render.yaml` and
   offers to create a service called **noore-api**. Click **Apply** / **Create resources**.
3. It will start building and **will fail or come up unhealthy at first** — that is expected,
   because the values you must supply yourself are still blank. Open the **noore-api** service,
   go to **Environment**, and add:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `CLOUDINARY_URL` | the `cloudinary://...` value from step 2 |
   | `SITE_URL` | leave blank for now (step 4 fills it) |
   | `CORS_ALLOWED_ORIGINS` | leave blank for now |
   | `CSRF_TRUSTED_ORIGINS` | leave blank for now |

   Leave `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` blank: the store
   then offers Cash on Delivery only, which is enough for a showcase. (Step 7 adds card and UPI.)

4. **Save, rebuild and deploy.** Watch the log. It should end with the server starting. Your
   address is at the top of the page:

       https://noore-api.onrender.com

5. Check it. Open in a browser:

       https://noore-api.onrender.com/api/v1/health/

   You want `{"status": "ok", "database": true, "cache": true, ...}`. `worker` says `false` for
   now; step 6 fixes that.

6. Create your admin login. On the service page, open the **Shell** tab and run, one at a time:

       python manage.py createsuperuser
       python manage.py claim_shop --email you@example.com

   Use the same email in both. If the Shell tab is not available on the free plan, see
   "If you have no Shell tab" at the end.

---

## Step 4 — The storefront (Vercel)

1. Go to vercel.com, sign in with GitHub, **Add New** > **Project**, pick `noore-store`.
2. **Root Directory**: click **Edit** and choose `frontend`. This matters: the storefront is not
   at the top of the repository.
3. Framework should say **Vite**. Leave the build settings alone (`vercel.json` sets them).
4. Open **Environment Variables** and add:

   | Key | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://noore-api.onrender.com/api/v1/` |
   | `VITE_SERVER_URL` | `https://noore-api.onrender.com/` |
   | `VITE_STORE_NAME` | `Noore Candles` |
   | `VITE_SUPPORT_EMAIL` | your email |
   | `VITE_WHATSAPP_NUMBER` | your number, digits only with 91 in front, e.g. `919876543210` |

   Use your real Render address, and keep the trailing slashes exactly as shown.

5. **Deploy.** You get an address like `https://noore-store.vercel.app`.

> These values are baked in when the site is built, so if you change one later you must redeploy
> on Vercel for it to take effect.

---

## Step 5 — Introduce them to each other

Back on Render, **noore-api** > **Environment**, set all three to your Vercel address with **no
trailing slash**:

| Key | Value |
|---|---|
| `SITE_URL` | `https://noore-store.vercel.app` |
| `CORS_ALLOWED_ORIGINS` | `https://noore-store.vercel.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://noore-store.vercel.app` |

Save and let it redeploy. Now open your Vercel address: the storefront loads and talks to the
backend. The first load after a quiet spell is the slow one.

---

## Step 6 — Keep the background jobs running

Order emails, payment confirmation and abandoned-checkout expiry normally run in a second
process, which the free plan cannot do. Instead, GitHub calls the backend every 15 minutes.

1. On Render, **noore-api** > **Environment**, find `JOBS_RUN_TOKEN`. Render generated it. Click
   to reveal it and copy it.
2. On GitHub, open your repository > **Settings** > **Secrets and variables** > **Actions** >
   **New repository secret**. Add two:

   | Name | Value |
   |---|---|
   | `API_BASE_URL` | `https://noore-api.onrender.com` |
   | `JOBS_RUN_TOKEN` | the value you copied |

3. Open the **Actions** tab, choose **Run store background jobs**, and click **Run workflow** to
   test it now. A green tick means it worked. After that it runs by itself.

Check `https://noore-api.onrender.com/api/v1/health/?strict=1` — `worker` should now say `true`.

> GitHub pauses scheduled workflows in a repository with no activity for 60 days. If your demo
> goes quiet for months, push any commit to wake it.

---

## Step 7 — Payments (optional)

Cash on Delivery works with nothing configured, and shows the whole order flow. To demonstrate
UPI and cards as well, in Razorpay **Test Mode**:

1. Razorpay dashboard > **Account & Settings** > **API Keys** > **Generate Test Key**.
2. On Render add `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. **Account & Settings** > **Webhooks** > **Add New Webhook**:
   - URL: `https://noore-api.onrender.com/api/v1/payments/razorpay/webhook/`
   - Secret: any long random string; put the same string on Render as `RAZORPAY_WEBHOOK_SECRET`
   - Event: `payment.captured`
4. Save on both sides and let Render redeploy. Test UPI id: `success@razorpay`. Test card:
   `4100 2800 0000 1007`, any future expiry, any CVV.

No real money moves in test mode, and no KYC is needed to generate test keys.

---

## Step 8 — Fill the shop

On your Vercel address, sign in with the superuser from step 3, then:

1. **Admin** (top right) > **Add Product**: photo, title, description, price, MRP, stock. Create.
2. Sizes and more stock live in Django admin, at
   `https://noore-api.onrender.com/admin/`:
   - **Catalog** > **Product variants**: one row per size (name `200 g`, options `{"Size": "200 g"}`,
     price and MRP in paise — ₹799 is `79900`).
   - **Inventory** > **Batches**: add a batch to put stock in.
3. Replace the placeholder text: the About page and the four policy pages live in
   `frontend/src/views/policy/`. Edit, commit, push; Vercel redeploys on its own.

---

## Everyday use

| Task | How |
|---|---|
| Deploy a change | `git push`. Render and Vercel both rebuild on their own. |
| See backend errors | Render > noore-api > **Logs** |
| Back up the database | Neon > your project > **Backups**, or use the `pg_dump` line in `docs/DEPLOY.md` |
| Wake the site before a demo | Open it yourself a minute beforehand |

---

## When something is wrong

| What you see | What it means |
|---|---|
| Storefront loads, but no products and the console says CORS | `CORS_ALLOWED_ORIGINS` on Render does not exactly match your Vercel address, or has a trailing slash |
| `DisallowedHost` in the Render log | You are opening the backend on an address that is not its own; use the `.onrender.com` one |
| Product photos vanish after a redeploy | `CLOUDINARY_URL` is missing or wrong |
| Admin pages look unstyled | The build step did not run `collectstatic`; redeploy with **Clear build cache** |
| Health says `"cache": false` | `createcachetable` did not run; redeploy with **Clear build cache** |
| Emails never arrive | Expected: no email provider is configured. Add one later with the Mailgun settings in `backend/.env.example` |
| Everything 404s and you cannot sign in | The database is empty; run `createsuperuser` and `claim_shop` (step 3) |

### If you have no Shell tab

Create the admin account from your own computer instead, pointed at the online database:

    cd backend
    .\venv\Scripts\Activate.ps1
    $env:DATABASE_URL = "<your Neon connection string>"
    python manage.py createsuperuser
    python manage.py claim_shop --email you@example.com
    Remove-Item Env:DATABASE_URL

Remember to clear the variable afterwards, or your next local command will run against the
online database.

---

## What this deployment does not have

- **A custom domain.** Both platforms allow one free; you just have to buy the domain.
- **Real emails.** Nothing is sent until an email provider is configured.
- **Live payments.** Test mode only, by design.
- **Backups you control.** Neon's free plan keeps its own; there is no off-site copy.
- **Always-on.** The 15-minute sleep is the price of free.

`docs/DEPLOY.md` covers the paid setup that fixes all five.