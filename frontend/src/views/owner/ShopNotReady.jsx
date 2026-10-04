import { STORE_NAME } from '../../utils/constants';

// Shown to a staff account that is not yet attached to the brand's shop.
//
// This is a single-brand store: there is one shop, and the owner's account owns it. A newly
// created superuser does not own it yet, so the dashboard has nothing to show. One command
// attaches it. (The old marketplace code used to send the person to a "register your shop"
// form instead; that form is no longer part of this store.)
function ShopNotReady() {
    const command = 'python manage.py claim_shop --email ';
    return (
        <main className="mx-auto max-w-2xl px-5 py-16" data-testid="shop-not-ready">
            <p className="noore-eyebrow mb-4">One step left</p>
            <h1 className="font-serif text-4xl">Your account is not linked to the shop yet.</h1>
            <p className="mt-6 text-sm leading-7 text-stone">
                {STORE_NAME} has one shop, and your staff account needs to own it before the dashboard
                can show products, orders and coupons. Run this once, from the <code>backend</code> folder
                with the virtual environment active, using your own sign-in email:
            </p>
            <pre className="mt-5 overflow-x-auto border border-line bg-sand p-4 text-xs">{command}you@example.com</pre>
            <p className="mt-5 text-sm leading-7 text-stone">
                Then sign out and sign in again, so your browser picks up the change.
            </p>
            <p className="mt-3 text-sm leading-7 text-stone">
                To see which shops exist first: <code>python manage.py claim_shop --list</code>
            </p>
        </main>
    );
}

export default ShopNotReady;
