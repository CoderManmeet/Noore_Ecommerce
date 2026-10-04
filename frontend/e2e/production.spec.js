// Smoke check of a DEPLOYED site. Runs only when E2E_BASE_URL is set:
//
//   $env:E2E_BASE_URL = "https://shop.example.in"; npx playwright test; Remove-Item Env:E2E_BASE_URL
//
// It needs no seed data: it uses whatever the first product on the home page is. It places ONE
// Cash on Delivery order under the name "SMOKE TEST - please cancel"; cancel it afterwards in
// the owner's "Handle orders" screen (that returns its stock).
import { test, expect } from '@playwright/test';

test('deployed site: health, search-engine files and policies answer', async ({ page, request, baseURL }) => {
    const health = await request.get(`${baseURL}/api/v1/health/?strict=1`);
    expect(health.status(), 'health check (database, cache and worker)').toBe(200);
    expect((await health.json()).worker.ok).toBe(true);

    const robots = await request.get(`${baseURL}/robots.txt`);
    expect(robots.status()).toBe(200);
    expect(await robots.text()).toContain('Sitemap:');
    const sitemap = await request.get(`${baseURL}/sitemap.xml`);
    expect(sitemap.status()).toBe(200);
    expect(await sitemap.text()).toContain('/detail/');

    for (const path of ['/policy/shipping', '/policy/returns', '/policy/privacy', '/policy/terms', '/contact']) {
        await page.goto(path);
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    }
});

test('deployed site: a shopper can place a Cash on Delivery order', async ({ page }) => {
    await page.goto('/');
    const firstProduct = page.locator('a[href^="/detail/"]').first();
    await expect(firstProduct).toBeVisible();
    const href = await firstProduct.getAttribute('href');

    // The product URL itself carries the product's own title (link previews).
    await page.goto(href);
    await expect(page.getByTestId('product-title')).toBeVisible();
    const title = (await page.getByTestId('product-title').textContent()).trim();
    await expect(page).toHaveTitle(new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    await expect(page.getByTestId('product-price')).toContainText('₹');

    const added = page.waitForResponse((r) => r.url().includes('/cart-view/') && r.request().method() === 'POST');
    await page.getByTestId('add-to-cart').click();
    expect((await added).status()).toBeLessThan(300);

    await page.goto('/cart/');
    await expect(page.getByTestId('cart-line')).toHaveCount(1);
    await expect(page.locator('body')).not.toContainText('$');
    await page.getByLabel('Full Name').fill('SMOKE TEST - please cancel');
    await page.getByLabel('Email').fill('smoke-test@example.com');
    await page.getByLabel('Mobile').fill('9876543210');
    await page.getByLabel('Address', { exact: true }).fill('Smoke test order, do not ship');
    await page.getByLabel('City').fill('Test');
    await page.getByLabel('State').fill('Test');
    await page.getByLabel('PIN code').fill('000000');
    await page.getByRole('button', { name: 'Go to checkout' }).click();

    await expect(page).toHaveURL(/\/checkout\//);
    await page.getByLabel('Cash on delivery').check();
    await page.getByTestId('place-cod').click();
    await expect(page.getByTestId('order-state')).toContainText('Order placed');
    console.log(`Smoke-test order placed: ${page.url()} - cancel it in "Handle orders".`);
});
