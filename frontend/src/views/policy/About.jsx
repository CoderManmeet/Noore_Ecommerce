import { Link } from 'react-router-dom';

import { STORE_NAME } from '../../utils/constants';
import usePageTitle from '../../utils/usePageTitle';
import { PageIntro } from '../ui/noore';
import { PLACEHOLDER_COPY } from './policies';

// About page.
//
// ============================  PLACEHOLDER COPY  ============================
// The paragraphs below are draft wording so the page can be laid out. They are NOT the
// brand's approved story, and they deliberately make no claim about ingredients, burn time or
// where the candles are made: those are statements the owner must supply and stand behind.
// Replace the text, then this page needs no other change.
// ============================================================================
function About() {
    usePageTitle('Our story');
    return (
        <main data-testid="about-page">
            <PageIntro eyebrow="Our story" title="A slower way of living." />
            <div className="mx-auto max-w-3xl px-5 py-12 md:px-10 md:py-20">
                {PLACEHOLDER_COPY &&
                    <p className="mb-8 border border-clay/40 bg-sand px-4 py-3 text-xs text-clay" role="note">
                        Draft text. The final story has not been published yet.
                    </p>
                }
                <div className="flex flex-col gap-6 text-sm leading-7 text-stone">
                    <p className="font-serif text-2xl leading-snug text-ink">{STORE_NAME} began with a simple belief: everyday rituals deserve beautiful attention.</p>
                    <p>[PLACEHOLDER] Who makes the candles, where, and how the brand started goes here.</p>
                    <p>[PLACEHOLDER] What the candles are made of, and how to care for them, goes here.</p>
                </div>
                <Link to="/shop" className="noore-btn mt-10">Shop candles</Link>
            </div>
        </main>
    );
}

export default About;
