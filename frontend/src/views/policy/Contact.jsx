import { Link } from 'react-router-dom';
import { Mail, MessageCircle } from 'lucide-react';

import { STORE_NAME, SUPPORT_EMAIL, WHATSAPP_LINK } from '../../utils/constants';
import usePageTitle from '../../utils/usePageTitle';
import { PageIntro } from '../ui/noore';
import { POLICY_LINKS } from './policies';

// Contact page: a named way to reach the store by email or WhatsApp (ROADMAP P13).
// The address and number come from VITE_SUPPORT_EMAIL / VITE_WHATSAPP_NUMBER.
function Contact() {
    usePageTitle('Contact us');
    return (
        <main data-testid="policy-contact">
            <PageIntro eyebrow="Customer care" title="Contact us" />
            <div className="mx-auto max-w-3xl px-5 py-12 md:px-10 md:py-20">
                <p className="text-sm leading-7 text-stone">Need help with an order from {STORE_NAME}? Write to us or message us on WhatsApp. Please include your order number so we can help you faster.</p>

                <div className="mt-8 grid gap-4 sm:grid-cols-2">
                    <a href={`mailto:${SUPPORT_EMAIL}`} className="flex items-center gap-4 border border-line p-5" data-testid="contact-email">
                        <Mail className="size-5 text-clay" aria-hidden="true" />
                        <span><span className="noore-label block">Email</span><span className="text-sm">{SUPPORT_EMAIL}</span></span>
                    </a>
                    <a href={WHATSAPP_LINK} target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 border border-line p-5" data-testid="contact-whatsapp">
                        <MessageCircle className="size-5 text-clay" aria-hidden="true" />
                        <span><span className="noore-label block">WhatsApp</span><span className="text-sm">Chat on WhatsApp</span></span>
                    </a>
                </div>

                <h2 className="mt-14 font-serif text-2xl">Policies</h2>
                <ul className="mt-4 flex flex-col gap-3 text-sm">
                    {POLICY_LINKS.map((link) => (
                        <li key={link.path}><Link to={link.path} className="noore-link">{link.title}</Link></li>
                    ))}
                </ul>
            </div>
        </main>
    );
}

export default Contact;
