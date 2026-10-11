// What a first-time visitor sees while the free backend is still waking up.
//
// The backend is put to sleep after 15 minutes without traffic, and the first request then takes
// tens of seconds. These tests hold the catalogue request back on purpose and check that the
// page is never blank, never silent and never jumps when the data finally lands.

import { test, expect } from '@playwright/test';

// Hold `products/` for `ms`, letting every other request through untouched.
async function delayCatalogue(page, ms) {
    await page.route(/\/api\/v1\/products\/$/, async (route) => {
        await new Promise((resolve) => setTimeout(resolve, ms));
        await route.continue();
    });
}

test.beforeEach(async ({ context }) => {
    // A first-ever visit: nothing cached from an earlier test.
    await context.clearCookies();
});

test('the home page is readable while the server is still starting', async ({ page }) => {
    await delayCatalogue(page, 9000);
    await page.addInitScript(() => {
        try { window.localStorage.clear(); } catch (err) { /* storage blocked */ }
    });

    const started = Date.now();
    await page.goto('/');

    // The words and the button are there long before any data arrives.
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 4000 });
    await expect(page.getByRole('link', { name: /explore the collection/i })).toBeVisible();
    expect(Date.now() - started).toBeLessThan(6000);

    // The collection area holds placeholder cards, not an empty hole.
    await expect(page.getByRole('status', { name: 'Loading candles' })).toBeVisible();

    // And after a few seconds it says, honestly, what is going on.
    await expect(page.getByTestId('waking-notice')).toBeVisible({ timeout: 8000 });

    // Then the real products replace the placeholders.
    await expect(page.getByTestId('home-products')).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('waking-notice')).toHaveCount(0);
    expect(await page.getByTestId('product-card').count()).toBeGreaterThan(0);
});

test('a second visit paints the collection from the cache, with the server still slow', async ({ page }) => {
    // First visit at normal speed fills the cache.
    await page.goto('/');
    await expect(page.getByTestId('home-products')).toBeVisible();

    // Now the server is slow again. The products must appear anyway, from the stored copy.
    await delayCatalogue(page, 9000);
    await page.goto('/');
    await expect(page.getByTestId('home-products')).toBeVisible({ timeout: 4000 });
    expect(await page.getByTestId('product-card').count()).toBeGreaterThan(0);
    // No "starting the server" line: there was nothing to wait for.
    await expect(page.getByTestId('waking-notice')).toHaveCount(0);
});

test('the shop page shows placeholder cards in the real grid shape', async ({ page }) => {
    await page.addInitScript(() => {
        try { window.localStorage.clear(); } catch (err) { /* storage blocked */ }
    });
    await delayCatalogue(page, 6000);
    await page.goto('/shop');

    await expect(page.getByRole('status', { name: 'Loading candles' })).toBeVisible({ timeout: 4000 });
    await expect(page.getByTestId('shop-products')).toBeVisible({ timeout: 20000 });
});

test('the hero photo loads eagerly while listing photos stay lazy', async ({ page }) => {
    // The seeded catalogue has no photographs, so the catalogue is answered here with two that
    // do: the point under test is which loading strategy each <img> gets, not the files.
    const product = (id, title) => ({
        id,
        pid: `p${id}`,
        title,
        slug: `candle-${id}`,
        image: `https://res.cloudinary.com/demo/image/upload/v1/sample-${id}.jpg`,
        featured: id === 1,
        price_from_paise: 49900,
        available_qty: 5,
        variants: [{ id, is_default: true, price_paise: 49900 }],
    });
    await page.route(/\/api\/v1\/products\/$/, (route) =>
        route.fulfill({ json: [product(1, 'Hero candle'), product(2, 'Second candle')] }));
    // Answer the photo requests locally with a 1x1 pixel: a failed photo is drawn as nothing at
    // all by Photo(), which would leave no <img> to inspect.
    const pixel = Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==',
        'base64',
    );
    await page.route(/res\.cloudinary\.com/, (route) => route.fulfill({ contentType: 'image/png', body: pixel }));

    await page.goto('/');
    await expect(page.getByTestId('home-products')).toBeVisible();

    const hero = page.locator('img[src*="sample-1"]').first();
    await expect(hero).toHaveAttribute('loading', 'eager');
    await expect(hero).toHaveAttribute('fetchpriority', 'high');

    // A card inside the collection row is the opposite: it waits its turn.
    const cardPhoto = page.getByTestId('product-card').locator('img').first();
    await expect(cardPhoto).toHaveAttribute('loading', 'lazy');
});