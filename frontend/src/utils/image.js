// Product photo addresses.
//
// Photos uploaded to Cloudinary are stored at full size: a 4 MB phone picture would be sent to
// every shopper as-is, which is the slowest thing on a page. Cloudinary can resize and convert
// on delivery, so asking for the size actually needed turns megabytes into tens of kilobytes.
// It is done by putting instructions into the address:
//
//   https://res.cloudinary.com/demo/image/upload/v1/noore/candle.jpg
//   https://res.cloudinary.com/demo/image/upload/f_auto,q_auto,c_limit,w_600/v1/noore/candle.jpg
//
//   f_auto   send WebP or AVIF to browsers that take it
//   q_auto   pick a sensible quality
//   c_limit  never enlarge a small picture
//   w_600    at most 600 pixels wide
//
// Anything not stored on Cloudinary (a local development upload, an address already carrying
// instructions) is handed back untouched, so nothing breaks when Cloudinary is not configured.

const UPLOAD = '/image/upload/';

// Widths actually used by the pages, so the browser caches a handful of sizes, not dozens.
export const SIZES = {
    thumb: 160,    // cart line, order line
    card: 600,     // listing card
    detail: 1200,  // product page main photo
    hero: 1600,    // home page hero
};

export const imageUrl = (src, width = SIZES.card) => {
    if (typeof src !== 'string' || !src) return src;
    if (!src.includes('res.cloudinary.com') || !src.includes(UPLOAD)) return src;

    const [before, after] = src.split(UPLOAD);
    // Already transformed (someone put their own instructions in): leave it alone.
    if (/^[a-z]+_[^/]*\//.test(after)) return src;

    return `${before}${UPLOAD}f_auto,q_auto,c_limit,w_${Math.round(width)}/${after}`;
};