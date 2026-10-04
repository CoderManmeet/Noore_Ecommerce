// Checkout smoke suite (phases G3 and G4): Cash on Delivery end to end, the online payment
// hand-off to Razorpay, the owner's order handling, and "Buy again".
//
// Accounts come from `python manage.py seed_e2e` (smoke-suite database only).
import { test, expect } from '@playwright/test';

const OWNER = 'owner@e2e.test';
const CUSTOMER = 'customer@e2e.test';
const PASSWORD = 'E2e-only-Passw0rd!';

const signIn = async (page, email) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(PASSWORD);
    const token = page.waitForResponse((r) => r.url().includes('/user/token/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign In' }).click();
    expect((await token).status()).toBe(200);
    await expect.poll(async () => (await page.context().cookies()).some((c) => c.name === 'access_token')).toBe(true);
};

const signOut = async (page) => {
    await page.goto('/logout');
    await expect.poll(async () => (await page.context().cookies()).some((c) => c.name === 'access_token')).toBe(false);
};

const addCandle = async (page, slug, size) => {
    await page.goto(`/detail/${slug}`);
    await page.getByTestId('option-Size').getByRole('button', { name: size }).click();
    const added = page.waitForResponse((r) => r.url().includes('/cart-view/') && r.request().method() === 'POST');
    await page.getByTestId('add-to-cart').click();
    expect((await added).status()).toBeLessThan(300);
    await expect(page.getByTestId('add-to-cart')).toHaveText(/Add to bag/);
};

const goToCheckout = async (page, email = 'guest@example.com') => {
    await page.goto('/cart/');
    await page.getByLabel('Full Name').fill('Asha Rao');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Mobile').fill('9876543210');
    await page.getByLabel('Address', { exact: true }).fill('12 MG Road');
    await page.getByLabel('City').fill('Ludhiana');
    await page.getByLabel('State').fill('Punjab');
    await page.getByLabel('PIN code').fill('141001');
    await page.getByRole('button', { name: 'Go to checkout' }).click();
    await expect(page).toHaveURL(/\/checkout\//);
    await expect(page.getByTestId('payment-methods')).toBeVisible();
};

const confirmDialog = async (page) => {
    await page.getByRole('button', { name: 'Yes' }).click();
};

test('G3: a guest places a Cash on Delivery order end to end and can ask for an account link', async ({ page }) => {
    await addCandle(page, 'noore-vanilla-bean', '200 g');
    await goToCheckout(page);

    // Online payment is the default; the customer switches to Cash on Delivery.
    await expect(page.getByLabel('UPI / Card / Netbanking')).toBeChecked();
    await page.getByLabel('Cash on delivery').check();
    await expect(page.getByTestId('checkout-summary')).toContainText('You pay ₹878 in cash when your order arrives');
    await page.getByTestId('place-cod').click();

    await expect(page).toHaveURL(/\/order\//);
    await expect(page.getByTestId('order-state')).toContainText('Order placed. Thank you!');
    await expect(page.getByTestId('order-state')).toContainText('₹878');
    await expect(page.getByTestId('confirmation-total')).toHaveText('₹878');
    await expect(page.locator('body')).not.toContainText('$');

    // The cart is empty again.
    await page.goto('/cart/');
    await expect(page.getByText('Your Cart Is Empty')).toBeVisible();

    // Guest: "Create an account to track this order" (the link goes to the order's email only).
    await page.goBack();
    await expect(page.getByTestId('account-invite')).toContainText('guest@example.com');
    await page.getByRole('button', { name: 'Email me the link' }).click();
    await expect(page.getByTestId('account-invite-message')).toContainText('we have emailed a link');
});

test('G3: online payment hands the stored total to Razorpay Checkout and nothing secret', async ({ page }) => {
    // The suite has no Razorpay keys, so the two calls that would reach Razorpay are replaced:
    // our server's "start" answer, and Razorpay's checkout script. Everything up to the
    // hand-off (what the page asks for and what it passes to Razorpay) is real.
    let startedFor = null;
    await page.route('**/payments/razorpay/start/**', async (route) => {
        startedFor = route.request().url();
        await route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify({
                order_oid: 'x',
                options: {
                    key: 'rzp_test_e2eKeyId', amount: 127800, currency: 'INR', name: 'Noore Candles',
                    description: 'Order', order_id: 'order_E2Ehandoff',
                    prefill: { name: 'Asha Rao', email: 'guest@example.com', contact: '+919876543210' },
                },
            }),
        });
    });
    await page.route('https://checkout.razorpay.com/v1/checkout.js', (route) => route.fulfill({
        contentType: 'application/javascript',
        body: 'window.Razorpay = function (options) { window.__rzpOptions = options; this.on = function () {}; this.open = function () { window.__rzpOpened = true; }; };',
    }));

    await addCandle(page, 'noore-sandalwood', '300 g');
    await goToCheckout(page);
    await expect(page.getByTestId('pay-online')).toHaveText('Pay ₹1,199');
    await page.getByTestId('pay-online').click();

    await expect.poll(() => page.evaluate(() => window.__rzpOpened === true)).toBe(true);
    expect(startedFor).toMatch(/\/payments\/razorpay\/start\/[a-z]+\/$/);
    const options = await page.evaluate(() => {
        const { handler, ...rest } = window.__rzpOptions;
        return { ...rest, hasHandler: typeof handler === 'function' };
    });
    expect(options.order_id).toBe('order_E2Ehandoff');
    expect(options.currency).toBe('INR');
    expect(options.key).toMatch(/^rzp_test_/);
    expect(options.hasHandler).toBe(true);
    expect(JSON.stringify(options)).not.toMatch(/secret/i);

    // Still on checkout and still unpaid: only Razorpay's confirmation can change that.
    await expect(page).toHaveURL(/\/checkout\//);
});

test('G3 + G4: owner confirms, ships and delivers a COD order; the customer buys it again', async ({ page }) => {
    // --- the customer orders two candles, Cash on Delivery
    await signIn(page, CUSTOMER);
    await addCandle(page, 'noore-lavender', '100 g');
    await addCandle(page, 'noore-vanilla-bean', '100 g');
    await goToCheckout(page, CUSTOMER);
    await page.getByLabel('Cash on delivery').check();
    await page.getByTestId('place-cod').click();
    await expect(page.getByTestId('order-state')).toContainText('Order placed');
    const oid = page.url().split('/order/')[1].replace(/\//g, '');
    await signOut(page);

    // --- the owner handles it
    await signIn(page, OWNER);
    await page.goto('/owner/orders/');
    await expect(page.getByTestId('owner-orders')).toContainText(`#${oid}`);
    await page.goto(`/owner/orders/${oid}/`);
    await expect(page.getByTestId('owner-cod-state')).toContainText('Not confirmed');

    // Shipping before "Confirm COD" is refused by the server.
    await page.getByRole('button', { name: 'Mark shipped' }).click();
    await expect(page.getByText('has not been confirmed by the customer yet')).toBeVisible();
    await page.getByRole('button', { name: 'OK' }).click();
    await expect(page.getByTestId('owner-delivery-status').first()).toHaveText('On Hold');

    await page.getByRole('button', { name: 'Confirm COD' }).click();
    await confirmDialog(page);
    await expect(page.getByTestId('owner-cod-state')).toContainText('Confirmed with customer');

    await page.getByLabel('Tracking number').fill('AWB-E2E-1');
    await page.getByRole('button', { name: 'Mark shipped' }).click();
    await expect(page.getByTestId('owner-delivery-status').first()).toHaveText('Shipped');
    await page.getByRole('button', { name: 'Mark delivered' }).click();
    await expect(page.getByTestId('owner-order-status')).toHaveText('Fulfilled');

    await page.getByRole('button', { name: 'Mark cash collected' }).click();
    await confirmDialog(page);
    await expect(page.getByTestId('owner-payment-status')).toHaveText('paid');
    await signOut(page);

    // --- the customer buys the same order again from their order history
    await signIn(page, CUSTOMER);
    await page.goto('/customer/orders/');
    const row = page.getByTestId('customer-order').filter({ hasText: `#${oid}` });
    await expect(row).toBeVisible();
    await row.getByTestId('buy-again').click();

    await expect(page).toHaveURL(/\/cart\/$/);
    await expect(page.getByTestId('cart-line')).toHaveCount(2);
    await expect(page.getByTestId('summary-subtotal')).toHaveText('₹998');
    await expect(page.getByTestId('summary-shipping')).toHaveText('₹79');
    await expect(page.getByTestId('summary-total')).toHaveText('₹1,077');

    // A delivered product can now be reviewed by this customer; the review waits for moderation.
    await page.goto('/detail/noore-lavender');
    await page.locator('#reviewText').fill('Burns evenly and smells lovely.');
    await page.getByRole('button', { name: 'Submit review' }).click();
    await expect(page.getByTestId('review-box')).toContainText('will appear once it has been checked');
    await expect(page.getByText('Burns evenly and smells lovely.')).toHaveCount(0);
});
