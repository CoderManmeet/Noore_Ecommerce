import { Link } from 'react-router-dom';
import { MessageCircle } from 'lucide-react';

import { STORE_NAME, SUPPORT_EMAIL, WHATSAPP_LINK } from '../../utils/constants';
import { POLICY_LINKS } from '../policy/policies';
import { Logo } from './StoreHeader';

// Storefront footer (Noore design): policies, a named way to reach the store, and a floating
// WhatsApp button. The email and number come from VITE_SUPPORT_EMAIL / VITE_WHATSAPP_NUMBER.
function StoreFooter() {
    return (
        <div className="noore-chrome font-sans">
            <footer className="mt-20 bg-linen px-5 py-12 text-ink md:px-10">
                <div className="mx-auto grid max-w-[1440px] gap-10 md:grid-cols-4">
                    <div>
                        <Logo />
                        <p className="mt-4 max-w-xs text-xs leading-6 text-stone">Hand-poured scented candles, made in small batches.</p>
                    </div>
                    <div>
                        <p className="mb-4 text-[10px] uppercase tracking-[0.2em]">Explore</p>
                        <div className="flex flex-col gap-3 text-xs text-stone">
                            <Link to="/shop">Shop candles</Link>
                            <Link to="/about">Our story</Link>
                            <Link to="/customer/orders/">My orders</Link>
                        </div>
                    </div>
                    <div>
                        <p className="mb-4 text-[10px] uppercase tracking-[0.2em]">Policies</p>
                        <ul className="flex flex-col gap-3 text-xs text-stone" data-testid="footer-policies">
                            {POLICY_LINKS.map((policy) => (
                                <li key={policy.path}><Link to={policy.path}>{policy.title}</Link></li>
                            ))}
                        </ul>
                    </div>
                    <div>
                        <p className="mb-4 text-[10px] uppercase tracking-[0.2em]">Support</p>
                        <div className="flex flex-col gap-3 text-xs text-stone">
                            <Link to="/contact">Contact us</Link>
                            <a href={`mailto:${SUPPORT_EMAIL}`} data-testid="footer-email">{SUPPORT_EMAIL}</a>
                            <a href={WHATSAPP_LINK} target="_blank" rel="noopener noreferrer" data-testid="footer-whatsapp">Chat on WhatsApp</a>
                        </div>
                    </div>
                </div>
                <div className="mx-auto mt-12 max-w-[1440px] border-t border-line pt-5 text-[10px] uppercase tracking-[0.12em] text-stone">
                    © {new Date().getFullYear()} {STORE_NAME} · Prices in Indian rupees, inclusive of all taxes
                </div>
            </footer>
            <a href={WHATSAPP_LINK} target="_blank" rel="noopener noreferrer" aria-label={`Chat with ${STORE_NAME} on WhatsApp`} className="fixed bottom-5 right-4 z-40 flex size-12 items-center justify-center rounded-full bg-ink text-cream shadow-lg">
                <MessageCircle className="size-5" aria-hidden="true" />
            </a>
        </div>
    );
}

export default StoreFooter;
