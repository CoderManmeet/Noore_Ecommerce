import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import moment from 'moment';

import apiInstance from '../../utils/axios';
import Sidebar from '../vendor/Sidebar';
import { formatINR } from '../../utils/money';

// Every order a customer has placed: paid online, Cash on Delivery, cancelled or refunded.
// (The older "Orders" screen lists paid orders only, so COD orders awaiting cash never showed.)
function OwnerOrders() {
    const [orders, setOrders] = useState(null)

    useEffect(() => {
        apiInstance.get('owner/orders/').then((res) => setOrders(res.data))
            .catch((error) => { console.error(error); setOrders([]) })
    }, [])

    return (
        <div className="container-fluid" id="main">
            <div className="row row-offcanvas row-offcanvas-left h-100">
                <Sidebar />
                <div className="col-md-9 col-lg-10 main mt-4" data-testid="owner-orders">
                    <h4><i className="bi bi-box-seam" /> Orders to handle</h4>
                    <p className="text-muted">Cash on Delivery orders must be confirmed with the customer before they can be shipped.</p>
                    {orders === null && <p><i className='fas fa-spinner fa-spin'></i> Loading...</p>}
                    {orders !== null && orders.length === 0 && <p>No orders yet.</p>}
                    {orders !== null && orders.length > 0 &&
                        <div className="table-responsive">
                            <table className="table">
                                <thead className="table-dark">
                                    <tr>
                                        <th scope="col">Order</th>
                                        <th scope="col">Date</th>
                                        <th scope="col">Customer</th>
                                        <th scope="col">Payment</th>
                                        <th scope="col">Status</th>
                                        <th scope="col">Total</th>
                                        <th scope="col"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {orders.map((o) => (
                                        <tr key={o.oid}>
                                            <th scope="row">
                                                #{o.oid}
                                                {o.needs_attention && <span className="badge bg-danger ms-2">Needs attention</span>}
                                            </th>
                                            <td>{moment(o.date).format('DD MMM YYYY')}</td>
                                            <td>{o.full_name}</td>
                                            <td>
                                                {o.payment_method === 'COD' ? 'Cash on Delivery' : 'Online'} · {o.payment_status}
                                                {o.payment_method === 'COD' && !o.cod_confirmed_at && o.order_status !== 'Cancelled' &&
                                                    <span className="badge bg-warning text-dark ms-2">Confirm COD</span>
                                                }
                                            </td>
                                            <td>{o.order_status}</td>
                                            <td>{formatINR(o.total_paise)}</td>
                                            <td><Link to={`/admin-area/owner/orders/${o.oid}/`} className="btn btn-primary btn-sm">Open</Link></td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    }
                </div>
            </div>
        </div>
    )
}

export default OwnerOrders
