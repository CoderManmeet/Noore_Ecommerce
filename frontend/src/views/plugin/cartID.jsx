// Returns this browser's cart id, creating one on first use.
//
// The cart id is the only thing that identifies a guest cart, so it is generated with the
// browser's cryptographic random number generator (not Math.random) and returned
// immediately on first use (previously the first call returned null).
const CART_ID_KEY = 'randomString';
const CART_ID_LENGTH = 30;
const CHARACTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';

function generateCartId() {
    const bytes = new Uint32Array(CART_ID_LENGTH);
    window.crypto.getRandomValues(bytes);
    let id = '';
    for (let i = 0; i < CART_ID_LENGTH; i++) {
        id += CHARACTERS.charAt(bytes[i] % CHARACTERS.length);
    }
    return id;
}

function CartID() {
    const existing = localStorage.getItem(CART_ID_KEY);
    if (existing) {
        return existing;
    }
    const created = generateCartId();
    localStorage.setItem(CART_ID_KEY, created);
    return created;
}

export default CartID;
