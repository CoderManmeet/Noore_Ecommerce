import { Link } from 'react-router-dom';

import usePageTitle from '../../utils/usePageTitle';

function NotFound() {
    usePageTitle('Page not found');
    return (
        <main className="mx-auto max-w-2xl px-5 py-28 text-center" data-testid="not-found">
            <p className="noore-eyebrow mb-4">Page not found</p>
            <h1 className="font-serif text-5xl">This page has gone quiet.</h1>
            <p className="mt-6 text-sm text-stone">The page you are looking for does not exist or has moved.</p>
            <Link to="/shop" className="noore-btn mt-9">Browse candles</Link>
        </main>
    );
}

export default NotFound;
