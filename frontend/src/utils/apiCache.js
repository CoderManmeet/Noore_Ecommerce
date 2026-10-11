// First-visit speed.
//
// The backend runs on a free Render instance, which is put to sleep after 15 minutes without
// traffic. The first request after that has to wait for Django to boot — tens of seconds — and
// for those seconds the storefront had nothing to draw, which reads as a broken site rather
// than a loading one. Three things here, none of which hides a real failure:
//
//   1. warmStart()  — the public catalogue request is fired the moment the JavaScript starts,
//                     before React renders, so the wait overlaps the rest of the boot instead
//                     of following it.
//   2. a cache      — the last answer is kept in localStorage, so a repeat visit paints real
//                     products immediately and the network refresh happens behind it.
//   3. `waking`     — if there is nothing cached and the request is still running after a few
//                     seconds, the page is told so it can say what is happening honestly.
//
// Only public, non-personal catalogue data is cached. Nothing here touches the cart, an order,
// an address or anything that belongs to a signed-in shopper, and nothing is cached from a
// request that carried a token.

import { useEffect, useRef, useState } from 'react';

import apiInstance from './axios';
import { API_BASE_URL } from './constants';

const CACHE_PREFIX = 'noore:catalogue:v1:';
// A single answer bigger than this is not worth storing (localStorage is ~5 MB in total).
const MAX_CACHE_BYTES = 400 * 1024;
// How long a cached answer is served without a visible refresh happening anyway. The refresh
// always runs; this only decides whether the cached copy is used for the first paint.
export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;

const warmed = {};

const keyFor = (path, params) => {
    if (!params) return path;
    const parts = Object.keys(params)
        .sort()
        .map((name) => `${name}=${params[name]}`)
        .join('&');
    return parts ? `${path}?${parts}` : path;
};

// ------------------------------------------------------------------ localStorage, defensively

// Storage throws in a private window, when site data is blocked, and inside some embeds. Every
// read and write is guarded and the app works identically when it fails.
export function readCache(key) {
    try {
        const raw = window.localStorage.getItem(CACHE_PREFIX + key);
        if (!raw) return null;
        const entry = JSON.parse(raw);
        if (!entry || typeof entry.at !== 'number') return null;
        return { data: entry.data, age: Date.now() - entry.at };
    } catch (err) {
        return null;
    }
}

export function writeCache(key, data) {
    try {
        const raw = JSON.stringify({ at: Date.now(), data });
        if (raw.length > MAX_CACHE_BYTES) return;
        window.localStorage.setItem(CACHE_PREFIX + key, raw);
    } catch (err) {
        // Quota exceeded or storage unavailable: the cache is an optimisation, never required.
    }
}

export function clearCache() {
    try {
        Object.keys(window.localStorage)
            .filter((name) => name.startsWith(CACHE_PREFIX))
            .forEach((name) => window.localStorage.removeItem(name));
    } catch (err) {
        // Nothing to do.
    }
}

// ------------------------------------------------------------------ warm start

/**
 * Start the public catalogue requests immediately, outside React.
 *
 * Called from main.jsx. Uses plain fetch, not the Axios instance, because these endpoints are
 * public: no token is read, so nothing waits on a token refresh. The promises are kept and
 * handed to the first component that asks for the same path.
 */
export function warmStart(paths = ['products/', 'addon/']) {
    paths.forEach((path) => {
        if (warmed[path]) return;
        warmed[path] = fetch(API_BASE_URL + path, { headers: { Accept: 'application/json' } })
            .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
            .catch(() => null);
    });
}

function takeWarm(key) {
    const promise = warmed[key];
    if (!promise) return null;
    // One consumer only: a later mount should make a fresh request, not reuse a stale answer.
    delete warmed[key];
    return promise;
}

// Two components mounting at the same moment (the header and the page both read `addon/`) share
// one request instead of making two. It matters most on exactly the slow first load this file
// exists for.
const inflight = {};

function requestOnce(key, path, params) {
    if (inflight[key]) return inflight[key];
    const promise = (takeWarm(key) || apiInstance.get(path, params ? { params } : undefined).then((res) => res.data, () => null))
        .then((data) => {
            delete inflight[key];
            return data;
        }, () => {
            delete inflight[key];
            return null;
        });
    inflight[key] = promise;
    return promise;
}

// ------------------------------------------------------------------ the hook

/**
 * GET a public endpoint, painting a cached answer first when there is one.
 *
 * Returns:
 *   data     the answer, or null while there is nothing at all to show
 *   loading  true until something is in `data`
 *   waking   true when nothing is cached and the request has been running a while, i.e. the
 *            server is almost certainly booting
 *   stale    true while `data` came from the cache and the refresh is still in flight
 *   failed   true when the request failed and there was no cached copy
 */
export function useCachedApi(path, { params = null, slowAfterMs = 3000, enabled = true } = {}) {
    const key = keyFor(path, params);
    const [state, setState] = useState(() => {
        const cached = enabled ? readCache(key) : null;
        if (cached && cached.age < CACHE_MAX_AGE_MS) {
            return { data: cached.data, loading: false, waking: false, stale: true, failed: false };
        }
        return { data: null, loading: true, waking: false, stale: false, failed: false };
    });
    const live = useRef(true);

    useEffect(() => {
        live.current = true;
        const cached = enabled ? readCache(key) : null;
        const hasCached = !!(cached && cached.age < CACHE_MAX_AGE_MS);

        setState(hasCached
            ? { data: cached.data, loading: false, waking: false, stale: true, failed: false }
            : { data: null, loading: true, waking: false, stale: false, failed: false });

        // Say what is happening, but only when the shopper is actually staring at nothing.
        const timer = hasCached ? null : window.setTimeout(() => {
            if (live.current) setState((current) => (current.loading ? { ...current, waking: true } : current));
        }, slowAfterMs);

        Promise.resolve(requestOnce(key, path, params)).then((data) => {
            if (!live.current) return;
            if (timer) window.clearTimeout(timer);
            if (data === null || data === undefined) {
                // Keep whatever was already on screen; only report a failure if nothing is.
                setState((current) => (current.data != null
                    ? { ...current, stale: false, waking: false }
                    : { data: null, loading: false, waking: false, stale: false, failed: true }));
                return;
            }
            if (enabled) writeCache(key, data);
            setState({ data, loading: false, waking: false, stale: false, failed: false });
        });

        return () => {
            live.current = false;
            if (timer) window.clearTimeout(timer);
        };
    }, [key, path, slowAfterMs, enabled]);

    return state;
}