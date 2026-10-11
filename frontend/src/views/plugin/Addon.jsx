import { useCachedApi } from '../../utils/apiCache';

// Store-wide settings used all over the storefront: shipping, the free-shipping threshold, tax.
//
// This is the same answer for every visitor and never personal, so it goes through the shared
// cache: the request is already in flight before React renders (started in main.jsx), the last
// answer is painted immediately on a repeat visit, and a page that mounts this twice makes one
// request, not two. See src/utils/apiCache.js.
function Addon() {
    const { data } = useCachedApi('addon/');
    // Callers check individual fields (`addon?.shipping_flat_paise != null`), so an empty object
    // while the answer is on its way behaves exactly as the old empty array did.
    return data || {};
}

export default Addon;