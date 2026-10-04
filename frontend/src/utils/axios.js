// Shared Axios instance for every API call in the app.
//
// Security: the backend is default-deny. This instance therefore attaches the signed-in
// user's JWT to every request automatically, refreshing it first when it has expired.
// Guests simply send no Authorization header and can still browse, use the cart and check out.
import axios from 'axios';
import Cookies from 'js-cookie';
import jwt_decode from 'jwt-decode';
import { API_BASE_URL } from './constants';

const apiInstance = axios.create({
    baseURL: API_BASE_URL,
    timeout: 100000,
    headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
    },
});

// Endpoints that must never carry a (possibly stale) access token.
const TOKENLESS_PATHS = [
    'user/token/',
    'user/token/refresh/',
    'user/register/',
    'user/password-reset/',
    'user/password-change/',
];

const COOKIE_OPTIONS = { secure: true, sameSite: 'Lax' };

const isExpired = (token) => {
    try {
        // Treat tokens expiring in the next 10 seconds as expired.
        return jwt_decode(token).exp < Date.now() / 1000 + 10;
    } catch (err) {
        return true;
    }
};

// Single in-flight refresh shared by concurrent requests, so a rotated refresh token
// is never used twice (the backend blacklists it after rotation).
let refreshPromise = null;

export const refreshAccessToken = async () => {
    const refresh = Cookies.get('refresh_token');
    if (!refresh || isExpired(refresh)) {
        Cookies.remove('access_token');
        Cookies.remove('refresh_token');
        return null;
    }
    if (!refreshPromise) {
        refreshPromise = axios
            .post(`${API_BASE_URL}user/token/refresh/`, { refresh })
            .then((res) => {
                Cookies.set('access_token', res.data.access, { ...COOKIE_OPTIONS, expires: 1 });
                if (res.data.refresh) {
                    Cookies.set('refresh_token', res.data.refresh, { ...COOKIE_OPTIONS, expires: 7 });
                }
                return res.data.access;
            })
            .catch(() => {
                Cookies.remove('access_token');
                Cookies.remove('refresh_token');
                return null;
            })
            .finally(() => {
                refreshPromise = null;
            });
    }
    return refreshPromise;
};

apiInstance.interceptors.request.use(async (config) => {
    const url = config.url || '';
    if (TOKENLESS_PATHS.some((path) => url.startsWith(path))) {
        return config;
    }

    let access = Cookies.get('access_token');
    if (access && isExpired(access)) {
        access = await refreshAccessToken();
    } else if (!access && Cookies.get('refresh_token')) {
        access = await refreshAccessToken();
    }

    if (access) {
        config.headers.Authorization = `Bearer ${access}`;
    }
    return config;
});

export default apiInstance;
