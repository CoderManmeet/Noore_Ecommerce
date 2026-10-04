import { useContext, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import moment from 'moment';
import Swal from 'sweetalert2';

import apiInstance from '../../utils/axios';
import Addon from '../plugin/Addon';
import GetCurrentAddress from '../plugin/UserCountry';
import UserData from '../plugin/UserData';
import CartID from '../plugin/cartID';
import { addToCart } from '../plugin/addToCart';
import { addToWishlist } from '../plugin/addToWishlist';
import { CartContext } from '../plugin/Context';
import { Heart } from 'lucide-react';
import { formatINR } from '../../utils/money';
import { BackLink, Loading, Photo } from '../ui/noore';
import { SIZES } from '../../utils/image';
import usePageTitle from '../../utils/usePageTitle';

// Product page.
//
// A product is sold as one or more VARIANTS (for a candle: its sizes). Each variant has its
// own price, MRP, SKU and stock, and describes itself with `options`, e.g. {"Size": "200 g"}.
// The picker below is built from those options alone: one row of buttons per option name, so
// adding a second option (say "Colour") needs data only, no code here.
//
// Everything shown about price and stock comes from the server for the selected variant:
//   * price            variant.price_paise
//   * struck price     variant.strikethrough (null when no reduction may be claimed)
//   * stock            variant.stock = { state, label, left } from the stock ledger
// Nothing here invents urgency: there are no timers, and "Only N left" appears only when the
// server says N really is what is left.

const optionKeysOf = (variants) => {
    const keys = [];
    variants.forEach((variant) => {
        Object.keys(variant.options || {}).forEach((key) => {
            if (!keys.includes(key)) keys.push(key);
        });
    });
    return keys;
};

const matches = (variant, selection, keys) => keys.every((key) => (variant.options || {})[key] === selection[key]);

const STOCK_CLASS = { in_stock: 'text-success', low_stock: 'text-clay', sold_out: 'text-danger' };

function ProductDetail() {
    const [product, setProduct] = useState(null)
    usePageTitle(product?.title);
    const [productImage, setProductImage] = useState('')
    const [selection, setSelection] = useState({})
    const [qtyValue, setQtyValue] = useState(1)
    const [adding, setAdding] = useState(false)
    const [wishlisted, setWishlisted] = useState(false)
    const [, setCartCount] = useContext(CartContext);

    const [createReview, setCreateReview] = useState({ review: "", rating: 1 })
    const [reviews, setReviews] = useState([]);
    // { eligible, reason }: reason is "login", "not_purchased" or "already_reviewed"
    const [reviewAccess, setReviewAccess] = useState(null);
    const [reviewSent, setReviewSent] = useState("");

    const axios = apiInstance
    const params = useParams()
    const addon = Addon()
    const currentAddress = GetCurrentAddress()
    const userData = UserData()
    const cart_id = CartID()

    const loadProduct = () => axios.get(`products/${params.slug}/`).then((res) => {
        setProduct(res.data);
        return res.data;
    });

    useEffect(() => {
        setProduct(null);
        loadProduct().then((data) => {
            setProductImage(data.image);
            const all = data.variants || [];
            const initial = all.find((v) => v.is_default) || all[0];
            setSelection(initial ? { ...(initial.options || {}) } : {});
            axios.get(`reviews/${data.id}/`).then((res) => setReviews(res.data));
            axios.get(`review-eligibility/${data.id}/`).then((res) => setReviewAccess(res.data));
        }).catch((error) => console.error('Could not load the product:', error));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [params.slug]);

    const variants = useMemo(() => product?.variants || [], [product]);
    const optionKeys = useMemo(() => optionKeysOf(variants), [variants]);

    // The variant the shopper is looking at. A product with no options has just its default.
    const selectedVariant = useMemo(() => {
        if (variants.length === 0) return null;
        if (optionKeys.length === 0) return variants.find((v) => v.is_default) || variants[0];
        return variants.find((v) => matches(v, selection, optionKeys)) || null;
    }, [variants, optionKeys, selection]);

    // The variant a button for (key = value) leads to: the current selection with that one
    // option changed, or failing that any variant carrying that value.
    const variantFor = (key, value) => {
        const wanted = { ...selection, [key]: value };
        return variants.find((v) => matches(v, wanted, optionKeys)) || variants.find((v) => (v.options || {})[key] === value) || null;
    };

    const chooseOption = (key, value) => {
        const target = variantFor(key, value);
        if (target) setSelection({ ...(target.options || {}) });
    };

    const stock = selectedVariant?.stock;
    const soldOut = !selectedVariant || stock?.state === 'sold_out';
    const strike = selectedVariant?.strikethrough;

    const handleAddToCart = async () => {
        if (soldOut) return;
        const qty = parseInt(qtyValue, 10);
        if (!Number.isInteger(qty) || qty < 1) {
            Swal.fire({ icon: 'warning', title: 'Quantity must be at least 1' });
            return;
        }
        setAdding(true);
        try {
            const added = await addToCart(product.id, userData?.user_id, qty, null, null, currentAddress?.country, null, null, cart_id, null, selectedVariant.id);
            if (added) {
                const url = userData?.user_id ? `cart-list/${cart_id}/${userData?.user_id}/` : `cart-list/${cart_id}/`;
                const response = await axios.get(url);
                setCartCount(response.data.length);
            }
            // Either way the stock figure may have moved (our own hold, or someone else's).
            await loadProduct();
        } finally {
            setAdding(false);
        }
    };

    const handleAddToWishlist = () => {
        if (userData) {
            addToWishlist(product.id, userData?.user_id)
            setWishlisted(true)
        }
    }

    const handleReviewChange = (event) => {
        setCreateReview({ ...createReview, [event.target.name]: event.target.value })
    }

    const handleReviewSubmit = (e) => {
        e.preventDefault()

        const formdata = new FormData()
        formdata.append('user_id', userData?.user_id)
        formdata.append('product_id', product?.id)
        formdata.append('rating', createReview.rating)
        formdata.append('review', createReview.review)

        axios.post(`create-review/`, formdata).then((res) => {
            // A new review is checked by the store before it is shown, so it will not appear yet.
            setReviewSent(res.data.message)
            setReviewAccess({ eligible: false, reason: "already_reviewed" })
            setCreateReview({ review: "", rating: createReview.rating })
        }).catch((error) => {
            const status = error?.response?.status;
            Swal.fire({
                icon: "error",
                title: status === 401 ? "Please sign in to write a review"
                    : status === 403 ? "Only customers who have received this product can review it"
                        : "Could not save your review",
            })
        })
    }

    if (product === null) {
        return (
            <main><Loading /></main>
        )
    }

    const gallery = product.gallery || [];
    const specifications = product.specification || [];
    const rating = product.product_rating;
    const fullStars = rating ? Math.round(rating) : 0;
    const images = [product.image, ...gallery.map((g) => g.image)].filter((src, index, all) => src && all.indexOf(src) === index);

    return (
        <main>
            <div className="mx-auto max-w-[1440px] px-5 py-10 md:px-10 md:py-16">
                <BackLink to="/shop">All candles</BackLink>
                <div className="grid gap-10 md:grid-cols-2 md:gap-16">
                    {/* Gallery: one large photo, thumbnails beneath */}
                    <div>
                        <div className="aspect-[4/5] overflow-hidden bg-oat">
                            {productImage && <Photo src={productImage} alt={product.title} width={SIZES.detail} className="size-full object-cover" />}
                        </div>
                        {images.length > 1 &&
                            <div className="mt-3 grid grid-cols-5 gap-3">
                                {images.map((src, index) => (
                                    <button key={src} type="button" onClick={() => setProductImage(src)} aria-label={`Show photo ${index + 1}`}
                                        className={`aspect-square overflow-hidden border ${productImage === src ? 'border-ink' : 'border-transparent'}`}>
                                        <Photo src={src} alt="" width={SIZES.thumb} className="size-full object-cover" />
                                    </button>
                                ))}
                            </div>
                        }
                    </div>

                    <div>
                        <h1 className="font-serif text-4xl leading-tight md:text-6xl" data-testid="product-title">{product.title}</h1>
                        <p className="mt-3 flex items-center gap-2 text-xs text-stone">
                            {rating
                                ? <><span aria-hidden="true" className="text-clay">{'★'.repeat(fullStars)}{'☆'.repeat(5 - fullStars)}</span><span>{Number(rating).toFixed(1)} out of 5 · {product.rating_count} {product.rating_count === 1 ? 'review' : 'reviews'}</span></>
                                : <span>No reviews yet</span>
                            }
                        </p>

                        {/* Price for the selected variant */}
                        <p className="mt-7 flex flex-wrap items-baseline gap-3 font-serif text-3xl" data-testid="product-price-block">
                            <span data-testid="product-price">{selectedVariant ? formatINR(selectedVariant.price_paise) : ''}</span>
                            {strike && <s className="font-sans text-base text-stone" data-testid="product-mrp">{formatINR(strike.compare_at_paise)}</s>}
                            {strike && strike.percent_off > 0 && <span className="font-sans text-xs uppercase tracking-[0.15em] text-clay" data-testid="product-percent-off">{strike.percent_off}% off</span>}
                        </p>
                        <p className="mt-1 text-xs text-stone">Inclusive of all taxes</p>

                        {product.description && <p className="mt-7 whitespace-pre-line text-sm leading-7 text-stone">{product.description}</p>}

                        {/* Variant picker: one row of buttons per option name */}
                        {optionKeys.map((key) => {
                            const values = [];
                            variants.forEach((v) => {
                                const value = (v.options || {})[key];
                                if (value !== undefined && !values.includes(value)) values.push(value);
                            });
                            return (
                                <div className="mt-8" key={key} data-testid={`option-${key}`}>
                                    <p className="noore-label mb-3">{key}: <span className="text-stone">{selection[key]}</span></p>
                                    <div className="flex flex-wrap gap-2" role="group" aria-label={key}>
                                        {values.map((value) => {
                                            const target = variantFor(key, value);
                                            const isSelected = selection[key] === value;
                                            const isSoldOut = target?.stock?.state === 'sold_out';
                                            return (
                                                <button key={value} type="button" onClick={() => chooseOption(key, value)} aria-pressed={isSelected}
                                                    title={isSoldOut ? 'Sold out' : undefined}
                                                    className={`min-h-11 border px-4 text-xs ${isSelected ? 'border-ink bg-ink text-white' : 'border-line-strong'} ${isSoldOut ? 'line-through opacity-60' : ''}`}>
                                                    {value}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}

                        {/* Honest stock status for the selected variant */}
                        {stock &&
                            <p className="mt-6 text-xs">
                                <span className={`uppercase tracking-[0.15em] ${STOCK_CLASS[stock.state] || ''}`} data-testid="stock-status">{stock.label}</span>
                                {selectedVariant?.sku && <span className="ml-4 text-stone">SKU {selectedVariant.sku}</span>}
                            </p>
                        }

                        <div className="mt-6 flex flex-wrap items-end gap-3">
                            <div className="flex flex-col gap-2">
                                <label htmlFor="productQuantity" className="noore-label">Quantity</label>
                                <input type="number" id="productQuantity" min={1} value={qtyValue} disabled={soldOut}
                                    onChange={(event) => setQtyValue(event.target.value)}
                                    className="h-12 w-24 border border-line-strong bg-transparent px-3 text-sm outline-none focus:border-clay" />
                            </div>
                            <button onClick={handleAddToCart} type="button" disabled={soldOut || adding} className="noore-btn flex-1" data-testid="add-to-cart">
                                {adding ? 'Adding...' : soldOut ? 'Sold out' : 'Add to bag'}
                            </button>
                            {userData &&
                                <button onClick={handleAddToWishlist} type="button" aria-label="Save to wishlist" aria-pressed={wishlisted}
                                    className={`flex size-12 items-center justify-center border border-line-strong ${wishlisted ? 'bg-clay text-white' : ''}`}>
                                    <Heart className="size-4" aria-hidden="true" />
                                </button>
                            }
                        </div>

                        {addon?.shipping_flat_paise != null &&
                            <p className="mt-5 text-xs text-stone" data-testid="shipping-line">
                                Shipping {formatINR(addon.shipping_flat_paise)}. Free on orders of {formatINR(addon.free_shipping_threshold_paise)} or more.{' '}
                                <Link to="/policy/shipping" className="noore-link">Shipping policy</Link>
                            </p>
                        }

                        {(selectedVariant?.weight_grams || specifications.length > 0) &&
                            <dl className="mt-10 border-t border-line text-sm">
                                {selectedVariant?.weight_grams &&
                                    <div className="flex justify-between gap-6 border-b border-line py-3"><dt className="noore-label">Net weight</dt><dd className="text-stone">{selectedVariant.weight_grams} g</dd></div>
                                }
                                {specifications.map((s, index) => (
                                    <div className="flex justify-between gap-6 border-b border-line py-3" key={index}><dt className="noore-label">{s.title}</dt><dd className="text-right text-stone">{s.content}</dd></div>
                                ))}
                            </dl>
                        }
                    </div>
                </div>

                {/* Reviews: approved reviews from verified buyers */}
                <section className="mt-20 border-t border-line pt-12" id="reviews">
                    <p className="noore-eyebrow mb-4">Reviews</p>
                    <div className="grid gap-12 md:grid-cols-2">
                        <div>
                            {reviews.length > 0
                                ? <div className="flex flex-col gap-8" data-testid="review-list">
                                    {reviews.map((review, index) => (
                                        <article key={index}>
                                            <p className="text-clay" aria-label={`${review.rating} out of 5`}>{'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}</p>
                                            <p className="mt-2 text-sm leading-7">{review.review}</p>
                                            <p className="mt-2 text-xs text-stone">{review.profile?.full_name || 'Customer'} · verified buyer · {moment(review.date).format("DD MMM YYYY")}</p>
                                        </article>
                                    ))}
                                </div>
                                : <p className="font-serif text-2xl">No reviews yet.</p>
                            }
                        </div>
                        <div className="h-fit bg-sand p-6 md:p-8" data-testid="review-box">
                            <h2 className="font-serif text-2xl">Write a review</h2>
                            {reviewSent && <p className="mt-4 text-sm text-success">{reviewSent}</p>}
                            {!reviewSent && reviewAccess?.reason === "login" &&
                                <p className="mt-4 text-sm leading-7 text-stone">Reviews are from verified buyers. <Link to="/login" className="noore-link">Sign in</Link> to review a product you have received. Bought as a guest? Use the "create an account" link on your order page first.</p>
                            }
                            {!reviewSent && reviewAccess?.reason === "not_purchased" &&
                                <p className="mt-4 text-sm leading-7 text-stone">Only customers who have received this product can review it.</p>
                            }
                            {!reviewSent && reviewAccess?.reason === "already_reviewed" &&
                                <p className="mt-4 text-sm leading-7 text-stone">You have already reviewed this product. Thank you.</p>
                            }
                            {reviewAccess?.eligible &&
                                <form method='POST' onSubmit={handleReviewSubmit} className="mt-5 flex flex-col gap-5">
                                    <div className="flex flex-col gap-2">
                                        <label htmlFor="reviewRating" className="noore-label">Rating</label>
                                        <select onChange={handleReviewChange} name="rating" value={createReview.rating} id="reviewRating" className="noore-input">
                                            <option value="1">★ (1)</option>
                                            <option value="2">★★ (2)</option>
                                            <option value="3">★★★ (3)</option>
                                            <option value="4">★★★★ (4)</option>
                                            <option value="5">★★★★★ (5)</option>
                                        </select>
                                    </div>
                                    <div className="flex flex-col gap-2">
                                        <label htmlFor="reviewText" className="noore-label">Your review</label>
                                        <textarea id="reviewText" rows={4} onChange={handleReviewChange} name="review" value={createReview.review}
                                            className="w-full border border-line-strong bg-transparent p-3 text-sm outline-none focus:border-clay" />
                                    </div>
                                    <button type="submit" className="noore-btn w-fit">Submit review</button>
                                </form>
                            }
                        </div>
                    </div>
                </section>
            </div>
        </main>
    )
}

export default ProductDetail