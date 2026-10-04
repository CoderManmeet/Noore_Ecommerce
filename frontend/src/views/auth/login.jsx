import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { login } from '../../utils/auth';
import { useAuthStore } from '../../store/auth';
import usePageTitle from '../../utils/usePageTitle';
import { Field } from '../ui/noore';

const Login = () => {
    const navigate = useNavigate();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
    const [isLoading, setIsLoading] = useState(false);

    usePageTitle('Sign in');

    useEffect(() => {
        if (isLoggedIn()) {
            navigate('/');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        const { error: problem } = await login(username, password);
        if (problem) {
            setError(typeof problem === 'string' ? problem : 'Those details were not recognised.');
        } else {
            setUsername('');
            setPassword('');
            navigate('/');
        }
        setIsLoading(false);
    };

    return (
        <main className="mx-auto max-w-md px-5 py-16 md:py-24" data-testid="login-page">
            <p className="noore-eyebrow mb-4">Welcome back</p>
            <h1 className="font-serif text-5xl">Sign in.</h1>
            <form onSubmit={handleLogin} className="mt-10 flex flex-col gap-6">
                <Field id="loginEmail" label="Email" type="email" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="email" required />
                <Field id="loginPassword" label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
                {error && <p className="text-sm text-danger" role="alert" data-testid="login-error">{error}</p>}
                <button className="noore-btn w-full" type="submit" disabled={isLoading}>{isLoading ? 'Please wait...' : 'Sign In'}</button>
            </form>
            <div className="mt-8 flex flex-col gap-3 text-xs text-stone">
                <p>New here? <Link to="/register" className="noore-link text-ink">Create an account</Link></p>
                <p><Link to="/forgot-password" className="noore-link">Forgot your password?</Link></p>
            </div>
        </main>
    );
};

export default Login;
