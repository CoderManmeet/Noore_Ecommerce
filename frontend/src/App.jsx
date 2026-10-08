import { Suspense, lazy, useEffect, useState } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';

import MainWrapper from './layouts/MainWrapper';
import PrivateRoute from './layouts/PrivateRoute';
import LegacyStyles from './layouts/LegacyStyles';
import { useAuthStore } from './store/auth';
import apiInstance from './utils/axios';
import { CartContext } from './views/plugin/Context';
import UserData from './views/plugin/UserData';
import CartID from './views/plugin/cartID';

import StoreHeader from './views/base/StoreHeader';
import StoreFooter from './views/base/StoreFooter';
import NotFound from './views/base/NotFound';

// Storefront (Noore design)
import Home from './views/shop/home';
import Shop from './views/shop/Products';
import ProductDetail from './views/shop/ProductDetail';
import Cart from './views/shop/Cart';
import Checkout from './views/shop/Checkout';
import OrderConfirmation from './views/shop/OrderConfirmation';
import About from './views/policy/About';
import PolicyPage from './views/policy/PolicyPage';
import Contact from './views/policy/Contact';
import Login from './views/auth/login';
import Register from './views/auth/register';
import Logout from './views/auth/logout';
import ClaimAccount from './views/auth/ClaimAccount';
import Orders from './views/customer/Orders';
import OrderDetail from './views/customer/OrderDetail';

// Pages a shopper never opens are kept out of the storefront's own download and fetched only
// when someone actually goes there. The admin area alone (with its rich-text editor) is most of
// the JavaScript in this project; a shopper should not be waiting for it before seeing a candle.
const lazyPage = (loader) => lazy(loader);

// Older customer pages, still in their original Bootstrap styling
const ForgotPassword = lazyPage(() => import('./views/auth/forgotPassword'));
const CreatePassword = lazyPage(() => import('./views/auth/createPassword'));
const PaymentSuccess = lazyPage(() => import('./views/shop/PaymentSuccess'));
const Invoice = lazyPage(() => import('./views/shop/Invoice'));
const Account = lazyPage(() => import('./views/customer/Account'));
const Wishlist = lazyPage(() => import('./views/customer/Wishlist'));
const Notifications = lazyPage(() => import('./views/customer/Notifications'));
const Settings = lazyPage(() => import('./views/customer/Settings'));

// Admin area (the owner dashboard)
const Dashboard = lazyPage(() => import('./views/vendor/Dashboard'));
const Products = lazyPage(() => import('./views/vendor/Products'));
const AddProduct = lazyPage(() => import('./views/vendor/AddProduct'));
const UpdateProduct = lazyPage(() => import('./views/vendor/UpdateProduct'));
const DashboardOrders = lazyPage(() => import('./views/vendor/Orders'));
const DashboardOrderDetail = lazyPage(() => import('./views/vendor/OrderDetail'));
const OrderItemDetail = lazyPage(() => import('./views/vendor/OrderItemDetail'));
const Earning = lazyPage(() => import('./views/vendor/Earning'));
const Reviews = lazyPage(() => import('./views/vendor/Reviews'));
const ReviewDetail = lazyPage(() => import('./views/vendor/ReviewDetail'));
const Coupon = lazyPage(() => import('./views/vendor/Coupon'));
const EditCoupon = lazyPage(() => import('./views/vendor/EditCoupon'));
const DashboardNotifications = lazyPage(() => import('./views/vendor/Notifications'));
const DashboardSettings = lazyPage(() => import('./views/vendor/Settings'));
const OwnerOrders = lazyPage(() => import('./views/owner/OwnerOrders'));
const OwnerOrderDetail = lazyPage(() => import('./views/owner/OwnerOrderDetail'));
const OwnerReviews = lazyPage(() => import('./views/owner/OwnerReviews'));
const ShopNotReady = lazyPage(() => import('./views/owner/ShopNotReady'));

// Shown for the moment a lazily-loaded page is being fetched.
function PageLoading() {
    return <div className="px-5 py-24 text-center text-sm text-stone" role="status">Loading...</div>;
}

// The storefront: Noore header and footer around a Noore-styled page.
function StorefrontLayout() {
    return (
        <div className="noore-shell font-sans" data-layout="storefront">
            <StoreHeader />
            <Outlet />
            <StoreFooter />
        </div>
    );
}

// Older pages keep their Bootstrap styling (loaded only while they are open) inside the same
// Noore header and footer.
function LegacyLayout() {
    return (
        <div className="noore-shell" data-layout="legacy">
            <LegacyStyles />
            <StoreHeader />
            <Outlet />
            <StoreFooter />
        </div>
    );
}

const useIsStaff = () => {
    const [isLoggedIn, user] = useAuthStore((state) => [state.isLoggedIn, state.user]);
    return isLoggedIn() && user().is_staff;
};

// The brand's shop, from the sign-in token. 0 means this staff account does not own it yet.
const useHasShop = () => {
    const user = useAuthStore((state) => state.user);
    return Boolean(user().vendor_id);
};

// The admin area is shown to staff only. Anyone else gets the ordinary not-found page, exactly
// as if the address did not exist. This is a convenience gate: the API itself refuses every
// owner request that does not come from a staff account.
function AdminArea() {
    const isStaff = useIsStaff();
    const hasShop = useHasShop();
    const location = useLocation();
    if (!isStaff) {
        return (
            <div className="noore-shell font-sans" data-layout="storefront">
                <StoreHeader />
                <NotFound />
                <StoreFooter />
            </div>
        );
    }
    // Staff, but the shop is not attached to this account yet: say so, with the command that
    // fixes it. The owner-order and review screens do not need a shop, so they still open.
    if (!hasShop && !location.pathname.includes('/owner/')) {
        return (
            <div className="noore-shell font-sans" data-layout="admin">
                <StoreHeader />
                <ShopNotReady />
                <StoreFooter />
            </div>
        );
    }

    // `noore-admin` is what src/theme/admin.css hangs off: it gives the dashboard's existing
    // Bootstrap-style markup (cards, tables, buttons, forms) the Noore look, so the admin area
    // no longer loads Bootstrap at all.
    return (
        <div className="noore-shell noore-admin" data-layout="admin">
            <StoreHeader />
            <Outlet />
        </div>
    );
}

// Old dashboard addresses (/vendor/... and /owner/...). Staff are sent to the same screen
// under /admin-area/; everyone else sees the not-found page.
function OldDashboardAddress() {
    const isStaff = useIsStaff();
    const location = useLocation();
    if (!isStaff) {
        return (
            <div className="noore-shell font-sans" data-layout="storefront">
                <StoreHeader />
                <NotFound />
                <StoreFooter />
            </div>
        );
    }
    const target = location.pathname.startsWith('/owner')
        ? `/admin-area${location.pathname}`
        : location.pathname.replace(/^\/vendor/, '/admin-area');
    return <Navigate to={`${target}${location.search}`} replace />;
}

function App() {
    const [cartCount, setCartCount] = useState()
    const userData = UserData()
    const cart_id = CartID()

    useEffect(() => {
        const url = userData?.user_id ? `cart-list/${cart_id}/${userData?.user_id}/` : `cart-list/${cart_id}/`;
        apiInstance.get(url).then((res) => {
            setCartCount(res.data.length)
        }).catch(() => setCartCount(0));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    return (
        <CartContext.Provider value={[cartCount, setCartCount]} >
            <BrowserRouter>
                <MainWrapper>
                    <Suspense fallback={<PageLoading />}>
                    <Routes>
                        <Route element={<StorefrontLayout />}>
                            <Route path="/" element={<Home />} />
                            <Route path="/shop" element={<Shop />} />
                            <Route path="/search" element={<Shop />} />
                            <Route path="/detail/:slug" element={<ProductDetail />} />
                            <Route path="/cart/" element={<Cart />} />
                            <Route path="/checkout/:order_oid" element={<Checkout />} />
                            <Route path="/order/:order_oid/" element={<OrderConfirmation />} />
                            <Route path="/about" element={<About />} />
                            <Route path="/policy/:slug" element={<PolicyPage />} />
                            <Route path="/contact" element={<Contact />} />

                            <Route path="/login" element={<Login />} />
                            <Route path="/register" element={<Register />} />
                            <Route path="/logout" element={<Logout />} />
                            <Route path="/claim-account" element={<ClaimAccount />} />

                            <Route path="/customer/orders/" element={<PrivateRoute><Orders /></PrivateRoute>} />
                            <Route path="/customer/order/detail/:order_oid/" element={<PrivateRoute><OrderDetail /></PrivateRoute>} />

                            <Route path="*" element={<NotFound />} />
                        </Route>

                        <Route element={<LegacyLayout />}>
                            <Route path="/forgot-password" element={<ForgotPassword />} />
                            <Route path="/create-new-password" element={<CreatePassword />} />
                            <Route path="/payment-success/:order_oid/" element={<PaymentSuccess />} />
                            <Route path="/invoice/:order_oid/" element={<Invoice />} />
                            <Route path="/customer/account/" element={<PrivateRoute><Account /></PrivateRoute>} />
                            <Route path="/customer/wishlist/" element={<PrivateRoute><Wishlist /></PrivateRoute>} />
                            <Route path="/customer/notifications/" element={<PrivateRoute><Notifications /></PrivateRoute>} />
                            <Route path="/customer/settings/" element={<PrivateRoute><Settings /></PrivateRoute>} />
                        </Route>

                        <Route path="/admin-area" element={<AdminArea />}>
                            <Route index element={<Navigate to="/admin-area/dashboard/" replace />} />
                            <Route path="dashboard/" element={<Dashboard />} />
                            <Route path="products/" element={<Products />} />
                            <Route path="product/new/" element={<AddProduct />} />
                            <Route path="product/update/:pid/" element={<UpdateProduct />} />
                            <Route path="orders/" element={<DashboardOrders />} />
                            <Route path="orders/:oid/" element={<DashboardOrderDetail />} />
                            <Route path="orders/:oid/:id/" element={<OrderItemDetail />} />
                            <Route path="earning/" element={<Earning />} />
                            <Route path="reviews/" element={<Reviews />} />
                            <Route path="reviews/:id/" element={<ReviewDetail />} />
                            <Route path="coupon/" element={<Coupon />} />
                            <Route path="coupon/:id/" element={<EditCoupon />} />
                            <Route path="notifications/" element={<DashboardNotifications />} />
                            <Route path="settings/" element={<DashboardSettings />} />
                            <Route path="owner/orders/" element={<OwnerOrders />} />
                            <Route path="owner/orders/:oid/" element={<OwnerOrderDetail />} />
                            <Route path="owner/reviews/" element={<OwnerReviews />} />
                            <Route path="*" element={<NotFound />} />
                        </Route>

                        <Route path="/vendor/*" element={<OldDashboardAddress />} />
                        <Route path="/owner/*" element={<OldDashboardAddress />} />
                    </Routes>
                    </Suspense>
                </MainWrapper>
            </BrowserRouter>
        </CartContext.Provider >
    );
}

export default App;