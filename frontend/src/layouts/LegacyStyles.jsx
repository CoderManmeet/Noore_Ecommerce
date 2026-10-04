import { useEffect } from 'react';

// Bootstrap, for the pages that were built with it and have not been redesigned: the admin
// area and a few older account pages. It is added to the page only while one of those pages
// is open and removed again afterwards, so it can never restyle the Noore storefront.
//
// The stylesheets are inserted at the START of <head>, so the storefront theme (later in the
// document) still wins wherever both style the same element, e.g. the shared header.
const STYLES = [
    {
        href: 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css',
        integrity: 'sha384-1BmE4kWBq78iYhFldvKuhfTAU6auU8tT94WrHftjDbrCEXSU1oBoqyl2QvZ6jIW3',
    },
    { href: 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css' },
];
const SCRIPTS = [
    {
        src: 'https://cdn.jsdelivr.net/npm/@popperjs/core@2.10.2/dist/umd/popper.min.js',
        integrity: 'sha384-7+zCNj/IqJ95wo16oMtfsKbZ9ccEh31eOz1HGyDuCQ6wgnyJNSYdrPa03rtR1zdB',
    },
    {
        src: 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.min.js',
        integrity: 'sha384-QJHtvGhmr9XOIpI6YVutG+2QOK9T+ZnN4kzFN1RtK3zEFEIsxhlmWl5/YESvpZ13',
    },
];
const MARK = 'data-legacy-styles';

let users = 0;

const addStyles = () => {
    STYLES.slice().reverse().forEach(({ href, integrity }) => {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        if (integrity) {
            link.integrity = integrity;
            link.crossOrigin = 'anonymous';
        }
        link.setAttribute(MARK, '');
        document.head.insertBefore(link, document.head.firstChild);
    });
};

const addScriptsOnce = () => {
    if (document.querySelector(`script[${MARK}]`)) return;
    // In order: Bootstrap's JavaScript needs Popper first.
    SCRIPTS.reduce((previous, { src, integrity }) => previous.then(() => new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = src;
        script.integrity = integrity;
        script.crossOrigin = 'anonymous';
        script.setAttribute(MARK, '');
        script.onload = resolve;
        script.onerror = resolve;
        document.body.appendChild(script);
    })), Promise.resolve());
};

function LegacyStyles() {
    useEffect(() => {
        users += 1;
        if (users === 1) {
            addStyles();
            addScriptsOnce();
        }
        return () => {
            users -= 1;
            if (users === 0) {
                document.querySelectorAll(`link[${MARK}]`).forEach((link) => link.remove());
            }
        };
    }, []);
    return null;
}

export default LegacyStyles;
