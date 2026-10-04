import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom';
import '../style/InvoiceStyle.css'

import apiInstance from '../../utils/axios';
import { formatINR } from '../../utils/money';


function Invoice() {
    const [order, setOrder] = useState([])
    const [orderItems, setOrderItems] = useState([])
    const axios = apiInstance
    const param = useParams()

    useEffect(() => {
        axios.get(`checkout/${param?.order_oid}/`).then((res) => {
            setOrder(res.data);
            setOrderItems(res.data.orderitem);
        })
    }, [param])

    const handlePrint = () => {
        window.print();
    };

    return (
        <div>
            <>
                <div className="row d-flex justify-content-center p-2">
                    <div className="receipt-main col-xs-10 col-sm-10 col-md-6 col-xs-offset-1 col-sm-offset-1 col-md-offset-3">
                        <div className="d-flex justify-content-between">
                            <div className="row">
                                <div className="receipt-header">
                                    <div className="col-xs-6 col-sm-6 col-md-6">
                                        <div className="receipt-left">
                                            <img
                                                className="img-responsive"
                                                alt="iamgurdeeposahan"
                                                src="https://img.freepik.com/free-vector/bird-colorful-logo-gradient-vector_343694-1365.jpg"
                                                style={{ width: 71, borderRadius: 43 }}
                                            />
                                        </div>
                                    </div>
                                    <div className="col-xs-12 col-sm-12 col-md-12 text-left">
                                        <div className="receipt-right">
                                            <h5 className="margin-top-10">
                                                Desphixs<span className="text-warning">.</span>
                                            </h5>
                                            <p>
                                                <i className="fa fa-phone" /> +1 3649-6589
                                            </p>
                                            <p>
                                                <i className="fa fa-envelope" /> company@gmail.com
                                            </p>
                                            <p>
                                                <i className="fa fa-location-arrow" /> 123 Main Street
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div className="row">
                                <div className="receipt-header receipt-header-mid">
                                    <div className="col-xs-12 col-sm-12 col-md-12 text-left">
                                        <div className="receipt-right">
                                            <h5>Customer Details</h5>
                                            <p>
                                                <b>
                                                    <i className="fa fa-user" />
                                                </b>
                                                {order.full_name}
                                            </p>
                                            <p>
                                                <b>
                                                    <i className="fa fa-envelope" />
                                                </b>{order.email}
                                            </p>
                                            <p>
                                                <b>
                                                    <i className="fa fa-phone" />
                                                </b>{order.mobile}
                                            </p>
                                        </div>
                                    </div>
                                    <br />
                                    <div className="col-xs-12 col-sm-12 col-md-12">
                                        <div className="receipt-left">
                                            <h6>
                                                INVOICE ID #{order.oid}
                                            </h6>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div>

                            <table className="table table-bordered">
                                <thead>
                                    <tr>
                                        <th>Product</th>
                                        <th>Price</th>
                                        <th>Qty</th>
                                        <th>Sub Total</th>
                                        <th>Discount</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {orderItems.map((order, index) => (
                                        <tr>
                                            <td className="col-md-5">
                                                {order?.product?.title}
                                            </td>
                                            <td className="col-md-2">
                                                {formatINR(order?.price_paise)}
                                            </td>
                                            <td className="col-md-2">
                                                {order?.qty}
                                            </td>
                                            <td className="col-md-2">
                                                {formatINR(order?.sub_total_paise)}
                                            </td>
                                            <td className="col-md-2">
                                                {formatINR(order?.saved_paise)}
                                            </td>
                                        </tr>
                                    ))}

                                </tbody>
                            </table>
                            <div className="row">
                                <div className="col-xs-6 col-sm-6 col-md-6 col-lg-6 d-flex justify-content-start">

                                </div>
                                <div className="col-xs-6 col-sm-6 col-md-6 col-lg-6 d-flex justify-content-end">
                                    <div className="receipt-right">
                                        <h5>Summary</h5>
                                        <p className="mb-2">
                                            <b>Sub Total: </b>
                                            {formatINR(order.sub_total_paise)}
                                        </p>
                                        <p className="mb-2">
                                            <b>Shipping: </b>
                                            {order.shipping_amount_paise > 0 ? formatINR(order.shipping_amount_paise) : 'Free'}
                                        </p>
                                        {order.saved_paise > 0 &&
                                            <p className="mb-2">
                                                <b>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}: </b>
                                                -{formatINR(order.saved_paise)}
                                            </p>
                                        }
                                        <br />
                                        <p className="mb-2">
                                            <b>Total: </b>
                                            {formatINR(order.total_paise)}
                                        </p>
                                        <p className="mb-2 text-muted"><small>Inclusive of all taxes</small></p>

                                    </div>
                                </div>
                            </div>
                        </div>
                        <hr />
                        <div className="d-flex justify-content-center align-items-center">
                            <button onClick={handlePrint} id="printButton" className="btn btn-dark">
                                Print <i className="fas fa-print" />
                            </button>
                        </div>
                    </div>
                </div>
                {/* Print Windows */}
            </>

        </div>
    )
}

export default Invoice