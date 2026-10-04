import { Link, useParams } from 'react-router-dom';

import Addon from '../plugin/Addon';
import { formatINR } from '../../utils/money';
import { STORE_NAME, SUPPORT_EMAIL } from '../../utils/constants';
import usePageTitle from '../../utils/usePageTitle';
import { PageIntro } from '../ui/noore';
import NotFound from '../base/NotFound';
import { PLACEHOLDER_COPY, POLICIES } from './policies';

// Shown on every policy page while the copy is still placeholder text.
export function PlaceholderNotice() {
    if (!PLACEHOLDER_COPY) return null;
    return (
        <p className="mb-8 border border-clay/40 bg-sand px-4 py-3 text-xs text-clay" role="note" data-testid="placeholder-notice">
            <strong>Placeholder text.</strong> This page is a draft layout. The final policy wording has not been published yet.
        </p>
    );
}

// Renders one policy from views/policy/policies.js. The shipping figures are read live from
// the server's settings so the page always matches what checkout charges.
function PolicyPage() {
    const { slug } = useParams();
    const addon = Addon();
    const policy = POLICIES[slug];
    usePageTitle(policy?.title);

    if (!policy) {
        return <NotFound />;
    }

    const tokens = {
        '{shipping}': addon?.shipping_flat_paise != null ? formatINR(addon.shipping_flat_paise) : 'a flat charge',
        '{threshold}': addon?.free_shipping_threshold_paise != null ? formatINR(addon.free_shipping_threshold_paise) : 'the free-shipping amount',
        '{email}': SUPPORT_EMAIL,
        '{store}': STORE_NAME,
    };
    const fill = (text) => Object.entries(tokens).reduce((result, [token, value]) => result.split(token).join(value), text);

    return (
        <main data-testid={`policy-${slug}`}>
            <PageIntro eyebrow="Customer care" title={policy.title} />
            <div className="mx-auto max-w-3xl px-5 py-12 md:px-10 md:py-20">
                <PlaceholderNotice />
                {policy.sections.map((section) => (
                    <section className="mb-10" key={section.heading}>
                        <h2 className="font-serif text-2xl">{section.heading}</h2>
                        {section.paragraphs.map((paragraph, index) => (
                            <p className="mt-4 text-sm leading-7 text-stone" key={index}>{fill(paragraph)}</p>
                        ))}
                    </section>
                ))}
                <p className="border-t border-line pt-6 text-sm text-stone">
                    Questions? <Link to="/contact" className="noore-link text-ink">Contact us</Link>.
                </p>
            </div>
        </main>
    );
}

export default PolicyPage;
