import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import { logout } from '../../utils/auth';
import usePageTitle from '../../utils/usePageTitle';

// Signs the customer out as soon as the page opens.
const Logout = () => {
    usePageTitle('Signed out');

    useEffect(() => {
        logout();
    }, []);

    return (
        <main className="mx-auto max-w-md px-5 py-16 text-center md:py-24" data-testid="logout-page">
            <p className="noore-eyebrow mb-4">See you soon</p>
            <h1 className="font-serif text-5xl">You have been signed out.</h1>
            <p className="mt-6 text-sm text-stone">Thank you for visiting.</p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
                <Link to="/login" className="noore-btn">Sign in</Link>
                <Link to="/shop" className="noore-btn-outline min-h-12">Browse candles</Link>
            </div>
        </main>
    );
};

export default Logout;
