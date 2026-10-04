import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { register } from '../../utils/auth';
import { useAuthStore } from '../../store/auth';
import usePageTitle from '../../utils/usePageTitle';
import { Field } from '../ui/noore';

// Turn the server's validation answer ({field: [messages]}) into readable lines.
const describe = (problem) => {
    if (!problem) return [];
    if (typeof problem === 'string') return [problem];
    return Object.values(problem).flat().map((message) => String(message));
};

function Register() {
    const [fullname, setFullname] = useState('');
    const [email, setEmail] = useState('');
    const [phone, setPhone] = useState('');
    const [password, setPassword] = useState('');
    const [password2, setPassword2] = useState('');
    const [errors, setErrors] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const isLoggedIn = useAuthStore((state) => state.isLoggedIn);
    const navigate = useNavigate();

    usePageTitle('Create an account');

    useEffect(() => {
        if (isLoggedIn()) {
            navigate('/');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setErrors([]);
        setIsLoading(true);

        const { error } = await register(fullname, email, phone, password, password2);
        if (error) {
            setErrors(describe(error));
        } else {
            navigate('/');
        }
        setIsLoading(false);
    };

    return (
        <main className="mx-auto max-w-md px-5 py-16 md:py-24" data-testid="register-page">
            <p className="noore-eyebrow mb-4">Join us</p>
            <h1 className="font-serif text-5xl">Create an account.</h1>
            <form onSubmit={handleSubmit} className="mt-10 flex flex-col gap-6">
                <Field id="registerName" label="Full name" value={fullname} onChange={(e) => setFullname(e.target.value)} autoComplete="name" required />
                <Field id="registerEmail" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
                <Field id="registerPhone" label="Mobile number" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" required />
                <Field id="registerPassword" label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
                <Field id="registerPassword2" label="Confirm password" type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} autoComplete="new-password" required />
                {errors.length > 0 &&
                    <ul className="flex flex-col gap-1 text-sm text-danger" role="alert">
                        {errors.map((message, index) => <li key={index}>{message}</li>)}
                    </ul>
                }
                <button className="noore-btn w-full" type="submit" disabled={isLoading}>{isLoading ? 'Please wait...' : 'Create account'}</button>
            </form>
            <p className="mt-8 text-xs text-stone">Already have an account? <Link to="/login" className="noore-link text-ink">Sign in</Link></p>
        </main>
    );
}

export default Register;
