import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import usePageTitle from '../../utils/usePageTitle';
import { GridSkeleton, PageIntro, ProductCard, WakingNotice } from '../ui/noore';
import { useCachedApi } from '../../utils/apiCache';

// The shop: every candle, with search (?query=) and sorting. Also serves /search.
const SORTS = {
    featured: { label: 'Featured', compare: null },
    low: { label: 'Price: low to high', compare: (a, b) => (a.price_from_paise ?? 0) - (b.price_from_paise ?? 0) },
    high: { label: 'Price: high to low', compare: (a, b) => (b.price_from_paise ?? 0) - (a.price_from_paise ?? 0) },
};

function Shop() {
    const [searchParams] = useSearchParams();
    const query = (searchParams.get('query') || '').trim();
    const [sort, setSort] = useState('featured')

    usePageTitle(query ? `Search: ${query}` : 'Shop candles');

    // Without a search this is the same request the home page made, so it is already cached and
    // the grid appears at once. A search always goes to the server. See utils/apiCache.js.
    const { data: products, loading, waking, failed } = useCachedApi(
        query ? 'search/' : 'products/',
        query ? { params: { query } } : undefined,
    )

    const visible = useMemo(() => {
        const list = [...(products || [])];
        const compare = SORTS[sort].compare;
        return compare ? list.sort(compare) : list;
    }, [products, sort])

    return (
        <main>
            <PageIntro eyebrow={query ? 'Search' : 'The collection'} title={query ? `Results for "${query}".` : 'Choose your atmosphere.'} />
            <div className="mx-auto max-w-[1440px] px-5 py-10 md:px-10 md:py-16">
                <div className="mb-8 flex items-center justify-between gap-4 text-[10px] uppercase tracking-[0.15em] text-stone">
                    <span data-testid="shop-count">{loading ? '' : `${visible.length} ${visible.length === 1 ? 'candle' : 'candles'}`}</span>
                    <label className="flex items-center gap-2">
                        <span>Sort</span>
                        <select value={sort} onChange={(event) => setSort(event.target.value)} className="border-b border-line-strong bg-transparent py-2 text-[10px] uppercase tracking-[0.15em] outline-none">
                            {Object.entries(SORTS).map(([value, { label }]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                    </label>
                </div>
                {loading && <><GridSkeleton /><WakingNotice show={waking} /></>}
                {failed && <p className="py-20 text-center font-serif text-2xl">The candles could not be loaded. Please refresh.</p>}
                {!loading && !failed && visible.length === 0 && <p className="py-20 text-center font-serif text-2xl">No candles found.</p>}
                {!loading &&
                    <div className="grid gap-x-4 gap-y-12 sm:grid-cols-2 lg:grid-cols-4" data-testid="shop-products">
                        {visible.map((product) => <ProductCard key={product.id} product={product} />)}
                    </div>
                }
            </div>
        </main>
    )
}

export default Shop