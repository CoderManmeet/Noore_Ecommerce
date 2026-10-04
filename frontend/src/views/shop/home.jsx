import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

import apiInstance from '../../utils/axios';
import Addon from '../plugin/Addon';
import { formatINR } from '../../utils/money';
import { STORE_NAME } from '../../utils/constants';
import { Loading, Photo, ProductCard } from '../ui/noore';
import { SIZES } from '../../utils/image';

// Home page (Noore design). Every product, price and photo shown here comes from the store's
// own catalogue; nothing is hard-coded.
function Home() {
    const [products, setProducts] = useState(null)
    const addon = Addon()

    useEffect(() => {
        document.title = STORE_NAME;
        apiInstance.get('products/').then((res) => setProducts(res.data)).catch(() => setProducts([]))
    }, [])

    const featured = (products || []).filter((product) => product.featured)
    const hero = featured[0] || (products || [])[0]
    const collection = (featured.length > 0 ? featured : (products || [])).slice(0, 8)

    return (
        <main>
            <section className="overflow-hidden bg-oat">
                <div className="mx-auto grid max-w-[1440px] md:grid-cols-[0.92fr_1.08fr]">
                    <div className="flex min-h-[460px] flex-col justify-center px-6 py-16 md:min-h-[600px] md:px-16 lg:px-24">
                        <p className="mb-6 text-[10px] uppercase tracking-[0.3em] text-stone">The quiet ritual</p>
                        <h1 className="max-w-xl font-serif text-[clamp(3.2rem,8vw,7rem)] leading-[.9] tracking-[-.04em]">Light the<br /><i>beautiful</i><br />moment.</h1>
                        <p className="mt-8 max-w-sm text-sm leading-7 text-stone">Hand-poured scented candles for the spaces where life slows down.</p>
                        <Link to="/shop" className="noore-btn mt-9 w-fit">Explore the collection <ArrowRight className="size-4" aria-hidden="true" /></Link>
                    </div>
                    <div className="relative min-h-[380px] bg-linen md:min-h-[600px]">
                        {hero?.image && <Photo src={hero.image} alt={hero.title} width={SIZES.hero} className="absolute inset-0 size-full object-cover" />}
                        {hero &&
                            <Link to={`/detail/${hero.slug}`} className="absolute bottom-8 right-8 bg-cream/90 px-4 py-3 text-right">
                                <p className="text-[10px] uppercase tracking-[0.25em] text-stone">Featured</p>
                                <p className="mt-1 font-serif text-2xl">{hero.title}</p>
                            </Link>
                        }
                    </div>
                </div>
            </section>

            <section className="border-b border-line bg-sand px-5 py-16 md:px-10 md:py-24">
                <div className="mx-auto max-w-[1440px]">
                    <div className="flex items-end justify-between gap-6">
                        <div>
                            <p className="noore-eyebrow mb-4">Small batch / hand poured</p>
                            <h2 className="font-serif text-4xl md:text-5xl">The collection.</h2>
                        </div>
                        <Link to="/shop" className="noore-link hidden text-xs uppercase tracking-[0.15em] md:block">View all candles</Link>
                    </div>
                    {products === null && <Loading />}
                    {products !== null && collection.length === 0 && <p className="py-20 text-center font-serif text-2xl">The collection is being prepared.</p>}
                    <div className="mt-12 grid gap-x-4 gap-y-12 sm:grid-cols-2 lg:grid-cols-4" data-testid="home-products">
                        {collection.map((product) => <ProductCard key={product.id} product={product} />)}
                    </div>
                    <Link to="/shop" className="noore-btn-outline mt-10 w-full md:hidden">View all candles</Link>
                </div>
            </section>

            <section className="mx-auto grid max-w-[1440px] gap-12 px-5 py-16 md:grid-cols-2 md:items-center md:px-10 md:py-28">
                <div className="relative aspect-square overflow-hidden bg-oat">
                    {(collection[1] || hero)?.image && <Photo src={(collection[1] || hero).image} alt="" width={SIZES.detail} className="size-full object-cover" />}
                </div>
                <div className="max-w-lg md:pl-8">
                    <p className="noore-eyebrow mb-6">A slower way of living</p>
                    <h2 className="font-serif text-5xl leading-[1.05]">Made for the<br /><i>in-between.</i></h2>
                    <p className="mt-8 text-sm leading-7 text-stone">Everyday rituals deserve beautiful attention. Each Noore candle is made by hand, in small batches.</p>
                    <Link to="/about" className="mt-8 inline-flex min-h-11 items-center gap-3 text-xs uppercase tracking-[0.15em]">Our story <ArrowRight className="size-4" aria-hidden="true" /></Link>
                </div>
            </section>

            {addon?.shipping_flat_paise != null &&
                <section className="bg-ink px-5 py-14 text-cream md:px-10">
                    <div className="mx-auto grid max-w-[1440px] gap-8 text-center md:grid-cols-3">
                        <div>
                            <p className="font-serif text-2xl">Shipping {formatINR(addon.shipping_flat_paise)}</p>
                            <p className="mt-2 text-xs text-cream/70">Free on orders of {formatINR(addon.free_shipping_threshold_paise)} or more</p>
                        </div>
                        <div>
                            <p className="font-serif text-2xl">UPI, cards or cash</p>
                            <p className="mt-2 text-xs text-cream/70">Pay online or on delivery, at the same price</p>
                        </div>
                        <div>
                            <p className="font-serif text-2xl">Prices include all taxes</p>
                            <p className="mt-2 text-xs text-cream/70">What you see is what you pay</p>
                        </div>
                    </div>
                </section>
            }
        </main>
    )
}

export default Home