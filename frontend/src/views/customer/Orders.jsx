import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import moment from 'moment';

import apiInstance from '../../utils/axios';
import UserData from '../plugin/UserData';
import { formatINR } from '../../utils/money';
import usePageTitle from '../../utils/usePageTitle';
import { Loading, PageIntro } from '../ui/noore';
import BuyAgainButton from './BuyAgainButton';

// What the customer is told about an order, in plain words.
export const orderStatusLabel = (order) => {
    if (order.order_status === 'Cancelled' || order.payment_status === 'cancelled') return 'Cancelled';
    if (order.payment_status === 'refunded') return 'Refunded';
    const lines = order.orderitem || [];
    const all = (status) => lines.length > 0 && lines.every((line) => line.delivery_status === status);
    const some = (statuses) => lines.some((line) => statuses.includes(line.delivery_status));
    if (all('Delivered')) return 'Delivered';
    if (some(['Shipped', 'Arrived'])) return 'On its way';
    if (some(['Shipping Processing'])) return 'Being packed';
    if (order.payment_method === 'COD' && order.payment_status === 'pending') return 'Placed · pay on delivery';
    return 'Placed';
};

export function AccountNav() {
    const link = "text-[10px] uppercase tracking-[0.18em] text-stone hover:text-ink";
    return (
        <nav aria-label="Account" className="mt-8 flex flex-wrap gap-x-7 gap-y-3">
            <Link to="/customer/orders/" className={link}>Orders</Link>
            <Link to="/customer/wishlist/" className={link}>Wishlist</Link>
            <Link to="/customer/settings/" className={link}>Settings</Link>
            <Link to="/logout" className={link}>Sign out</Link>
        </nav>
    );
}

function Orders() {
    const [orders, setOrders] = useState(null)
    const userData = UserData()
    usePageTitle('My orders');

    useEffect(() => {
        apiInstance.get(`customer/orders/${userData?.user_id}/`).then((res) => {
            setOrders(res.data)
        }).catch(() => setOrders([]))
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
        <main data-testid="orders-page">
            <PageIntro eyebrow="Your account" title="Your orders.">
                <AccountNav />
            </PageIntro>
            <div className="mx-auto max-w-5xl px-5 py-12 md:px-10 md:py-16">
                {orders === null && <Loading />}
                {orders !== null && orders.length === 0 &&
                    <div className="py-16 text-center">
                        <p className="font-serif text-2xl">No orders yet.</p>
                        <Link to="/shop" className="noore-btn mt-7">Browse candles</Link>
                    </div>
                }
                <div className="flex flex-col">
                    {(orders || []).map((o) => (
                        <article key={o.oid} className="flex flex-col gap-4 border-b border-line py-6 md:flex-row md:items-center md:justify-between" data-testid="customer-order">
                            <div>
                                <p className="font-serif text-2xl">#{o.oid}</p>
                                <p className="mt-1 text-xs text-stone">{moment(o.date).format('DD MMM YYYY')} · {(o.orderitem || []).length} {(o.orderitem || []).length === 1 ? 'item' : 'items'}</p>
                                <p className="mt-2 text-[10px] uppercase tracking-[0.15em] text-clay">{orderStatusLabel(o)}</p>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className="text-sm">{formatINR(o.total_paise)}</span>
                                <Link className="noore-btn-outline" to={`/customer/order/detail/${o.oid}/`}>View</Link>
                                <BuyAgainButton orderOid={o.oid} />
                            </div>
                        </article>
                    ))}
                </div>
            </div>
        </main>
    )
}

export default Orders
