import { useContext, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Swal from 'sweetalert2';

import apiInstance from '../../utils/axios';
import CartID from '../plugin/cartID';
import { CartContext } from '../plugin/Context';

// "Buy again": puts a past order's items back in the bag at today's prices and today's
// availability, then opens the bag. It never places an order by itself; the customer still
// reviews the bag and checks out.
function BuyAgainButton({ orderOid, className = "noore-btn-outline" }) {
    const [busy, setBusy] = useState(false)
    const [, setCartCount] = useContext(CartContext)
    const navigate = useNavigate()

    const buyAgain = async () => {
        setBusy(true)
        try {
            const response = await apiInstance.post(`reorder/${orderOid}/`, { cart_id: CartID() })
            const { added, reduced, unavailable, cart_lines } = response.data
            setCartCount(cart_lines)

            const notes = []
            reduced.forEach((line) => notes.push(`${line.title}: only ${line.qty} of ${line.wanted} available`))
            unavailable.forEach((line) => notes.push(`${line.title}: ${line.reason === 'sold_out' ? 'sold out' : 'no longer sold'}`))

            if (added.length + reduced.length === 0) {
                await Swal.fire({ icon: 'info', title: 'Nothing could be added', text: notes.join('. ') })
                return
            }
            if (notes.length > 0) {
                await Swal.fire({
                    icon: 'info',
                    title: 'Added to your bag, with changes',
                    text: `${notes.join('. ')}. Prices are today's prices.`,
                })
            }
            navigate('/cart/')
        } catch (error) {
            Swal.fire({ icon: 'error', title: 'Could not add these items', text: error?.response?.data?.detail || 'Please try again.' })
        } finally {
            setBusy(false)
        }
    }

    return (
        <button type="button" className={className} onClick={buyAgain} disabled={busy} data-testid="buy-again">
            {busy ? 'Adding...' : 'Buy again'}
        </button>
    )
}

export default BuyAgainButton
