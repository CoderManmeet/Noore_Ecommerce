import { Link, useLocation } from 'react-router-dom';
import {
    Bell, Boxes, ClipboardList, LayoutDashboard, LogOut, Package, PlusCircle,
    Settings as SettingsIcon, Star, Store, Tag, TrendingUp,
} from 'lucide-react';

// Admin navigation, in two groups: what the owner touches daily, and the rest.
// The screens themselves still carry their original markup; src/theme/admin.css gives it the
// Noore look.
const DAILY = [
    { to: '/admin-area/dashboard/', label: 'Dashboard', Icon: LayoutDashboard },
    { to: '/admin-area/owner/orders/', label: 'Orders', Icon: ClipboardList, hint: 'COD, shipping' },
    { to: '/admin-area/products/', label: 'Products', Icon: Package },
    { to: '/admin-area/product/new/', label: 'Add product', Icon: PlusCircle },
    { to: '/admin-area/owner/reviews/', label: 'Review moderation', Icon: Star },
];

const MORE = [
    { to: '/admin-area/coupon/', label: 'Coupons', Icon: Tag },
    { to: '/admin-area/earning/', label: 'Earnings', Icon: TrendingUp },
    { to: '/admin-area/orders/', label: 'All orders', Icon: Boxes },
    { to: '/admin-area/reviews/', label: 'All reviews', Icon: Star },
    { to: '/admin-area/notifications/', label: 'Notifications', Icon: Bell },
    { to: '/admin-area/settings/', label: 'Shop settings', Icon: SettingsIcon },
];

function Sidebar() {
    const { pathname } = useLocation();

    const item = ({ to, label, Icon, hint }) => {
        const active = pathname === to || (to !== '/admin-area/dashboard/' && pathname.startsWith(to));
        return (
            <li key={to}>
                <Link
                    to={to}
                    aria-current={active ? 'page' : undefined}
                    className={`flex items-center gap-3 px-4 py-3 text-xs transition-colors ${active
                        ? 'bg-ink text-cream'
                        : 'text-ink hover:bg-sand'}`}
                >
                    <Icon className="size-4 shrink-0" strokeWidth={1.5} aria-hidden="true" />
                    <span className="min-w-0">
                        {label}
                        {hint && <span className={`block text-[10px] ${active ? 'text-cream/60' : 'text-stone'}`}>{hint}</span>}
                    </span>
                </Link>
            </li>
        );
    };

    const heading = 'px-4 pb-2 pt-5 text-[10px] uppercase tracking-[0.18em] text-stone';

    return (
        <nav aria-label="Admin" className="w-full shrink-0 border-line bg-cream md:w-60 md:border-r" data-testid="admin-sidebar">
            <div className="sticky top-0 pb-6">
                <p className={heading}>Every day</p>
                <ul className="list-none p-0">{DAILY.map(item)}</ul>
                <p className={heading}>More</p>
                <ul className="list-none p-0">{MORE.map(item)}</ul>
                <div className="mt-6 border-t border-line pt-4">
                    <Link to="/" className="flex items-center gap-3 px-4 py-2 text-xs text-stone hover:text-ink">
                        <Store className="size-4" strokeWidth={1.5} aria-hidden="true" /> View the shop
                    </Link>
                    <Link to="/logout" className="flex items-center gap-3 px-4 py-2 text-xs text-stone hover:text-ink">
                        <LogOut className="size-4" strokeWidth={1.5} aria-hidden="true" /> Sign out
                    </Link>
                </div>
            </div>
        </nav>
    );
}

export default Sidebar;