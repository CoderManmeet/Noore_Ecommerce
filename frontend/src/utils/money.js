// Money helpers for the storefront.
//
// The API sends money as INTEGER PAISE (Rs 499 = 49900). Never do arithmetic on rupee
// floats in the browser: add, compare and format paise.
//
//   formatINR(49900)        -> "₹499"
//   formatINR(157849)       -> "₹1,578.49"
//   formatINR(12345600)     -> "₹1,23,456"      (Indian digit grouping)
//   formatRupees("499.00")  -> "₹499"           (for the few legacy Decimal-rupee strings)

const RUPEE = '\u20B9';

const groupIndian = (digits) => {
    // 1234567 -> 12,34,567 : last three digits, then groups of two.
    if (digits.length <= 3) return digits;
    const last3 = digits.slice(-3);
    const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
    return `${rest},${last3}`;
};

// Integer paise -> display string. Returns '' for null/undefined/non-numeric input so a
// value that has not loaded yet renders as nothing rather than "₹NaN".
export const formatINR = (paise) => {
    if (paise === null || paise === undefined || paise === '') return '';
    const value = typeof paise === 'string' ? Number(paise) : paise;
    if (!Number.isFinite(value)) return '';
    const whole = Math.round(value);
    const sign = whole < 0 ? '-' : '';
    const abs = Math.abs(whole);
    const rupees = Math.floor(abs / 100);
    const rest = abs % 100;
    const fraction = rest === 0 ? '' : `.${String(rest).padStart(2, '0')}`;
    return `${sign}${RUPEE}${groupIndian(String(rupees))}${fraction}`;
};

// Decimal-rupee string or number ("1355.54", "499", 499) -> integer paise, without going
// through binary floating point for strings.
export const rupeesToPaise = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const text = String(value).trim();
    const match = /^(-?)(\d+)(?:\.(\d{1,}))?$/.exec(text);
    if (!match) return null;
    const [, sign, whole, fraction = ''] = match;
    const padded = `${fraction}000`;
    let paise = Number(whole) * 100 + Number(padded.slice(0, 2));
    if (Number(padded[2]) >= 5) paise += 1; // round half up on the third decimal
    return sign === '-' ? -paise : paise;
};

// Legacy Decimal-rupee value -> display string.
export const formatRupees = (value) => formatINR(rupeesToPaise(value));

// Whole-number percentage a price is below its MRP, rounded DOWN so a discount is never
// overstated. Returns 0 when there is no genuine reduction.
export const percentOff = (pricePaise, mrpPaise) => {
    if (!Number.isFinite(pricePaise) || !Number.isFinite(mrpPaise) || mrpPaise <= pricePaise || mrpPaise <= 0) return 0;
    return Math.floor(((mrpPaise - pricePaise) * 100) / mrpPaise);
};
