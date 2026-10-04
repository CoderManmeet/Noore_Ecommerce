import { useEffect, useState, useContext, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Swal from 'sweetalert2'

import { addToCart } from '../plugin/addToCart';
import apiInstance from '../../utils/axios';
import GetCurrentAddress from '../plugin/UserCountry';
import UserData from '../plugin/UserData';
import CartID from '../plugin/cartID';
import { CartContext } from '../plugin/Context';
import { Trash2 } from 'lucide-react';
import { formatINR } from '../../utils/money';
import { BackLink, Field, Photo } from '../ui/noore';
import { SIZES } from '../../utils/image';
import usePageTitle from '../../utils/usePageTitle';

// The coupon typed in the cart is remembered for this browser so it survives a refresh and
// is sent with the order. The server re-validates it every time; this is only a convenience.
const COUPON_STORAGE_KEY = 'cartCouponCode';

function Cart() {
    usePageTitle('Cart');
    const [cart, setCart] = useState([])
    // Totals come from the server's single pricing function. Every amount is integer paise.
    const [quote, setQuote] = useState(null)
    const [quantities, setQuantities] = useState({});
    const [couponInput, setCouponInput] = useState(localStorage.getItem(COUPON_STORAGE_KEY) || "")
    const [appliedCoupon, setAppliedCoupon] = useState(localStorage.getItem(COUPON_STORAGE_KEY) || "")
    const [couponMessage, setCouponMessage] = useState("")
    const [placingOrder, setPlacingOrder] = useState(false)

    const [fullName, setFullName] = useState("")
    const [email, setEmail] = useState("")
    const [mobile, setMobile] = useState("")
    const [address, setAddress] = useState("")
    const [city, setCity] = useState("")
    const [state, setState] = useState("")
    const [pincode, setPincode] = useState("")
    const [country, setCountry] = useState("India")
    const [cartCount, setCartCount] = useContext(CartContext);

    const axios = apiInstance
    const userData = UserData()
    const userId = userData?.user_id
    const cart_id = CartID()
    const currentAddress = GetCurrentAddress()
    const navigate = useNavigate();

    const fetchCart = useCallback(async (couponCode) => {
        const listUrl = userId ? `cart-list/${cart_id}/${userId}/` : `cart-list/${cart_id}/`;
        const totalsUrl = userId ? `cart-detail/${cart_id}/${userId}/` : `cart-detail/${cart_id}/`;
        const params = couponCode ? { coupon: couponCode } : {};

        const [listRes, totalsRes] = await Promise.all([axios.get(listUrl), axios.get(totalsUrl, { params })]);
        setCart(listRes.data);
        setQuote(totalsRes.data);
        setCartCount(listRes.data.length);

        const next = {};
        listRes.data.forEach((c) => { next[c.id] = c.qty });
        setQuantities(next);
        return totalsRes.data;
    }, [axios, cart_id, userId, setCartCount]);

    useEffect(() => {
        fetchCart(appliedCoupon).then((totals) => {
            // A remembered coupon that is no longer usable is dropped, with the reason shown.
            if (appliedCoupon && totals.coupon_error) {
                setCouponMessage(totals.coupon_message)
                setAppliedCoupon("")
                localStorage.removeItem(COUPON_STORAGE_KEY)
            }
        }).catch((error) => console.error('Could not load the cart:', error));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // cart item id -> the server's priced line for it
    const pricedLines = {};
    (quote?.lines || []).forEach((line) => { pricedLines[line.cart_item_id] = line });

    const handleQtyChange = (event, itemId) => {
        setQuantities((previous) => ({ ...previous, [itemId]: event.target.value }));
    };

    const updateLine = async (c) => {
        const qty = parseInt(quantities[c.id], 10);
        if (!Number.isInteger(qty) || qty < 1) {
            Swal.fire({ icon: 'warning', title: 'Quantity must be at least 1' })
            return;
        }
        await addToCart(c.product.id, userId, qty, null, null, currentAddress?.country, c.color, c.size, cart_id, null, c.variant?.id);
        await fetchCart(appliedCoupon);
    };

    const removeLine = async (itemId) => {
        const url = userId ? `cart-delete/${cart_id}/${itemId}/${userId}/` : `cart-delete/${cart_id}/${itemId}/`;
        try {
            await axios.delete(url);
            await fetchCart(appliedCoupon);
        } catch (error) {
            console.error('Error deleting item:', error);
        }
    };

    const applyCoupon = async () => {
        const code = couponInput.trim();
        if (!code) return;
        const totals = await fetchCart(code);
        if (totals.coupon_error) {
            setCouponMessage(totals.coupon_message);
            setAppliedCoupon("");
            localStorage.removeItem(COUPON_STORAGE_KEY);
            await fetchCart("");
        } else {
            setCouponMessage("");
            setAppliedCoupon(totals.coupon_code);
            setCouponInput(totals.coupon_code);
            localStorage.setItem(COUPON_STORAGE_KEY, totals.coupon_code);
        }
    };

    const removeCoupon = async () => {
        setAppliedCoupon("");
        setCouponInput("");
        setCouponMessage("");
        localStorage.removeItem(COUPON_STORAGE_KEY);
        await fetchCart("");
    };

    const createCartOrder = async () => {
        if (!fullName || !email || !mobile || !address || !city || !state || !pincode || !country) {
            Swal.fire({
                icon: 'warning',
                title: 'Missing Fields!',
                text: "All fields are required before checkout",
            })
            return;
        }

        setPlacingOrder(true)
        try {
            const formData = new FormData();
            formData.append('full_name', fullName);
            formData.append('email', email);
            formData.append('mobile', mobile);
            formData.append('address', address);
            formData.append('city', city);
            formData.append('state', state);
            formData.append('pincode', pincode);
            formData.append('country', country);
            formData.append('cart_id', cart_id);
            formData.append('user_id', userData ? userData.user_id : 0);
            // Always sent, even when blank, so removing a coupon in the cart removes it from the order.
            formData.append('coupon_code', appliedCoupon);

            const response = await axios.post('create-order/', formData)

            if (response.data.coupon_error) {
                // e.g. a guest who has used this coupon before: only known once we have their details.
                localStorage.removeItem(COUPON_STORAGE_KEY);
                await Swal.fire({
                    icon: 'info',
                    title: 'Coupon not applied',
                    text: response.data.coupon_message,
                })
            }
            navigate(`/checkout/${response.data.order_oid}`);
        } catch (error) {
            const data = error?.response?.data;
            const first = data && typeof data === 'object' ? Object.values(data)[0] : null;
            Swal.fire({
                icon: 'error',
                title: 'Could not start checkout',
                text: (Array.isArray(first) ? first[0] : first) || 'Please try again.',
            })
        } finally {
            setPlacingOrder(false)
        }
    }

    const visibleLines = cart.filter((c) => pricedLines[c.id]);
    const threshold = quote?.free_shipping_threshold_paise || 0;
    const afterDiscount = (quote?.subtotal_paise || 0) - (quote?.discount_paise || 0);
    const progress = threshold > 0 ? Math.min(100, Math.round((afterDiscount * 100) / threshold)) : 100;

    return (
        <main>
            <div className="mx-auto max-w-6xl px-5 py-12 md:px-10 md:py-20">
                <BackLink to="/shop">Continue shopping</BackLink>
                <h1 className="font-serif text-5xl md:text-7xl">Your bag.</h1>

                {quote !== null && visibleLines.length < 1 &&
                    <div className="py-20 text-center">
                        <p className="font-serif text-2xl">Your Cart Is Empty</p>
                        <p className="mt-2 text-sm text-stone">Choose a scent to begin.</p>
                        <Link to='/shop' className="noore-btn mt-7">Browse candles</Link>
                    </div>
                }

                {visibleLines.length > 0 &&
                    <div className="mt-12 grid gap-12 lg:grid-cols-[1.3fr_.7fr]">
                        <section>
                            <div className="flex flex-col gap-6">
                                {visibleLines.map((c) => {
                                    const line = pricedLines[c.id];
                                    return (
                                        <article className="flex gap-4 border-b border-line pb-6" key={c.id} data-testid="cart-line">
                                            <Link to={`/detail/${c?.product?.slug}`} className="block size-28 shrink-0 overflow-hidden bg-oat md:size-36">
                                                {c?.product?.image && <Photo src={c.product.image} alt={c?.product?.title} width={SIZES.thumb} className="size-full object-cover" />}
                                            </Link>
                                            <div className="flex min-w-0 flex-1 flex-col justify-between gap-4">
                                                <div className="flex justify-between gap-3">
                                                    <div>
                                                        <h2 className="font-serif text-2xl"><Link to={`/detail/${c.product.slug}`}>{c?.product?.title}</Link></h2>
                                                        {c.variant?.name && c.variant.name !== "Default" &&
                                                            <p className="mt-2 text-xs" data-testid="cart-line-variant">{c.variant.name}</p>
                                                        }
                                                        <p className="mt-1 text-xs text-stone">{formatINR(line.unit_price_paise)} each</p>
                                                    </div>
                                                    <p className="text-sm" data-testid="cart-line-subtotal">{formatINR(line.line_subtotal_paise)}</p>
                                                </div>
                                                <div className="flex items-center justify-between gap-3">
                                                    <div className="flex items-center gap-2">
                                                        <input type="number" aria-label="Quantity" min={1} value={quantities[c.id] ?? c.qty}
                                                            onChange={(e) => handleQtyChange(e, c.id)}
                                                            className="h-10 w-20 border border-line-strong bg-transparent px-3 text-sm outline-none focus:border-clay" />
                                                        <button onClick={() => updateLine(c)} className="noore-btn-outline" title="Update quantity">Update</button>
                                                    </div>
                                                    <button onClick={() => removeLine(c.id)} className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-stone">
                                                        <Trash2 className="size-3" aria-hidden="true" /> Remove
                                                    </button>
                                                </div>
                                            </div>
                                        </article>
                                    )
                                })}
                            </div>

                            <div className="mt-10 border-b border-line pb-8">
                                <label htmlFor="cartCoupon" className="noore-label">Have a coupon code?</label>
                                <div className="mt-3 flex max-w-md items-center border-b border-line-strong">
                                    <input id="cartCoupon" onChange={(e) => setCouponInput(e.target.value)} value={couponInput} name="couponCode" type="text"
                                        aria-label="Coupon code" placeholder="Enter code" readOnly={Boolean(appliedCoupon)}
                                        className="min-h-12 min-w-0 flex-1 bg-transparent text-sm uppercase outline-none" />
                                    {appliedCoupon
                                        ? <button onClick={removeCoupon} className="text-[10px] uppercase tracking-[0.15em] text-clay">Remove</button>
                                        : <button onClick={applyCoupon} className="text-[10px] uppercase tracking-[0.15em] text-clay">Apply</button>
                                    }
                                </div>
                                {couponMessage && <p className="mt-3 text-xs text-clay" data-testid="coupon-message">{couponMessage}</p>}
                            </div>

                            {quote &&
                                <>
                                    <p className="mt-6 text-xs text-stone" data-testid="free-shipping-line">
                                        {quote.amount_to_free_shipping_paise > 0
                                            ? <>Add <b>{formatINR(quote.amount_to_free_shipping_paise)}</b> more for free shipping.</>
                                            : <>Shipping {formatINR(quote.shipping_flat_paise)}. Free on orders of {formatINR(quote.free_shipping_threshold_paise)} or more.</>
                                        }
                                    </p>
                                    <div className="mt-3 h-1 bg-linen" aria-hidden="true"><div className="h-full bg-clay" style={{ width: `${progress}%` }} /></div>
                                </>
                            }

                            <h2 className="mt-14 font-serif text-3xl">Delivery details</h2>
                            <div className="mt-8 grid gap-6 md:grid-cols-2">
                                <div className="md:col-span-2"><Field id="cartFullName" label="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" /></div>
                                <Field id="cartEmail" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
                                <Field id="cartMobile" label="Mobile" type="tel" value={mobile} onChange={(e) => setMobile(e.target.value)} autoComplete="tel" />
                                <div className="md:col-span-2"><Field id="cartAddress" label="Address" value={address} onChange={(e) => setAddress(e.target.value)} autoComplete="street-address" /></div>
                                <Field id="cartCity" label="City" value={city} onChange={(e) => setCity(e.target.value)} autoComplete="address-level2" />
                                <Field id="cartState" label="State" value={state} onChange={(e) => setState(e.target.value)} autoComplete="address-level1" />
                                <Field id="cartPincode" label="PIN code" value={pincode} onChange={(e) => setPincode(e.target.value)} inputMode="numeric" maxLength={10} autoComplete="postal-code" />
                                <Field id="cartCountry" label="Country" value={country} onChange={(e) => setCountry(e.target.value)} autoComplete="country-name" />
                            </div>
                        </section>

                        {/* Summary. Every price, fee and discount is shown here before the customer commits. */}
                        <section className="h-fit bg-sand p-6 md:p-8 lg:sticky lg:top-6" data-testid="cart-summary">
                            <p className="mb-6 text-[10px] uppercase tracking-[0.2em]">Order summary</p>
                            <div className="flex flex-col gap-3 text-sm">
                                <div className="flex justify-between"><span>Subtotal</span><span data-testid="summary-subtotal">{formatINR(quote?.subtotal_paise ?? 0)}</span></div>
                                {quote?.discount_paise > 0 &&
                                    <div className="flex justify-between text-clay"><span>Discount ({quote.coupon_code})</span><span data-testid="summary-discount">-{formatINR(quote.discount_paise)}</span></div>
                                }
                                <div className="flex justify-between"><span>Shipping</span><span data-testid="summary-shipping">{quote?.free_shipping ? 'Free' : formatINR(quote?.shipping_paise ?? 0)}</span></div>
                                <div className="mt-3 flex justify-between border-t border-line pt-4 font-serif text-2xl"><span>Total</span><span data-testid="summary-total">{formatINR(quote?.total_paise ?? 0)}</span></div>
                                <p className="text-xs text-stone">Inclusive of all taxes</p>
                            </div>
                            <button onClick={createCartOrder} disabled={placingOrder} className="noore-btn mt-8 w-full">
                                {placingOrder ? 'Please wait...' : 'Go to checkout'}
                            </button>
                            <p className="mt-4 text-center text-xs text-stone">You choose how to pay on the next step.</p>
                        </section>
                    </div>
                }
            </div>
        </main>
    )
}

export default Cart