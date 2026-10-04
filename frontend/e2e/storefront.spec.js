// Storefront smoke suite (phases G1 and G2).
//
// Runs against the placeholder catalogue from `python manage.py seed_noore`:
//   three scents, each in 100 g (Rs 499, MRP Rs 599), 200 g (Rs 799, MRP Rs 949) and
//   300 g (Rs 1,199, MRP Rs 1,399), 20 of each in stock, plus the coupon WELCOME10 (10% off).
// Shipping is Rs 79, free from Rs 999.
import { test, expect } from '@playwright/test';

const SCENT = '/detail/noore-lavender';

const addToCart = async (page) => {
    const added = page.waitForResponse((response) => response.url().includes('/cart-view/') && response.request().method() === 'POST');
    await page.getByTestId('add-to-cart').click();
    expect((await added).status()).toBeLessThan(300);
    // The page re-reads the product after adding; wait for the button to settle.
    await expect(page.getByTestId('add-to-cart')).toHaveText(/Add to bag/);
};

const fillAddress = async (page) => {
    await page.getByLabel('Full Name').fill('Asha Rao');
    await page.getByLabel('Email').fill('asha@example.com');
    await page.getByLabel('Mobile').fill('9876543210');
    await page.getByLabel('Address', { exact: true }).fill('12 MG Road');
    await page.getByLabel('City').fill('Ludhiana');
    await page.getByLabel('State').fill('Punjab');
    await page.getByLabel('PIN code').fill('141001');
};

test('G2: choosing a size shows that size\'s price and honest stock, and adds that size to the cart', async ({ page }) => {
    await page.goto(SCENT);
    await expect(page.getByTestId('product-title')).toHaveText('Lavender Scented Candle');

    // Default size.
    await expect(page.getByTestId('product-price')).toHaveText('₹499');
    await expect(page.getByTestId('product-mrp')).toHaveText('₹599');
    await expect(page.getByTestId('product-percent-off')).toHaveText('16% off');

    // Pick 200 g.
    await page.getByTestId('option-Size').getByRole('button', { name: '200 g' }).click();
    await expect(page.getByTestId('product-price')).toHaveText('₹799');
    await expect(page.getByTestId('product-mrp')).toHaveText('₹949');
    await expect(page.getByTestId('product-percent-off')).toHaveText('15% off');
    await expect(page.getByTestId('stock-status')).toHaveText('In stock');
    await expect(page.getByTestId('shipping-line')).toContainText('Shipping ₹79. Free on orders of ₹999 or more.');
    await expect(page.locator('main')).toContainText('Inclusive of all taxes');

    await addToCart(page);

    await page.goto('/cart/');
    await expect(page.getByTestId('cart-line')).toHaveCount(1);
    await expect(page.getByTestId('cart-line-variant')).toHaveText('200 g');
    await expect(page.getByTestId('cart-line-subtotal')).toHaveText('₹799');
});

test('G1: add to cart, apply a coupon, and see correct INR totals in the cart and at checkout', async ({ page }) => {
    await page.goto(SCENT);
    await page.getByTestId('option-Size').getByRole('button', { name: '200 g' }).click();
    await expect(page.getByTestId('product-price')).toHaveText('₹799');
    await addToCart(page);

    await page.goto('/cart/');
    await expect(page.getByTestId('summary-subtotal')).toHaveText('₹799');
    await expect(page.getByTestId('summary-shipping')).toHaveText('₹79');
    await expect(page.getByTestId('summary-total')).toHaveText('₹878');
    await expect(page.getByTestId('free-shipping-line')).toHaveText('Add ₹200 more for free shipping.');

    // An unknown code is refused with a reason and changes nothing.
    await page.getByLabel('Coupon code').fill('NOPE');
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.getByTestId('coupon-message')).toHaveText('This coupon code is not valid.');
    await expect(page.getByTestId('summary-total')).toHaveText('₹878');

    // 10% off the Rs 799 subtotal = Rs 79.90; shipping still applies.
    await page.getByLabel('Coupon code').fill('welcome10');
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect(page.getByTestId('summary-discount')).toHaveText('-₹79.90');
    await expect(page.getByTestId('summary-shipping')).toHaveText('₹79');
    await expect(page.getByTestId('summary-total')).toHaveText('₹798.10');
    await expect(page.getByTestId('cart-summary')).toContainText('Inclusive of all taxes');
    await expect(page.getByTestId('cart-summary')).not.toContainText('Tax');
    await expect(page.getByTestId('cart-summary')).not.toContainText('Service');

    await fillAddress(page);
    await page.getByRole('button', { name: 'Go to checkout' }).click();

    await expect(page).toHaveURL(/\/checkout\//);
    const summary = page.getByTestId('checkout-summary');
    await expect(summary.getByTestId('summary-subtotal')).toHaveText('₹799');
    await expect(summary.getByTestId('summary-discount')).toHaveText('-₹79.90');
    await expect(summary.getByTestId('summary-shipping')).toHaveText('₹79');
    await expect(summary.getByTestId('summary-total')).toHaveText('₹798.10');
    await expect(summary).toContainText('Discount (WELCOME10)');
    await expect(summary).toContainText('Inclusive of all taxes');
    await expect(page.getByLabel('UPI / Card / Netbanking')).toBeChecked();
    await expect(page.getByTestId('pay-online')).toHaveText('Pay ₹798.10');

    // No dollars, no PayPal, no tax or service-fee rows anywhere on the page.
    const body = page.locator('body');
    await expect(body).not.toContainText('$');
    await expect(body).not.toContainText('USD');
    await expect(body).not.toContainText(/paypal/i);
    await expect(summary).not.toContainText('Tax');
    await expect(summary).not.toContainText('Service');

    // The policies are linked from checkout.
    await expect(page.getByTestId('checkout-policies').getByRole('link')).toHaveCount(5);
});

test('G1: an order of Rs 999 or more ships free', async ({ page }) => {
    await page.goto(SCENT);
    await page.getByTestId('option-Size').getByRole('button', { name: '300 g' }).click();
    await expect(page.getByTestId('product-price')).toHaveText('₹1,199');
    await addToCart(page);

    await page.goto('/cart/');
    await expect(page.getByTestId('summary-subtotal')).toHaveText('₹1,199');
    await expect(page.getByTestId('summary-shipping')).toHaveText('Free');
    await expect(page.getByTestId('summary-total')).toHaveText('₹1,199');
    await expect(page.locator('body')).not.toContainText('$');
});

test('G2: every policy page and the contact page render and are linked from the footer', async ({ page }) => {
    await page.goto('/');
    const footer = page.getByTestId('footer-policies');

    const pages = [
        ['Shipping Policy', 'policy-shipping'],
        ['Returns and Refunds', 'policy-returns'],
        ['Privacy Policy', 'policy-privacy'],
        ['Terms and Conditions', 'policy-terms'],
    ];
    for (const [title, testId] of pages) {
        await footer.getByRole('link', { name: title }).click();
        await expect(page.getByTestId(testId).getByRole('heading', { level: 1 })).toHaveText(title);
        // The copy is placeholder text and says so.
        await expect(page.getByTestId('placeholder-notice')).toBeVisible();
    }

    // The shipping page states the live charge and threshold.
    await page.goto('/policy/shipping');
    await expect(page.getByTestId('policy-shipping')).toContainText('Shipping is ₹79 per order. Orders of ₹999 or more');

    await page.getByRole('contentinfo').getByRole('link', { name: 'Contact us' }).click();
    await expect(page.getByTestId('policy-contact').getByRole('heading', { level: 1 })).toHaveText('Contact us');
    await expect(page.getByTestId('contact-email')).toHaveAttribute('href', /^mailto:/);
    await expect(page.getByTestId('contact-whatsapp')).toHaveAttribute('href', /^https:\/\/wa\.me\/\d+$/);
    await expect(page.getByTestId('footer-whatsapp')).toHaveAttribute('href', /^https:\/\/wa\.me\/\d+$/);
});
