import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import apiInstance from '../../utils/axios';
import usePageTitle from '../../utils/usePageTitle';
import { Loading, PageIntro, ProductCard } from '../ui/noore';

// The shop: every candle, with search (?query=) and sorting. Also serves /search.
const SORTS = {
    featured: { label: 'Featured', compare: null },
    low: { label: 'Price: low to high', compare: (a, b) => (a.price_from_paise ?? 0) - (b.price_from_paise ?? 0) },
    high: { label: 'Price: high to low', compare: (a, b) => (b.price_from_paise ?? 0) - (a.price_from_paise ?? 0) },
};

function Shop() {
    const [searchParams] = useSearchParams();
    const query = (searchParams.get('query') || '').trim();
    const [products, setProducts] = useState(null)
    const [sort, setSort] = useState('featured')

    usePageTitle(query ? `Search: ${query}` : 'Shop candles');

    useEffect(() => {
        setProducts(null)
        const request = query ? apiInstance.get('search/', { params: { query } }) : apiInstance.get('products/')
        request.then((res) => setProducts(res.data)).catch(() => setProducts([]))
    }, [query])

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
                    <span data-testid="shop-count">{products === null ? '' : `${visible.length} ${visible.length === 1 ? 'candle' : 'candles'}`}</span>
                    <label className="flex items-center gap-2">
                        <span>Sort</span>
                        <select value={sort} onChange={(event) => setSort(event.target.value)} className="border-b border-line-strong bg-transparent py-2 text-[10px] uppercase tracking-[0.15em] outline-none">
                            {Object.entries(SORTS).map(([value, { label }]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                    </label>
                </div>
                {products === null && <Loading />}
                {products !== null && visible.length === 0 && <p className="py-20 text-center font-serif text-2xl">No candles found.</p>}
                <div className="grid gap-x-4 gap-y-12 sm:grid-cols-2 lg:grid-cols-4" data-testid="shop-products">
                    {visible.map((product) => <ProductCard key={product.id} product={product} />)}
                </div>
            </div>
        </main>
    )
}

export default Shop
