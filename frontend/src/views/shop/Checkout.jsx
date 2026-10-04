import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Swal from 'sweetalert2'

import apiInstance from '../../utils/axios';
import { formatINR } from '../../utils/money';
import { loadRazorpay } from '../../utils/razorpay';
import { POLICY_LINKS } from '../policy/policies';
import { Loading, PageIntro, Photo } from '../ui/noore';
import { SIZES } from '../../utils/image';
import usePageTitle from '../../utils/usePageTitle';

// Checkout: review the order, choose how to pay, and pay.
//
// Every amount shown is the order's stored total in integer paise, computed on the server by
// the single pricing function. Nothing is calculated in the browser.
//
// Two ways to pay:
//   * "UPI / Card / Netbanking" opens Razorpay Checkout. When the customer finishes there, the
//     server only notes that they came back; the order becomes PAID when Razorpay's own
//     server-to-server notification confirms it. The confirmation page waits for that.
//   * "Cash on delivery" places the order with nothing charged.
//
// Stripe and PayPal are not offered (their code remains in the project, switched off).

const METHOD_ONLINE = 'razorpay';
const METHOD_COD = 'cod';

function Checkout() {
  usePageTitle('Checkout');
  const [order, setOrder] = useState(null)
  const [methods, setMethods] = useState(null)
  const [method, setMethod] = useState(METHOD_ONLINE)
  const [couponCode, setCouponCode] = useState("")
  const [couponBusy, setCouponBusy] = useState(false)
  const [paying, setPaying] = useState(false)

  const axios = apiInstance
  const param = useParams()
  const navigate = useNavigate()

  const loadOrder = useCallback(() => {
    return axios.get(`checkout/${param?.order_oid}/`).then((res) => {
      setOrder(res.data);
      return res.data;
    })
  }, [axios, param?.order_oid])

  useEffect(() => {
    loadOrder().then((data) => {
      // An order that has already been placed has nothing left to do here.
      if (data.payment_status === 'paid' || data.payment_status === 'pending') {
        navigate(`/order/${data.oid}/`, { replace: true })
      }
    })
    axios.get('payments/methods/').then((res) => {
      setMethods(res.data)
      if (!res.data.razorpay && res.data.cod) setMethod(METHOD_COD)
      // Fetch Razorpay's script early so the payment window opens straight from the click.
      if (res.data.razorpay) loadRazorpay().catch(() => { })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submitCoupon = async (code) => {
    setCouponBusy(true)
    const formdata = new FormData()
    formdata.append("order_oid", order.oid)
    formdata.append("coupon_code", code)

    try {
      const response = await axios.post('coupon/', formdata)
      await loadOrder()
      Swal.fire({
        icon: response.data.message === "Coupon Already Activated" ? 'info' : 'success',
        title: response.data.message,
      })
      setCouponCode("")
    } catch (error) {
      // The server says exactly why a coupon was refused (expired, minimum not met, used up...).
      Swal.fire({
        icon: 'error',
        title: 'Coupon not applied',
        text: error?.response?.data?.message || 'This coupon could not be applied.',
      })
    } finally {
      setCouponBusy(false)
    }
  }

  const applyCoupon = () => {
    const code = couponCode.trim()
    if (code) submitCoupon(code)
  }

  const showError = (title, error) => {
    Swal.fire({ icon: 'error', title, text: error?.response?.data?.message || error?.message || 'Please try again.' })
  }

  const payOnline = async () => {
    setPaying(true)
    try {
      const [Razorpay, started] = await Promise.all([
        loadRazorpay(),
        axios.post(`payments/razorpay/start/${order.oid}/`),
      ])
      const checkout = new Razorpay({
        ...started.data.options,
        // Razorpay calls this when the customer has completed payment in its window.
        handler: async (response) => {
          try {
            await axios.post('payments/razorpay/return/', {
              order_oid: order.oid,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_signature: response.razorpay_signature,
            })
          } catch (error) {
            // The payment may still be genuine; the confirmation page waits for Razorpay's own confirmation.
            console.error('Could not record the return from Razorpay:', error)
          }
          navigate(`/order/${order.oid}/`)
        },
      })
      checkout.on('payment.failed', (response) => {
        Swal.fire({
          icon: 'error',
          title: 'Payment failed',
          text: response?.error?.description || 'The payment did not go through. You can try again.',
        })
      })
      checkout.open()
    } catch (error) {
      showError('Could not start the payment', error)
    } finally {
      setPaying(false)
    }
  }

  const placeCod = async () => {
    setPaying(true)
    try {
      await axios.post(`payments/cod/${order.oid}/`)
      navigate(`/order/${order.oid}/`)
    } catch (error) {
      showError('Could not place the order', error)
    } finally {
      setPaying(false)
    }
  }

  if (order === null) {
    return <main><Loading>Loading your order...</Loading></main>
  }

  const hasDiscount = order.saved_paise > 0
  const onlineOffered = Boolean(methods?.razorpay)
  const codOffered = Boolean(methods?.cod)
  const radio = (selected) => `flex cursor-pointer items-center gap-3 border px-4 py-4 text-sm ${selected ? 'border-ink' : 'border-line-strong'}`

  return (
    <main>
      <PageIntro eyebrow="Checkout" title="Review and pay." />
      <div className="mx-auto max-w-6xl px-5 py-12 md:px-10 md:py-16">
        <div className="grid gap-12 lg:grid-cols-[1.2fr_.8fr]">
          <section>
            <p className="mb-5 text-[10px] uppercase tracking-[0.2em]">Delivering to</p>
            <div className="border border-line p-6 text-sm leading-7">
              <p className="font-serif text-2xl">{order.full_name}</p>
              <p className="mt-2 text-stone">{order.address}<br />{order.city}, {order.state} {order.pincode}<br />{order.country}</p>
              <p className="mt-3 text-stone">{order.email} · {order.mobile}</p>
              <Link to="/cart/" className="noore-link mt-4 inline-block text-[10px] uppercase tracking-[0.15em]">Change details</Link>
            </div>

            <p className="mb-5 mt-12 text-[10px] uppercase tracking-[0.2em]">Items</p>
            <div className="flex flex-col gap-5">
              {(order.orderitem || []).map((item) => (
                <div className="flex items-center gap-4" key={item.id} data-testid="checkout-line">
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
          </section>

          {/* Summary: every price, fee and discount is visible before the customer pays. */}
          <section className="h-fit bg-sand p-6 md:p-8" data-testid="checkout-summary">
            <p className="mb-6 text-[10px] uppercase tracking-[0.2em]">Order summary</p>
            <div className="flex flex-col gap-3 text-sm">
              <div className="flex justify-between"><span>Subtotal</span><span data-testid="summary-subtotal">{formatINR(order.sub_total_paise)}</span></div>
              {hasDiscount &&
                <div className="flex justify-between text-clay"><span>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</span><span data-testid="summary-discount">-{formatINR(order.saved_paise)}</span></div>
              }
              <div className="flex justify-between"><span>Shipping</span><span data-testid="summary-shipping">{order.shipping_amount_paise > 0 ? formatINR(order.shipping_amount_paise) : 'Free'}</span></div>
              <div className="mt-3 flex justify-between border-t border-line pt-4 font-serif text-2xl"><span>Total</span><span data-testid="summary-total">{formatINR(order.total_paise)}</span></div>
              <p className="text-xs text-stone">Inclusive of all taxes</p>
            </div>

            <div className="mt-7 flex items-center border-b border-line-strong">
              <input onChange={(e) => setCouponCode(e.target.value)} value={couponCode} readOnly={couponBusy} name="couponCode" type="text"
                aria-label="Coupon code" placeholder={order.coupon_code ? 'Use a different coupon' : 'Coupon code'}
                className="min-h-12 min-w-0 flex-1 bg-transparent text-sm uppercase outline-none" />
              <button onClick={applyCoupon} disabled={couponBusy} className="text-[10px] uppercase tracking-[0.15em] text-clay">{couponBusy ? '...' : 'Apply'}</button>
            </div>
            {order.coupon_code &&
              <p className="mt-3 text-xs text-stone">
                Coupon <b>{order.coupon_code}</b> applied.{' '}
                <button type="button" className="noore-link" disabled={couponBusy} onClick={() => submitCoupon("")}>Remove</button>
              </p>
            }

            {/* How to pay. Neither option costs more than the other: no COD fee is charged. */}
            <p className="mb-3 mt-9 text-[10px] uppercase tracking-[0.2em]">How would you like to pay?</p>
            <div className="flex flex-col gap-2" data-testid="payment-methods">
              {onlineOffered &&
                <label htmlFor="payOnline" className={radio(method === METHOD_ONLINE)}>
                  <input type="radio" name="paymentMethod" id="payOnline" className="accent-ink" checked={method === METHOD_ONLINE} onChange={() => setMethod(METHOD_ONLINE)} />
                  UPI / Card / Netbanking
                </label>
              }
              {codOffered &&
                <label htmlFor="payCod" className={radio(method === METHOD_COD)}>
                  <input type="radio" name="paymentMethod" id="payCod" className="accent-ink" checked={method === METHOD_COD} onChange={() => setMethod(METHOD_COD)} />
                  Cash on delivery
                </label>
              }
              {methods !== null && !onlineOffered && !codOffered &&
                <p className="text-xs text-danger">No payment method is available right now. Please contact us.</p>
              }
            </div>

            {method === METHOD_ONLINE && onlineOffered &&
              <button onClick={payOnline} type="button" disabled={paying} className="noore-btn mt-6 w-full" data-testid="pay-online">
                {paying ? 'Please wait...' : <>Pay {formatINR(order.total_paise)}</>}
              </button>
            }
            {method === METHOD_COD && codOffered &&
              <>
                <button onClick={placeCod} type="button" disabled={paying} className="noore-btn mt-6 w-full" data-testid="place-cod">
                  {paying ? 'Please wait...' : 'Place order'}
                </button>
                <p className="mt-3 text-xs leading-6 text-stone">You pay {formatINR(order.total_paise)} in cash when your order arrives. We may call or message you to confirm it before we send it.</p>
              </>
            }

            <p className="mt-6 text-xs leading-6 text-stone" data-testid="checkout-policies">
              Before you pay, please read our{' '}
              {POLICY_LINKS.map((policy, index) => (
                <span key={policy.path}>
                  <Link to={policy.path} target="_blank" rel="noopener noreferrer" className="noore-link">{policy.title}</Link>
                  {index < POLICY_LINKS.length - 1 ? ', ' : '. '}
                </span>
              ))}
              Need help? <Link to="/contact" target="_blank" rel="noopener noreferrer" className="noore-link">Contact us</Link>.
            </p>
          </section>
        </div>
      </div>
    </main>
  )
}

export default Checkout