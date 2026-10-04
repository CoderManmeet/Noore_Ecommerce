import { useEffect } from 'react';

import { STORE_NAME } from './constants';

// Sets the browser tab title for a page: "Cart | Noore Candles". Pass nothing (or an empty
// string) while the real title is still loading and the title is left as it is.
// Product pages also get their title from the server for link previews (backend core/seo.py);
// this keeps it right when the shopper moves between pages inside the app.
export default function usePageTitle(title) {
    useEffect(() => {
        if (title) {
            document.title = `${title} | ${STORE_NAME}`;
        }
    }, [title]);
}
