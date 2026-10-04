import React from 'react'
import { Link, useLocation } from 'react-router-dom';
import UserData from '../plugin/UserData';


function Sidebar() {
    const currentPathname = window.location.pathname;
    const location = useLocation();
    const isActiveLink = (currentPath, linkPath) => {
        return currentPath.includes(linkPath);
    };



    return (
        <div className="col-md-3 col-lg-2 sidebar-offcanvas bg-dark navbar-dark" id="sidebar" role="navigation" >
            <ul className="nav nav-pills flex-column mb-auto nav flex-column pl-1 pt-2">
                <li className="mb-3">
                    <Link to="/admin-area/dashboard/" className={isActiveLink(location.pathname, '/admin-area/dashboard/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-speedometer" /> Dashboard{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/products/" className={isActiveLink(location.pathname, '/admin-area/products/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-grid" /> Products{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/orders/" className={isActiveLink(location.pathname, '/admin-area/orders/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-cart-check" /> Orders{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/owner/orders/" className={isActiveLink(location.pathname, '/admin-area/owner/orders/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-box-seam" /> Handle orders (COD, shipping){" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/owner/reviews/" className={isActiveLink(location.pathname, '/admin-area/owner/reviews/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-star" /> Review moderation{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/earning/" className={isActiveLink(location.pathname, '/admin-area/earning/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-currency-dollar" /> Earning{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/reviews/" className={isActiveLink(location.pathname, '/admin-area/reviews/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-star" /> Reviews{" "}
                    </Link>
                </li>
                <li className="mb-3">
                    <Link to="/admin-area/product/new/" className={isActiveLink(location.pathname, '/admin-area/product/new/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-plus-circle" /> Add Product{" "}
                    </Link>
                </li>
                {/* <li className="mb-3">
                    <a href="faqs.html" className={isActiveLink(location.pathname, '/admin-area/faqs/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-patch-question" /> FAQs{" "}
                    </a>
                </li> */}
                <li className="mb-3">
                    <Link to={`/admin-area/coupon/`} className={isActiveLink(location.pathname, '/admin-area/coupon/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-tag" /> Coupon &amp; Discount{" "}
                    </Link>
                </li>
                {/* <li className="mb-3">
                    <a href="customers.html" className={isActiveLink(location.pathname, '/admin-area/customers/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-people" /> Customers{" "}
                    </a>
                </li> */}
                <li className="mb-3">
                    <Link to={`/admin-area/notifications/`} className={isActiveLink(location.pathname, '/admin-area/notifications/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-bell" /> Notifications{" "}
                    </Link>
                </li>
                {/* <li className="mb-3">
                    <a href="message.html" className={isActiveLink(location.pathname, '/admin-area/message/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-envelope" /> Message{" "}
                    </a>
                </li> */}
                <li className="mb-3">
                    <Link to="/admin-area/settings/" className={isActiveLink(location.pathname, '/admin-area/settings/') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-gear-fill" /> Settings{" "}
                    </Link>
                </li>

                <li className="mb-3">
                    <Link to="/logout" className={isActiveLink(location.pathname, '/logout') ? "nav-link text-white active" : "nav-link text-white"}>
                        {" "}
                        <i className="bi bi-box-arrow-left" /> Logout{" "}
                    </Link>
                </li>

            </ul>
            <hr />
        </div >
    )
}

export default Sidebar