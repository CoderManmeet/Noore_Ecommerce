import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import './theme/noore.css'
import './theme/admin.css'
import { warmStart } from './utils/apiCache'

// The catalogue request goes out here, before React is even asked to render. On a free host the
// backend may be asleep and take a long time to answer the first request of the day; starting it
// at the very first line of our JavaScript means that wait overlaps rendering instead of
// beginning after it. The first page that needs this data reuses the answer. See utils/apiCache.js.
warmStart()

// Hey buddy, welcome to the root component :)
ReactDOM.createRoot(document.getElementById('root')).render(
    <App />
)