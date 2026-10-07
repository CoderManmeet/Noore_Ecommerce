import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight } from 'lucide-react';

import { formatINR } from '../../utils/money';
import { imageUrl, SIZES } from '../../utils/image';

// Small shared pieces of the Noore storefront design.

// A product photo. If the file is missing or fails to load, nothing is drawn (the coloured
// block behind it remains), never the browser's broken-image icon.
export function Photo({ src, alt = '', className = '', width = SIZES.card, ...rest }) {
    const [failed, setFailed] = useState(false);
    useEffect(() => { setFailed(false); }, [src]);
    if (!src || failed) return null;
    // `width` is the widest this photo is ever drawn; Cloudinary then sends a file that size
    // instead of the original upload. See src/utils/image.js.
    return <img src={imageUrl(src, width)} alt={alt} className={className} loading="lazy" decoding="async"
                onError={() => setFailed(true)} {...rest} />;
}

export function PageIntro({ eyebrow, title, children }) {
    return (
        <div className="border-b border-line bg-sand px-5 py-14 md:px-10 md:py-20">
            <div className="mx-auto max-w-[1440px]">
                {eyebrow && <p className="noore-eyebrow mb-4">{eyebrow}</p>}
                <h1 className="max-w-3xl font-serif text-4xl leading-[.95] md:text-6xl">{title}</h1>
                {children}
            </div>
        </div>
    );
}

export function BackLink({ to = '/shop', children = 'Back' }) {
    return (
        <Link to={to} className="mb-8 inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-stone">
            <ArrowLeft className="size-3" aria-hidden="true" /> {children}
        </Link>
    );
}

// A labelled text input in the design's underline style. `id` ties the label to the input.
export function Field({ id, label, value, onChange, type = 'text', autoComplete, inputMode, maxLength, readOnly = false, required = false }) {
    return (
        <div className="flex flex-col gap-2">
            <label htmlFor={id} className="noore-label">{label}</label>
            <input id={id} type={type} value={value} onChange={onChange} autoComplete={autoComplete} inputMode={inputMode}
                maxLength={maxLength} readOnly={readOnly} required={required} className="noore-input" />
        </div>
    );
}

export function Loading({ children = 'Loading...' }) {
    return <div className="px-5 py-24 text-center text-sm text-stone" role="status">{children}</div>;
}

// One product on a listing: photo at a fixed 4:5 ratio, name, "From" price, sold-out mark.
// A horizontal row of product cards that the shopper swipes or drags through, with arrows on
// larger screens. Used on the home page, where "the collection" is a row rather than a grid.
//
// It is a plain scrolling list, so a touch swipe, a trackpad, Tab through the cards and a
// screen reader all work without any of this code running. The arrows are an extra on top, and
// are hidden when there is nothing to scroll.
export function ProductRail({ children, label = 'Products' }) {
    const rail = useRef(null);
    const [atStart, setAtStart] = useState(true);
    const [atEnd, setAtEnd] = useState(true);

    const measure = () => {
        const node = rail.current;
        if (!node) return;
        const max = node.scrollWidth - node.clientWidth;
        setAtStart(node.scrollLeft <= 1);
        setAtEnd(node.scrollLeft >= max - 1);
    };

    useEffect(() => {
        const node = rail.current;
        if (!node) return undefined;
        measure();
        node.addEventListener('scroll', measure, { passive: true });
        window.addEventListener('resize', measure);
        // Cards arrive with the data, and photos change the width as they load.
        const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
        if (observer) observer.observe(node);
        return () => {
            node.removeEventListener('scroll', measure);
            window.removeEventListener('resize', measure);
            if (observer) observer.disconnect();
        };
    }, [children]);

    // Move by one card, whatever the screen size.
    const nudge = (direction) => {
        const node = rail.current;
        if (!node) return;
        const card = node.firstElementChild;
        const step = card ? card.getBoundingClientRect().width + 16 : node.clientWidth * 0.8;
        node.scrollBy({ left: direction * step, behavior: 'smooth' });
    };

    const arrow = 'flex size-10 items-center justify-center border border-line-strong bg-cream transition-opacity disabled:pointer-events-none disabled:opacity-0';
    const hasOverflow = !(atStart && atEnd);

    return (
        <div className="relative">
            <div
                ref={rail}
                role="region"
                aria-label={label}
                tabIndex={0}
                data-testid="product-rail"
                className="noore-rail -mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-2 md:mx-0 md:px-0"
            >
                {children}
            </div>
            {hasOverflow &&
                <div className="pointer-events-none absolute inset-y-0 left-0 right-0 hidden items-center justify-between md:flex">
                    <button type="button" aria-label="Previous candles" onClick={() => nudge(-1)} disabled={atStart}
                        className={`${arrow} pointer-events-auto -ml-5`} data-testid="rail-prev">
                        <ArrowLeft className="size-4" aria-hidden="true" />
                    </button>
                    <button type="button" aria-label="More candles" onClick={() => nudge(1)} disabled={atEnd}
                        className={`${arrow} pointer-events-auto -mr-5`} data-testid="rail-next">
                        <ArrowRight className="size-4" aria-hidden="true" />
                    </button>
                </div>
            }
        </div>
    );
}


export function ProductCard({ product, inRail = false }) {
    const variants = product.variants || [];
    const soldOut = product.available_qty === 0;
    const strike = variants.find((variant) => variant.is_default)?.strikethrough;
    return (
        <article className={`group ${inRail ? 'w-[72vw] shrink-0 snap-start sm:w-[46vw] lg:w-[23rem]' : ''}`} data-testid="product-card">
            <Link to={`/detail/${product.slug}`} className="relative block overflow-hidden bg-oat">
                <div className="aspect-[4/5]">
                    {<Photo src={product.image} alt={product.title} width={SIZES.card} className="size-full object-cover transition-transform duration-700 group-hover:scale-105" />}
                </div>
                {soldOut && <span className="absolute left-3 top-3 bg-cream px-2 py-1 text-[9px] uppercase tracking-widest">Sold out</span>}
            </Link>
            <div className="flex items-start justify-between gap-3 pt-4">
                <h3 className="font-serif text-xl"><Link to={`/detail/${product.slug}`}>{product.title}</Link></h3>
                <p className="shrink-0 text-sm">
                    {variants.length > 1 ? <span className="text-stone">From </span> : null}
                    {product.price_from_paise != null ? formatINR(product.price_from_paise) : ''}
                    {variants.length <= 1 && strike && <s className="ml-2 text-stone">{formatINR(strike.compare_at_paise)}</s>}
                </p>
            </div>
            <Link to={`/detail/${product.slug}`} className="noore-btn-outline mt-4 w-full">{variants.length > 1 ? 'Choose a size' : 'View candle'}</Link>
        </article>
    );
}