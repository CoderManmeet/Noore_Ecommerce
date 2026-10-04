// Loads Razorpay's Checkout script. Razorpay's documentation says to always load it from
// their CDN and never self-host it.
const CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js';

let loading = null;

export const loadRazorpay = () => {
    if (window.Razorpay) return Promise.resolve(window.Razorpay);
    if (!loading) {
        loading = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = CHECKOUT_SRC;
            script.async = true;
            script.onload = () => (window.Razorpay ? resolve(window.Razorpay) : reject(new Error('Razorpay did not load')));
            script.onerror = () => {
                loading = null;
                reject(new Error('Razorpay could not be loaded'));
            };
            document.body.appendChild(script);
        });
    }
    return loading;
};
