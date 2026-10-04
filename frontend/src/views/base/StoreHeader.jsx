import { useContext, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Menu, Search, ShoppingBag, User, X } from 'lucide-react';

import { useAuthStore } from '../../store/auth';
import { CartContext } from '../plugin/Context';
import Addon from '../plugin/Addon';
import { formatINR } from '../../utils/money';

// Storefront header (Noore design). Shoppers see: Shop, About, search, their account and the
// bag. Staff additionally see one "Admin" link; nobody else sees any link to the dashboard.
export function Logo({ className = '' }) {
    return (
        <Link to="/" aria-label="Noore home" className={`font-serif text-[1.65rem] font-semibold uppercase leading-none tracking-[0.24em] text-ink ${className}`}>
            Noore
        </Link>
    );
}

const NAV_LINK = 'text-[10px] uppercase tracking-[0.2em] text-stone transition-colors hover:text-ink';

function StoreHeader() {
    const [cartCount] = useContext(CartContext);
    const [menuOpen, setMenuOpen] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);
    const [search, setSearch] = useState('');
    const [isLoggedIn, user] = useAuthStore((state) => [state.isLoggedIn, state.user]);
    const addon = Addon();
    const navigate = useNavigate();
    const location = useLocation();

    // Close the menus whenever the page changes.
    useEffect(() => {
        setMenuOpen(false);
        setSearchOpen(false);
    }, [location.pathname, location.search]);

    const submitSearch = (event) => {
        event.preventDefault();
        const query = search.trim();
        navigate(query ? `/shop?query=${encodeURIComponent(query)}` : '/shop');
    };

    const signedIn = isLoggedIn();
    const isStaff = signedIn && user().is_staff;

    return (
        <div className="noore-chrome font-sans">
            {addon?.free_shipping_threshold_paise != null &&
                <div className="bg-ink px-4 py-2.5 text-center text-[9px] uppercase leading-4 tracking-[0.16em] text-cream sm:text-[10px] sm:tracking-[0.22em]" data-testid="announcement">
                    Free shipping on orders of {formatINR(addon.free_shipping_threshold_paise)} or more
                </div>
            }
            <header className="relative border-b border-line bg-cream">
                <div className="mx-auto grid h-16 max-w-[1440px] grid-cols-[1fr_auto_1fr] items-center px-4 sm:px-5 md:h-[72px] md:px-10">
                    <div className="flex items-center gap-1 md:gap-7">
                        <button type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} onClick={() => setMenuOpen((open) => !open)} className="flex size-10 items-center justify-start md:hidden">
                            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
                        </button>
                        <nav aria-label="Main" className="hidden items-center gap-7 md:flex">
                            <Link to="/shop" className={NAV_LINK}>Shop</Link>
                            <Link to="/about" className={NAV_LINK}>Our story</Link>
                            <Link to="/contact" className={NAV_LINK}>Contact</Link>
                        </nav>
                    </div>
                    <Logo />
                    <div className="flex items-center justify-end gap-1 sm:gap-2 md:gap-4">
                        {isStaff && <Link to="/admin-area/dashboard/" className={`${NAV_LINK} hidden md:inline`} data-testid="admin-link">Admin</Link>}
                        <button type="button" aria-label="Search" onClick={() => setSearchOpen((open) => !open)} className="flex size-10 items-center justify-center">
                            <Search className="size-[18px]" strokeWidth={1.5} aria-hidden="true" />
                        </button>
                        <Link to={signedIn ? '/customer/orders/' : '/login'} aria-label={signedIn ? 'My account' : 'Sign in'} className="hidden size-10 items-center justify-center md:flex" data-testid="account-link">
                            <User className="size-[18px]" strokeWidth={1.5} aria-hidden="true" />
                        </Link>
                        <Link to="/cart/" aria-label="Open shopping bag" className="relative flex size-10 items-center justify-center">
                            <ShoppingBag className="size-[18px]" strokeWidth={1.5} aria-hidden="true" />
                            {cartCount > 0 &&
                                <span className="absolute right-0.5 top-0.5 flex size-4 items-center justify-center bg-clay text-[9px] leading-none text-white" data-testid="cart-count">{cartCount}</span>
                            }
                        </Link>
                    </div>
                </div>

                {searchOpen &&
                    <div className="border-t border-line px-5 py-4">
                        <form onSubmit={submitSearch} className="mx-auto flex max-w-[600px] items-center gap-3 border-b border-line-strong pb-2" role="search">
                            <Search className="size-4" aria-hidden="true" />
                            <input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search candles" placeholder="Search by scent or name" className="w-full bg-transparent text-base outline-none" />
                            <button type="submit" className="text-[10px] uppercase tracking-[0.18em] text-clay">Search</button>
                        </form>
                    </div>
                }

                {menuOpen &&
                    <div className="absolute inset-x-0 top-full z-20 border-b border-line bg-cream px-5 py-6 shadow-sm md:hidden">
                        <nav aria-label="Mobile" className="flex flex-col gap-5 text-[11px] uppercase tracking-[0.2em]">
                            <Link to="/shop">Shop candles</Link>
                            <Link to="/about">Our story</Link>
                            <Link to={signedIn ? '/customer/orders/' : '/login'}>{signedIn ? 'My orders' : 'Sign in'}</Link>
                            {signedIn && <Link to="/logout">Sign out</Link>}
                            <Link to="/policy/shipping">Shipping</Link>
                            <Link to="/contact">Contact</Link>
                            {isStaff && <Link to="/admin-area/dashboard/">Admin</Link>}
                        </nav>
                    </div>
                }
            </header>
        </div>
    );
}

export default StoreHeader;
