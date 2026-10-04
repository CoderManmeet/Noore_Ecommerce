import apiInstance from '../../utils/axios';
import Swal from 'sweetalert2';

const Toast = Swal.mixin({
    toast: true,
    position: 'top',
    showConfirmButton: false,
    timer: 2500,
    timerProgressBar: true,
});

// Pull the first human-readable message out of a DRF validation error body.
const firstErrorMessage = (error) => {
    const data = error?.response?.data;
    if (!data) return null;
    if (typeof data === 'string') return data;
    if (typeof data.message === 'string') return data.message;
    if (typeof data.detail === 'string') return data.detail;
    const first = Object.values(data)[0];
    if (Array.isArray(first)) return String(first[0]);
    if (typeof first === 'string') return first;
    return null;
};

const isLegacyPlaceholder = (value) =>
    value === undefined || value === null || value === '' || value === 'No Size' || value === 'No Color';

// Add a product to the cart, or change the quantity of a line that is already there.
//
// The server decides the price (the variant's price in the database) and reserves stock, so
// this call can legitimately fail (for example "Only 2 left in stock") and the shopper must
// see why. `price` and `shipping_amount` are accepted for backwards compatibility with older
// callers and are never sent.
//
// `variantId` is the exact sellable unit (for example the 200 g candle). When it is omitted
// the server falls back to the product's default variant.
export const addToCart = async (product_id, user_id, qty, price, shipping_amount, current_address, color, size, cart_id, setIsAddingToCart, variantId) => {
    const axios = apiInstance;

    try {
        const formData = new FormData();
        formData.append('product', product_id);
        formData.append('user', user_id);
        formData.append('qty', qty);
        formData.append('country', current_address || '');
        formData.append('size', isLegacyPlaceholder(size) ? '' : size);
        formData.append('color', isLegacyPlaceholder(color) ? '' : color);
        formData.append('cart_id', cart_id);
        if (variantId !== undefined && variantId !== null && variantId !== '') {
            formData.append('variant', variantId);
        }

        await axios.post('cart-view/', formData);

        Toast.fire({
            icon: 'success',
            title: 'Added To Cart'
        });
        return true;
    } catch (error) {
        Toast.fire({
            icon: 'error',
            title: firstErrorMessage(error) || 'Could not add this item to your cart.'
        });
        return false;
    }
};
