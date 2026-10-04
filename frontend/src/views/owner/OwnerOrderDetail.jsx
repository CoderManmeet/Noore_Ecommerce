import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import moment from 'moment';
import Swal from 'sweetalert2';

import apiInstance from '../../utils/axios';
import Sidebar from '../vendor/Sidebar';
import { formatINR } from '../../utils/money';

// One order, with the actions the owner takes on it. Every button posts to the server, which
// runs the change through the order state machine: it refuses anything that is not allowed
// (for example shipping an unconfirmed Cash on Delivery order) and records who did what.
const DELIVERY_STEPS = ['On Hold', 'Shipping Processing', 'Shipped', 'Arrived', 'Delivered'];

function OwnerOrderDetail() {
    const { oid } = useParams()
    const [order, setOrder] = useState(null)
    const [couriers, setCouriers] = useState([])
    const [trackingId, setTrackingId] = useState("")
    const [courierId, setCourierId] = useState("")
    const [busy, setBusy] = useState(false)

    useEffect(() => {
        apiInstance.get(`owner/orders/${oid}/`).then((res) => setOrder(res.data))
        apiInstance.get('vendor/couriers/').then((res) => setCouriers(res.data)).catch(() => setCouriers([]))
    }, [oid])

    const act = async (payload, confirmText) => {
        if (confirmText) {
            const answer = await Swal.fire({ icon: 'question', title: confirmText, showCancelButton: true, confirmButtonText: 'Yes' })
            if (!answer.isConfirmed) return
        }
        setBusy(true)
        try {
            const response = await apiInstance.post(`owner/orders/${oid}/action/`, payload)
            setOrder(response.data)
        } catch (error) {
            Swal.fire({ icon: 'error', title: 'Not done', text: error?.response?.data?.message || 'Please try again.' })
        } finally {
            setBusy(false)
        }
    }

    if (order === null) {
        return <div className="container text-center mt-5"><i className='fas fa-spinner fa-spin'></i> Loading...</div>
    }

    const items = order.orderitem || []
    const isCod = order.payment_method === 'COD'
    const cancelled = order.order_status === 'Cancelled'
    const furthest = items.reduce((max, item) => Math.max(max, DELIVERY_STEPS.indexOf(item.delivery_status)), 0)
    const delivered = items.length > 0 && items.every((item) => item.delivery_status === 'Delivered')
    const canShip = !cancelled && ['paid', 'pending'].includes(order.payment_status)

    const setDelivery = (status) => act({
        action: 'set_delivery', status,
        ...(trackingId ? { tracking_id: trackingId } : {}),
        ...(courierId ? { courier_id: courierId } : {}),
    })

    return (
        <div className="container-fluid" id="main">
            <div className="row row-offcanvas row-offcanvas-left h-100">
                <Sidebar />
                <div className="col-md-9 col-lg-10 main mt-4" data-testid="owner-order">
                    <p><Link to="/admin-area/owner/orders/">&larr; All orders</Link></p>
                    <h4>Order #{order.oid}</h4>
                    <p className="text-muted">{moment(order.date).format('DD MMM YYYY, h:mm a')}</p>

                    {order.needs_attention &&
                        <div className="alert alert-danger d-flex justify-content-between align-items-center">
                            <span><b>Needs attention:</b> {order.needs_attention}</span>
                            <button className="btn btn-outline-danger btn-sm" disabled={busy} onClick={() => act({ action: 'clear_attention' }, 'Has this been dealt with?')}>Mark as dealt with</button>
                        </div>
                    }

                    <div className="row">
                        <div className="col-lg-6 mb-3">
                            <div className="card h-100"><div className="card-body">
                                <h6>Customer</h6>
                                <p className="mb-1">{order.full_name}</p>
                                <p className="mb-1">{order.email} · {order.mobile}</p>
                                <p className="mb-0">{order.address}, {order.city}, {order.state} {order.pincode}</p>
                            </div></div>
                        </div>
                        <div className="col-lg-6 mb-3">
                            <div className="card h-100"><div className="card-body">
                                <h6>Payment</h6>
                                <p className="mb-1">{isCod ? 'Cash on Delivery' : 'Online (Razorpay)'} · <b data-testid="owner-payment-status">{order.payment_status}</b></p>
                                <p className="mb-1">Order status: <b data-testid="owner-order-status">{order.order_status}</b></p>
                                {isCod &&
                                    <p className="mb-1" data-testid="owner-cod-state">
                                        {order.cod_confirmed_at
                                            ? <>Confirmed with customer on {moment(order.cod_confirmed_at).format('DD MMM YYYY, h:mm a')}</>
                                            : <span className="text-danger">Not confirmed with the customer yet</span>}
                                    </p>
                                }
                                <p className="mb-0">Total: <b>{formatINR(order.total_paise)}</b>{order.saved_paise > 0 ? ` (discount ${formatINR(order.saved_paise)}${order.coupon_code ? `, ${order.coupon_code}` : ''})` : ''}</p>
                            </div></div>
                        </div>
                    </div>

                    <table className="table">
                        <thead><tr><th>Item</th><th>Qty</th><th>Amount</th><th>Delivery</th><th>Tracking</th></tr></thead>
                        <tbody>
                            {items.map((item) => (
                                <tr key={item.id}>
                                    <td>{item.product?.title}{item.variant?.name && item.variant.name !== 'Default' ? ` (${item.variant.name})` : ''}</td>
                                    <td>{item.qty}</td>
                                    <td>{formatINR(item.total_paise)}</td>
                                    <td data-testid="owner-delivery-status">{item.delivery_status}</td>
                                    <td>{item.tracking_id || '-'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    <h6 className="mt-4">Actions</h6>
                    <div className="d-flex flex-wrap gap-2 mb-3">
                        {isCod && !order.cod_confirmed_at && !cancelled &&
                            <button className="btn btn-warning" disabled={busy} onClick={() => act({ action: 'confirm_cod' }, 'Have you confirmed this order with the customer by phone or WhatsApp?')}>Confirm COD</button>
                        }
                        {isCod && delivered && order.payment_status === 'pending' &&
                            <button className="btn btn-success" disabled={busy} onClick={() => act({ action: 'mark_paid' }, 'Has the cash been collected?')}>Mark cash collected</button>
                        }
                        {!cancelled &&
                            <button className="btn btn-outline-danger" disabled={busy} onClick={() => act({ action: 'cancel' }, 'Cancel this order and return its stock?')}>Cancel order</button>
                        }
                        {cancelled && order.payment_status === 'paid' &&
                            <button className="btn btn-outline-secondary" disabled={busy} onClick={() => act({ action: 'record_refund' }, 'Have you issued the refund in the Razorpay dashboard?')}>Record refund as issued</button>
                        }
                    </div>

                    {canShip && !delivered &&
                        <div className="card mb-4"><div className="card-body">
                            <h6>Shipping</h6>
                            <div className="row g-2 mb-3">
                                <div className="col-md-4">
                                    <label className="form-label" htmlFor="ownerCourier">Courier</label>
                                    <select id="ownerCourier" className="form-select" value={courierId} onChange={(e) => setCourierId(e.target.value)}>
                                        <option value="">(none)</option>
                                        {couriers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                    </select>
                                </div>
                                <div className="col-md-4">
                                    <label className="form-label" htmlFor="ownerTracking">Tracking number</label>
                                    <input id="ownerTracking" className="form-control" value={trackingId} onChange={(e) => setTrackingId(e.target.value)} />
                                </div>
                            </div>
                            <div className="d-flex flex-wrap gap-2">
                                {DELIVERY_STEPS.slice(1).map((step, index) => (
                                    index + 1 > furthest &&
                                    <button key={step} className="btn btn-primary" disabled={busy} onClick={() => setDelivery(step)}>
                                        Mark {step === 'Shipping Processing' ? 'as packing' : step.toLowerCase()}
                                    </button>
                                ))}
                            </div>
                            <p className="text-muted mt-2 mb-0"><small>Stock leaves the inventory ledger the first time the order is marked as packing or shipped. The customer is emailed when it is shipped.</small></p>
                        </div></div>
                    }
                </div>
            </div>
        </div>
    )
}

export default OwnerOrderDetail
