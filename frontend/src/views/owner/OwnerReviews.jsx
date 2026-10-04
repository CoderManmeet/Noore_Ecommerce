import { useEffect, useState } from 'react';
import moment from 'moment';

import apiInstance from '../../utils/axios';
import Sidebar from '../vendor/Sidebar';

// Review moderation queue. New reviews (from verified buyers only) wait here until the owner
// approves them; only approved reviews are public or count towards a product's rating.
function OwnerReviews() {
    const [status, setStatus] = useState('PENDING')
    const [reviews, setReviews] = useState(null)
    const [busyId, setBusyId] = useState(null)

    const load = (wanted) => {
        setReviews(null)
        apiInstance.get('owner/reviews/', { params: { status: wanted } }).then((res) => setReviews(res.data))
            .catch(() => setReviews([]))
    }

    useEffect(() => { load(status) }, [status])

    const moderate = async (id, action) => {
        setBusyId(id)
        try {
            await apiInstance.post(`owner/reviews/${id}/moderate/`, { action })
            load(status)
        } finally {
            setBusyId(null)
        }
    }

    return (
        <div className="container-fluid" id="main">
            <div className="row row-offcanvas row-offcanvas-left h-100">
                <Sidebar />
                <div className="col-md-9 col-lg-10 main mt-4" data-testid="owner-reviews">
                    <h4><i className="bi bi-star" /> Review moderation</h4>
                    <div className="alert alert-info">
                        Approve genuine reviews, including critical ones. <b>Reject only abuse and spam, not low ratings.</b>
                    </div>
                    <div className="btn-group mb-3">
                        {['PENDING', 'APPROVED', 'REJECTED'].map((value) => (
                            <button key={value} className={`btn ${status === value ? 'btn-dark' : 'btn-outline-dark'}`} onClick={() => setStatus(value)}>
                                {value.charAt(0) + value.slice(1).toLowerCase()}
                            </button>
                        ))}
                    </div>
                    {reviews === null && <p><i className='fas fa-spinner fa-spin'></i> Loading...</p>}
                    {reviews !== null && reviews.length === 0 && <p>Nothing here.</p>}
                    {(reviews || []).map((review) => (
                        <div className="card mb-3" key={review.id} data-testid="owner-review">
                            <div className="card-body">
                                <h6 className="card-title mb-1">{review.product?.title} · {'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}</h6>
                                <p className="text-muted mb-2"><small>{review.profile?.full_name || 'Customer'} · {moment(review.date).format('DD MMM YYYY')} · verified buyer</small></p>
                                <p className="card-text">{review.review}</p>
                                {review.status !== 'APPROVED' &&
                                    <button className="btn btn-success btn-sm me-2" disabled={busyId === review.id} onClick={() => moderate(review.id, 'approve')}>Approve</button>
                                }
                                {review.status !== 'REJECTED' &&
                                    <button className="btn btn-outline-danger btn-sm" disabled={busyId === review.id} onClick={() => moderate(review.id, 'reject')}>Reject (abuse or spam)</button>
                                }
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default OwnerReviews
