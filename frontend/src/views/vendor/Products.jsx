import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom';

import apiInstance from '../../utils/axios';
import UserData from '../plugin/UserData';
import Sidebar from './Sidebar';
import { deleteProduct, setProductStatus } from '../plugin/DeleteProduct';
import { formatRupees } from '../../utils/money';

function Products() {
    const [products, setProducts] = useState([])

    const axios = apiInstance
    const userData = UserData()

    
    const fetchData = async () => {
        try {
            const response = await axios.get(`vendor/products/${userData?.vendor_id}/`)
            setProducts(response.data);
        } catch (error) {
            console.error('Error fetching data:', error);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleDeleteProduct = async (product) => {
        const changed = await deleteProduct(userData?.vendor_id, product.pid, `"${product.title}"`)
        if (changed) await fetchData();
    }

    // Hide a product from the shop, or put it back. Hiding is the reversible alternative to
    // deleting one that already has orders or stock history.
    const handleToggleVisibility = async (product) => {
        const target = product.status === 'published' ? 'disabled' : 'published'
        const changed = await setProductStatus(userData?.vendor_id, product.pid, target)
        if (changed) await fetchData();
    }


    const handleFilterProduct = async (param) => {
        try {
            const response = await axios.get(`vendor-product-filter/${userData?.vendor_id}?filter=${param}`)
            setProducts(response.data);

        } catch (error) {
            console.log(error);
        }
    }

    return (
        <div className="container-fluid" id="main" >
            <div className="row row-offcanvas row-offcanvas-left h-100">
                <Sidebar />
                <div className="col-md-9 col-lg-10 main mt-4">
                    <>
                        <h4>
                            <i className="bi bi-grid" /> All Products
                        </h4>
                        <div className="dropdown">
                            <button
                                className="btn btn-secondary dropdown-toggle  mt-3 mb-3 me-2"
                                type="button"
                                id="dropdownMenuButton1"
                                data-bs-toggle="dropdown"
                                aria-expanded="false"
                            >
                                Filter <i className="fas fa-sliders" />
                            </button>
                            <ul className="dropdown-menu" aria-labelledby="dropdownMenuButton1">
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('no-filter')}>
                                        No Filter
                                    </button>
                                </li>
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('published')}>
                                        Status: Published
                                    </button>
                                </li>
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('draft')}>
                                        Status: In Draft
                                    </button>
                                </li>
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('in-review')}>
                                        Status: In-review
                                    </button>
                                </li>
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('disabled')}>
                                        Status: Disabled
                                    </button>
                                </li>

                                <hr />
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('latest')}>
                                        Date: Latest
                                    </button>
                                </li>
                                <li>
                                    <button className="dropdown-item" onClick={() => handleFilterProduct('oldest')}>
                                        Date: Oldest
                                    </button>
                                </li>
                            </ul>
                            <Link to={'/admin-area/product/new/'} className='btn btn-primary'>Add Product</Link>
                        </div>
                    </>
                    <div className="mb-3 mt-2">
                        <table className="table">
                            <thead className="table-dark">
                                <tr>
                                    <th scope="col">#ID</th>
                                    <th scope="col">Name</th>
                                    <th scope="col">Price</th>
                                    <th scope="col">Available</th>
                                    <th scope="col">Orders</th>
                                    <th scope="col">Status</th>
                                    <th scope="col">Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {products?.map((p, index) => (
                                    <tr key={index}>
                                        <th scope="row">#{p.sku}</th>
                                        <td>{p.title}</td>
                                        <td>{formatRupees(p.price)}</td>
                                        <td>{p.available_qty}</td>
                                        <td>{p.order_count}</td>
                                        <td>{p?.status?.toUpperCase()}</td>
                                        <td>
                                            <Link to={`/detail/${p.slug}`} className="btn btn-primary mb-1 me-2"><i className="fas fa-eye" /></Link>
                                            <Link to={`/admin-area/product/update/${p.pid}/`} className="btn btn-success mb-1 me-2"><i className="fas fa-edit" /></Link>
                                            <button type='button' title={p.status === 'published' ? 'Hide from the shop' : 'Show in the shop'}
                                                onClick={() => handleToggleVisibility(p)} className="btn btn-secondary mb-1 me-2">
                                                <i className={p.status === 'published' ? 'fas fa-eye-slash' : 'fas fa-store'} />
                                            </button>
                                            <button type='button' title="Delete" onClick={() => handleDeleteProduct(p)} className="btn btn-danger mb-1 me-2"><i className="fas fa-trash" /></button>
                                        </td>
                                    </tr>
                                ))}

                                {products?.length < 1 &&
                                    <h4 className='p-3 mt-4'>No Products Yet</h4>
                                }

                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default Products