import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

import { formatINR } from '../../utils/money';

// Small shared pieces of the Noore storefront design.

// A product photo. If the file is missing or fails to load, nothing is drawn (the coloured
// block behind it remains), never the browser's broken-image icon.
export function Photo({ src, alt = '', className = '', ...rest }) {
    const [failed, setFailed] = useState(false);
    useEffect(() => { setFailed(false); }, [src]);
    if (!src || failed) return null;
    return <img src={src} alt={alt} className={className} onError={() => setFailed(true)} {...rest} />;
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
export function ProductCard({ product }) {
    const variants = product.variants || [];
    const soldOut = product.available_qty === 0;
    const strike = variants.find((variant) => variant.is_default)?.strikethrough;
    return (
        <article className="group" data-testid="product-card">
            <Link to={`/detail/${product.slug}`} className="relative block overflow-hidden bg-oat">
                <div className="aspect-[4/5]">
                    {<Photo src={product.image} alt={product.title} loading="lazy" className="size-full object-cover transition-transform duration-700 group-hover:scale-105" />}
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
