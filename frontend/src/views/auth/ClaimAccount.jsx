import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import apiInstance from '../../utils/axios';
import usePageTitle from '../../utils/usePageTitle';
import { Field } from '../ui/noore';

// Reached from the "create your account" link emailed to the address on a guest order.
// Choosing a password here creates the account for that email and attaches its orders.
function ClaimAccount() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token') || '';

    const [password, setPassword] = useState("")
    const [confirm, setConfirm] = useState("")
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState("")
    const [done, setDone] = useState(null)

    usePageTitle('Create your account');

    const submit = async (event) => {
        event.preventDefault()
        setError("")
        if (password !== confirm) {
            setError("The two passwords do not match.")
            return
        }
        setBusy(true)
        try {
            const response = await apiInstance.post('account/claim/', { token, password })
            setDone(response.data)
        } catch (err) {
            setError(err?.response?.data?.message || 'Something went wrong. Please try again.')
        } finally {
            setBusy(false)
        }
    }

    return (
        <main className="mx-auto max-w-md px-5 py-16 md:py-24" data-testid="claim-account">
            <p className="noore-eyebrow mb-4">Your orders, in one place</p>
            <h1 className="font-serif text-5xl">Create your account.</h1>

            {!token &&
                <p className="mt-8 border border-line bg-sand p-4 text-sm">This link is incomplete. Please open the link from your email again.</p>
            }

            {done &&
                <div className="mt-8 border border-line bg-sand p-6" data-testid="claim-done">
                    <p className="text-sm leading-7">{done.message}</p>
                    <Link to="/login" className="noore-btn mt-5">Sign in</Link>
                </div>
            }

            {token && !done &&
                <form onSubmit={submit} className="mt-10 flex flex-col gap-6">
                    <Field id="claimPassword" label="Choose a password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
                    <Field id="claimConfirm" label="Type it again" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
                    {error && <p className="text-sm text-danger" role="alert" data-testid="claim-error">{error}</p>}
                    <button type="submit" className="noore-btn w-full" disabled={busy}>{busy ? 'Please wait...' : 'Create my account'}</button>
                </form>
            }
        </main>
    )
}

export default ClaimAccount
