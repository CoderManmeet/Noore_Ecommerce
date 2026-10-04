import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import moment from 'moment';

import apiInstance from '../../utils/axios';
import UserData from '../plugin/UserData';
import { formatINR } from '../../utils/money';
import usePageTitle from '../../utils/usePageTitle';
import { Loading, PageIntro, Photo } from '../ui/noore';
import NotFound from '../base/NotFound';
import BuyAgainButton from './BuyAgainButton';
import { orderStatusLabel } from './Orders';

// One past order: where it has got to, what was in it, what was paid and how.
const STEPS = ['Placed', 'Being packed', 'On its way', 'Delivered'];
const STEP_OF = { 'On Hold': 0, 'Shipping Processing': 1, 'Shipped': 2, 'Arrived': 2, 'Delivered': 3 };

function OrderDetail() {
    const [order, setOrder] = useState(null)
    const [missing, setMissing] = useState(false)
    const userData = UserData()
    const param = useParams()
    usePageTitle(order ? `Order ${order.oid}` : 'Order');

    useEffect(() => {
        apiInstance.get(`customer/order/detail/${userData?.user_id}/${param?.order_oid}/`).then((res) => {
            setOrder(res.data);
        }).catch(() => setMissing(true))
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [param?.order_oid])

    if (missing) return <NotFound />;
    if (order === null) return <main><Loading /></main>;

    const items = order.orderitem || [];
    const cancelled = order.order_status === 'Cancelled' || order.payment_status === 'cancelled';
    // The order is as far along as its least-advanced line.
    const reached = items.length > 0 ? Math.min(...items.map((item) => STEP_OF[item.delivery_status] ?? 0)) : 0;
    const tracking = items.filter((item) => item.tracking_id).map((item) => ({ id: item.tracking_id, courier: item.delivery_couriers?.name }))
        .filter((entry, index, all) => all.findIndex((other) => other.id === entry.id) === index);
    const isCod = order.payment_method === 'COD';
    const paymentText = order.payment_status === 'paid' ? (isCod ? 'Paid in cash on delivery' : 'Paid online')
        : order.payment_status === 'pending' && isCod ? 'Cash on Delivery · to pay on arrival'
            : order.payment_status === 'refunded' ? 'Refunded' : order.payment_status;

    return (
        <main data-testid="order-detail-page">
            <PageIntro eyebrow="Order details" title={`Order ${order.oid}.`}>
                <p className="mt-5 text-xs text-stone">{moment(order.date).format('DD MMM YYYY')} · {orderStatusLabel(order)}</p>
            </PageIntro>
            <div className="mx-auto max-w-5xl px-5 py-12 md:px-10 md:py-16">
                <div className="grid gap-12 lg:grid-cols-[1.2fr_.8fr]">
                    <section>
                        {!cancelled &&
                            <>
                                <p className="mb-6 text-[10px] uppercase tracking-[0.2em]">Progress</p>
                                <ol className="border-l border-clay pl-6">
                                    {STEPS.map((step, index) => (
                                        <li key={step} className={`relative pb-8 last:pb-0 ${index <= reached ? '' : 'opacity-40'}`}>
                                            <span className={`absolute -left-[29px] top-1.5 size-2 rounded-full ${index <= reached ? 'bg-clay' : 'bg-line-strong'}`} aria-hidden="true" />
                                            <p className="font-serif text-xl">{step}</p>
                                        </li>
                                    ))}
                                </ol>
                                {tracking.length > 0 &&
                                    <p className="mt-6 text-sm text-stone">
                                        {tracking.map((entry) => <span key={entry.id} className="block">Tracking number: <b className="text-ink">{entry.id}</b>{entry.courier ? ` (${entry.courier})` : ''}</span>)}
                                    </p>
                                }
                            </>
                        }
                        {cancelled && <p className="border border-line bg-sand p-5 text-sm">This order was cancelled.</p>}

                        <p className="mb-6 mt-12 text-[10px] uppercase tracking-[0.2em]">Items</p>
                        <div className="flex flex-col gap-5">
                            {items.map((item) => (
                                <div key={item.id} className="flex items-center gap-4">
                                    <Link to={`/detail/${item.product?.slug}`} className="block size-16 shrink-0 overflow-hidden bg-oat">
                                        {item.product?.image && <Photo src={item.product.image} alt="" className="size-full object-cover" />}
                                    </Link>
                                    <div className="flex-1">
                                        <p className="font-serif text-xl"><Link to={`/detail/${item.product?.slug}`}>{item.product?.title}</Link></p>
                                        <p className="text-xs text-stone">{item.variant?.name && item.variant.name !== 'Default' ? `${item.variant.name} · ` : ''}Qty {item.qty} · {formatINR(item.price_paise)} each</p>
                                    </div>
                                    <p className="text-sm">{formatINR(item.sub_total_paise)}</p>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="h-fit bg-sand p-6 md:p-8">
                        <p className="text-[10px] uppercase tracking-[0.2em]">Delivery &amp; payment</p>
                        <p className="mt-6 font-serif text-2xl">{order.full_name}</p>
                        <p className="mt-2 text-sm leading-6 text-stone">{order.address}<br />{order.city}, {order.state} {order.pincode}</p>

                        <div className="mt-6 flex flex-col gap-2 border-t border-line pt-5 text-sm">
                            <div className="flex justify-between"><span>Subtotal</span><span>{formatINR(order.sub_total_paise)}</span></div>
                            {order.saved_paise > 0 &&
                                <div className="flex justify-between text-clay"><span>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</span><span>-{formatINR(order.saved_paise)}</span></div>
                            }
                            <div className="flex justify-between"><span>Shipping</span><span>{order.shipping_amount_paise > 0 ? formatINR(order.shipping_amount_paise) : 'Free'}</span></div>
                            {order.service_fee_paise > 0 &&
                                <div className="flex justify-between"><span>Service fee</span><span>{formatINR(order.service_fee_paise)}</span></div>
                            }
                            <div className="mt-2 flex justify-between border-t border-line pt-3 font-serif text-2xl"><span>Total</span><span>{formatINR(order.total_paise)}</span></div>
                            <p className="text-xs text-stone">Inclusive of all taxes · {paymentText}</p>
                        </div>

                        <div className="mt-8 flex flex-wrap items-center gap-5">
                            <BuyAgainButton orderOid={order.oid} className="noore-btn" />
                            <Link to="/customer/orders/" className="noore-link text-[10px] uppercase tracking-[0.15em]">All orders</Link>
                        </div>
                    </section>
                </div>
            </div>
        </main>
    )
}

export default OrderDetail
