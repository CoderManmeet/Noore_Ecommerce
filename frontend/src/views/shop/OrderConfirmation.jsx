import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import apiInstance from '../../utils/axios';
import UserData from '../plugin/UserData';
import { formatINR } from '../../utils/money';
import { Loading, Photo } from '../ui/noore';
import { SIZES } from '../../utils/image';
import usePageTitle from '../../utils/usePageTitle';

// Shown after checkout.
//
//   * Online payment: the order is PAID only when Razorpay tells our server so. Until then
//     this page says "Confirming your payment" and re-reads the order every few seconds.
//   * Cash on delivery: the order is placed; the amount is collected on delivery.
//
// A guest can ask for a link to create an account. The link is emailed to the address on the
// order, so only someone who can read that mailbox can attach the order to an account.

const POLL_EVERY_MS = 3000;
const MAX_POLLS = 40; // two minutes

function OrderConfirmation() {
    usePageTitle('Your order');
    const [order, setOrder] = useState(null)
    const [gaveUp, setGaveUp] = useState(false)
    const [inviteMessage, setInviteMessage] = useState("")
    const [inviteBusy, setInviteBusy] = useState(false)
    const polls = useRef(0)

    const axios = apiInstance
    const { order_oid } = useParams()
    const userData = UserData()

    useEffect(() => {
        // The cart this order came from is finished with.
        localStorage.removeItem('cartCouponCode');

        let timer = null;
        let cancelled = false;
        const read = () => {
            axios.get(`checkout/${order_oid}/`).then((res) => {
                if (cancelled) return;
                setOrder(res.data);
                const waiting = res.data.payment_provider === 'razorpay' && ['initiated', 'processing'].includes(res.data.payment_status);
                if (waiting) {
                    polls.current += 1;
                    if (polls.current >= MAX_POLLS) {
                        setGaveUp(true);
                    } else {
                        timer = setTimeout(read, POLL_EVERY_MS);
                    }
                }
            }).catch((error) => console.error('Could not load the order:', error));
        };
        read();
        return () => { cancelled = true; if (timer) clearTimeout(timer); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [order_oid]);

    const askForAccountLink = async () => {
        setInviteBusy(true)
        try {
            const response = await axios.post('account/invite/', { order_oid })
            setInviteMessage(response.data.message)
        } catch (error) {
            setInviteMessage(error?.response?.status === 429
                ? 'Please wait a minute before asking again.'
                : 'We could not send the link just now. Please try again later.')
        } finally {
            setInviteBusy(false)
        }
    }

    if (order === null) {
        return (
            <main><Loading>Loading your order...</Loading></main>
        )
    }

    const isCod = order.payment_method === 'COD';
    const status = order.payment_status;
    let state = 'other';
    if (order.order_status === 'Cancelled' || ['cancelled', 'expired', 'failed'].includes(status)) state = 'cancelled';
    else if (status === 'paid') state = 'paid';
    else if (isCod && status === 'pending') state = 'cod';
    else if (order.payment_provider === 'razorpay' && ['initiated', 'processing'].includes(status)) state = gaveUp ? 'slow' : 'confirming';
    else if (['initiated', 'processing'].includes(status)) state = 'unpaid';

    const isGuest = !order.buyer;
    const banner = "border border-line bg-sand p-6 md:p-8";

    return (
        <main data-testid="order-confirmation">
            <div className="mx-auto max-w-3xl px-5 py-14 md:px-10 md:py-20">
                <div className={banner} data-testid="order-state">
                    {state === 'paid' && <>
                        <p className="noore-eyebrow mb-3">Payment received</p>
                        <h1 className="font-serif text-4xl">Payment received. Thank you!</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">Your order <b>#{order.oid}</b> is confirmed. We have emailed the details to {order.email}.</p>
                    </>}
                    {state === 'cod' && <>
                        <p className="noore-eyebrow mb-3">Cash on delivery</p>
                        <h1 className="font-serif text-4xl">Order placed. Thank you!</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">Your order <b>#{order.oid}</b> is Cash on Delivery. Please keep <b>{formatINR(order.total_paise)}</b> ready to pay when it arrives. We may call or message you to confirm it before we send it.</p>
                    </>}
                    {state === 'confirming' && <>
                        <p className="noore-eyebrow mb-3">One moment</p>
                        <h1 className="font-serif text-4xl">Confirming your payment</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">This usually takes a few seconds. Please keep this page open.</p>
                    </>}
                    {state === 'slow' && <>
                        <p className="noore-eyebrow mb-3">Still working</p>
                        <h1 className="font-serif text-4xl">We are still confirming your payment</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">You do not need to pay again. As soon as your bank confirms, we will email {order.email}. If money has left your account and you do not hear from us, <Link to="/contact" className="noore-link">contact us</Link> with order <b>#{order.oid}</b>.</p>
                    </>}
                    {state === 'unpaid' && <>
                        <h1 className="font-serif text-4xl">This order has not been paid for yet</h1>
                        <p className="mt-4 text-sm leading-7 text-stone"><Link to={`/checkout/${order.oid}`} className="noore-link">Go back to checkout</Link> to choose how to pay.</p>
                    </>}
                    {state === 'cancelled' && <>
                        <h1 className="font-serif text-4xl">This order is no longer active</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">If you still want these items, please add them to your bag again.</p>
                    </>}
                    {state === 'other' && <>
                        <h1 className="font-serif text-4xl">Order #{order.oid}</h1>
                        <p className="mt-4 text-sm leading-7 text-stone">Status: {status}</p>
                    </>}
                </div>

                <p className="mb-5 mt-12 text-[10px] uppercase tracking-[0.2em]">Order #{order.oid}</p>
                <div className="flex flex-col gap-5">
                    {(order.orderitem || []).map((item) => (
                        <div className="flex items-center gap-4" key={item.id}>
                            <div className="size-16 shrink-0 overflow-hidden bg-oat">
                                {item.product?.image && <Photo src={item.product.image} alt="" width={SIZES.thumb} className="size-full object-cover" />}
                            </div>
                            <div className="flex-1">
                                <p className="font-serif text-xl">{item.product?.title}</p>
                                <p className="text-xs text-stone">{item.variant?.name && item.variant.name !== "Default" ? `${item.variant.name} · ` : ''}Qty {item.qty}</p>
                            </div>
                            <p className="text-sm">{formatINR(item.sub_total_paise)}</p>
                        </div>
                    ))}
                </div>
                <div className="ml-auto mt-8 flex max-w-xs flex-col gap-2 text-sm">
                    <div className="flex justify-between"><span>Subtotal</span><span>{formatINR(order.sub_total_paise)}</span></div>
                    {order.saved_paise > 0 &&
                        <div className="flex justify-between text-clay"><span>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</span><span>-{formatINR(order.saved_paise)}</span></div>
                    }
                    <div className="flex justify-between"><span>Shipping</span><span>{order.shipping_amount_paise > 0 ? formatINR(order.shipping_amount_paise) : 'Free'}</span></div>
                    <div className="mt-2 flex justify-between border-t border-line pt-3 font-serif text-2xl"><span>Total</span><span data-testid="confirmation-total">{formatINR(order.total_paise)}</span></div>
                    <p className="text-right text-xs text-stone">Inclusive of all taxes{isCod ? '. Cash on Delivery' : ''}</p>
                </div>

                <p className="mt-10 text-sm leading-7 text-stone">
                    <span className="noore-label text-ink">Delivering to</span><br />
                    {order.full_name}, {order.address}, {order.city}, {order.state} {order.pincode}
                </p>

                {(state === 'paid' || state === 'cod') && isGuest &&
                    <div className="mt-10 border border-line p-6" data-testid="account-invite">
                        <h2 className="font-serif text-2xl">Create an account to track this order</h2>
                        <p className="mt-3 text-sm leading-7 text-stone">We will email a link to <b>{order.email}</b>. Open it to choose a password; this order will then appear in your account and you can reorder in one tap.</p>
                        {inviteMessage
                            ? <p className="mt-4 text-sm text-success" data-testid="account-invite-message">{inviteMessage}</p>
                            : <button className="noore-btn-outline mt-5" onClick={askForAccountLink} disabled={inviteBusy}>{inviteBusy ? 'Sending...' : 'Email me the link'}</button>
                        }
                    </div>
                }
                <div className="mt-10 flex flex-wrap gap-6 text-[10px] uppercase tracking-[0.15em]">
                    {!isGuest && userData && <Link to="/customer/orders/" className="noore-link">See all my orders</Link>}
                    <Link to="/shop" className="noore-link">Continue shopping</Link>
                </div>
            </div>
        </main>
    )
}

export default OrderConfirmation