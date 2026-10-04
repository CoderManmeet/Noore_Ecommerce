import Swal from 'sweetalert2'
import apiInstance from '../../utils/axios';

// Delete a product, or hide it when it cannot be deleted.
//
// A product that has stock history or has been ordered cannot be deleted: doing so would erase
// records the store has to keep (the stock ledger and the audit trail are permanent). The
// server says so, and this offers the reversible alternative instead: hide it from the shop.
//
// Returns true when something changed (deleted or hidden), false when the owner backed out.
export const deleteProduct = async (vendorId, productPid, productTitle = 'this product') => {
    const confirmed = await Swal.fire({
        icon: 'warning',
        title: 'Delete product?',
        text: `Are you sure you want to permanently delete ${productTitle}?`,
        confirmButtonText: 'Yes, delete it',
        showCancelButton: true,
    });
    if (!confirmed.isConfirmed) return false;

    try {
        await apiInstance.delete(`vendor-product-delete/${vendorId}/${productPid}/`);
        await Swal.fire({ icon: 'success', title: 'Product deleted' });
        return true;
    } catch (error) {
        const data = error?.response?.data;

        if (error?.response?.status === 409 && data?.can_hide) {
            const choice = await Swal.fire({
                icon: 'info',
                title: 'This product cannot be deleted',
                text: data.message,
                showCancelButton: true,
                confirmButtonText: 'Hide it from the shop',
                cancelButtonText: 'Leave it as it is',
            });
            if (!choice.isConfirmed) return false;
            return hideProduct(vendorId, productPid);
        }

        await Swal.fire({
            icon: 'error',
            title: 'Could not delete this product',
            text: data?.message || data?.detail || 'Please try again.',
        });
        return false;
    }
};

// Change whether a product appears in the shop. `status` is "published", "draft" or "disabled".
export const setProductStatus = async (vendorId, productPid, status) => {
    try {
        await apiInstance.post(`vendor-product-visibility/${vendorId}/${productPid}/`, { status });
        await Swal.fire({
            icon: 'success',
            title: status === 'published' ? 'Product is back in the shop' : 'Product hidden from the shop',
        });
        return true;
    } catch (error) {
        await Swal.fire({
            icon: 'error',
            title: 'Could not change this product',
            text: error?.response?.data?.message || 'Please try again.',
        });
        return false;
    }
};

export const hideProduct = (vendorId, productPid) => setProductStatus(vendorId, productPid, 'disabled');