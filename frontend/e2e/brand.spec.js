// Brand and storefront checks (phase G4.5): the storefront reads as Noore Candles, a shopper
// never meets marketplace wording, and only staff can reach the admin area.
import { test, expect } from '@playwright/test';

const OWNER = 'owner@e2e.test';
const CUSTOMER = 'customer@e2e.test';
const PASSWORD = 'E2e-only-Passw0rd!';
const FORBIDDEN = /vendor/i;

const signIn = async (page, email) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(PASSWORD);
    const token = page.waitForResponse((r) => r.url().includes('/user/token/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign In' }).click();
    expect((await token).status()).toBe(200);
    await expect.poll(async () => (await page.context().cookies()).some((c) => c.name === 'access_token')).toBe(true);
    await expect(page).toHaveURL(/\/$/);
};

// Everything a shopper can see or follow on the page that is currently open.
const surfaceOf = (page) => page.evaluate(() => ({
    title: document.title,
    text: document.body.innerText,
    links: Array.from(document.querySelectorAll('a[href]')).map((a) => a.getAttribute('href')),
    alts: Array.from(document.querySelectorAll('img')).map((img) => img.getAttribute('alt') || ''),
    labels: Array.from(document.querySelectorAll('[aria-label],[title]')).map((el) => `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`),
}));

test('logged out, the word "vendor" is not reachable anywhere a shopper can navigate', async ({ page }) => {
    test.setTimeout(180_000);
    const queue = ['/'];
    const seen = new Set();
    const problems = [];

    while (queue.length > 0 && seen.size < 60) {
        const path = queue.shift();
        if (seen.has(path)) continue;
        seen.add(path);

        await page.goto(path);
        await expect(page.locator('main').first()).toBeVisible();
        // Let the page's own data arrive (product lists, prices) before reading it.
        await page.waitForLoadState('networkidle');

        const surface = await surfaceOf(page);
        if (FORBIDDEN.test(path)) problems.push(`${path}: the address itself`);
        if (FORBIDDEN.test(surface.title)) problems.push(`${path}: page title "${surface.title}"`);
        if (FORBIDDEN.test(surface.text)) problems.push(`${path}: visible text`);
        surface.alts.filter((alt) => FORBIDDEN.test(alt)).forEach((alt) => problems.push(`${path}: image alt "${alt}"`));
        surface.labels.filter((label) => FORBIDDEN.test(label)).forEach((label) => problems.push(`${path}: label "${label.trim()}"`));
        surface.links.filter((href) => FORBIDDEN.test(href)).forEach((href) => problems.push(`${path}: link to ${href}`));
        expect(surface.title, `title of ${path}`).toContain('Noore');

        surface.links
            .filter((href) => href && href.startsWith('/') && !href.startsWith('//'))
            .map((href) => href.split('#')[0])
            .filter((href) => href && !seen.has(href) && !queue.includes(href))
            .forEach((href) => queue.push(href));
    }

    expect(problems, problems.join('\n')).toEqual([]);
    // The crawl really did walk the shop: home, listing, products, policies, sign-in.
    expect(seen.size).toBeGreaterThan(12);
    expect([...seen].some((path) => path.startsWith('/detail/'))).toBe(true);
    expect(seen.has('/shop')).toBe(true);
    expect(seen.has('/about')).toBe(true);
    expect(seen.has('/login')).toBe(true);
});

test('every page carries the Noore title, favicon and logo', async ({ page }) => {
    for (const path of ['/', '/shop', '/about', '/cart/', '/contact', '/login']) {
        await page.goto(path);
        await expect(page).toHaveTitle(/Noore/);
        await expect(page.getByRole('link', { name: 'Noore home' }).first()).toBeVisible();
        await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/favicon.svg');
    }
    await page.goto('/');
    await expect(page.getByTestId('announcement')).toHaveText('Free shipping on orders of ₹999 or more');
});

test('a signed-in customer never sees the admin area and is never sent to a shop sign-up page', async ({ page }) => {
    await signIn(page, CUSTOMER);
    await expect(page.getByTestId('admin-link')).toHaveCount(0);
    await expect(page.locator('a[href*="admin-area"]')).toHaveCount(0);

    for (const path of ['/admin-area/dashboard/', '/vendor/dashboard/', '/vendor/register/', '/vendor/products/', '/owner/orders/']) {
        await page.goto(path);
        await expect(page.getByTestId('not-found')).toBeVisible();
        expect(page.url()).toContain(path);  // not redirected anywhere
    }
});

test('a signed-out visitor gets the not-found page for dashboard addresses', async ({ page }) => {
    for (const path of ['/admin-area/dashboard/', '/vendor/dashboard/', '/vendor/register/', '/some/unknown/page']) {
        await page.goto(path);
        await expect(page.getByTestId('not-found')).toBeVisible();
    }
});

test('staff reach every dashboard screen under /admin-area/ and old addresses redirect there', async ({ page }) => {
    test.setTimeout(120_000);
    await signIn(page, OWNER);
    await page.getByTestId('admin-link').click();
    await expect(page).toHaveURL(/\/admin-area\/dashboard\/$/);

    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));

    const screens = ['dashboard/', 'products/', 'product/new/', 'orders/', 'earning/', 'reviews/', 'coupon/',
        'notifications/', 'settings/', 'owner/orders/', 'owner/reviews/'];
    for (const screen of screens) {
        await page.goto(`/admin-area/${screen}`);
        await page.waitForLoadState('networkidle');
        await expect(page.getByTestId('not-found')).toHaveCount(0);
        await expect(page.locator('#main, .container, .container-fluid').first()).toBeVisible();
    }
    expect(errors, errors.join('\n')).toEqual([]);

    // The dashboard's own links use the new addresses: no redirect on a click.
    await page.goto('/admin-area/dashboard/');
    await page.getByRole('link', { name: /Products/ }).first().click();
    await expect(page).toHaveURL(/\/admin-area\/products\/$/);

    // Old addresses typed by hand still land staff on the new ones.
    await page.goto('/vendor/products/');
    await expect(page).toHaveURL(/\/admin-area\/products\/$/);
    await page.goto('/owner/orders/');
    await expect(page).toHaveURL(/\/admin-area\/owner\/orders\/$/);
    await expect(page.getByTestId('owner-orders')).toBeVisible();
});

test('a staff account with no shop linked is told how to link it, never sent to a sign-up form', async ({ page }) => {
    await signIn(page, OWNER);
    // Pretend this staff account does not own the shop yet (a freshly created superuser).
    await page.addInitScript(() => {
        const original = document.cookie;
        Object.defineProperty(document, 'cookie', {
            get: () => original,
            set: (value) => { },
            configurable: true,
        });
    });
    await page.evaluate(() => {
        // Rewrite the access token's vendor_id claim to 0, exactly as it is for a new superuser.
        const read = (name) => document.cookie.split('; ').find((c) => c.startsWith(`${name}=`))?.split('=')[1];
        const token = read('access_token');
        const [header, payload, signature] = token.split('.');
        const body = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
        body.vendor_id = 0;
        const encoded = btoa(JSON.stringify(body)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        document.cookie = `access_token=${header}.${encoded}.${signature}; path=/`;
    });

    await page.goto('/admin-area/product/new/');
    await expect(page.getByTestId('shop-not-ready')).toBeVisible();
    await expect(page.getByTestId('shop-not-ready')).toContainText('claim_shop');
    expect(page.url()).toContain('/admin-area/product/new/');
    await expect(page.locator('body')).not.toContainText(/register.{0,20}vendor/i);
    await expect(page.locator('body')).not.toContainText('Shop Avatar');

    // The screens that do not need a shop still open.
    await page.goto('/admin-area/owner/orders/');
    await expect(page.getByTestId('owner-orders')).toBeVisible();
});

for (const [name, viewport] of [['mobile', { width: 390, height: 844 }], ['desktop', { width: 1280, height: 800 }]]) {
    test(`home, about, shop and product page hold together at ${name} width`, async ({ page }) => {
        await page.setViewportSize(viewport);
        for (const path of ['/', '/about', '/shop', '/detail/noore-lavender']) {
            await page.goto(path);
            await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
            await page.waitForLoadState('networkidle');
            // Nothing spills sideways off the screen.
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
            expect(overflow, `${path} is wider than the screen by ${overflow}px`).toBeLessThanOrEqual(1);
        }
        await page.goto('/shop');
        await expect(page.getByTestId('product-card')).toHaveCount(3);
        // Listing photos share one ratio (4:5).
        const ratios = await page.getByTestId('product-card').locator('div.aspect-\\[4\\/5\\]').evaluateAll((nodes) => nodes.map((node) => Math.round((node.clientWidth / node.clientHeight) * 100)));
        expect(new Set(ratios).size).toBe(1);
        expect(ratios[0]).toBe(80);
    });
}
