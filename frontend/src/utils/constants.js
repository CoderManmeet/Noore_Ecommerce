// Values can be overridden per environment with Vite env vars (see frontend/.env.example).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1/';
export const PAYPAL_CLIENT_ID = import.meta.env.VITE_PAYPAL_CLIENT_ID || 'test'
export const SERVER_URL = import.meta.env.VITE_SERVER_URL || 'http://127.0.0.1:8000/'

// Customer support contact shown in the footer, on the contact page and at checkout.
// PLACEHOLDERS: set VITE_SUPPORT_EMAIL and VITE_WHATSAPP_NUMBER in frontend/.env.local.
export const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL || 'support@example.com'
// Digits only, with country code and no "+", as wa.me expects (e.g. 919876543210).
export const WHATSAPP_NUMBER = (import.meta.env.VITE_WHATSAPP_NUMBER || '910000000000').replace(/\D/g, '')
export const WHATSAPP_LINK = `https://wa.me/${WHATSAPP_NUMBER}`
export const STORE_NAME = import.meta.env.VITE_STORE_NAME || 'Noore Candles'
