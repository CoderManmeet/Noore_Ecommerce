// Importing the useAuthStore hook from the '../store/auth' file to manage authentication state
import { useAuthStore } from '../store/auth';

// Importing the shared axios instance and its single-flight token refresh
import axios, { refreshAccessToken } from './axios';

// Importing jwt_decode to decode JSON Web Tokens
import jwt_decode from 'jwt-decode';

// Importing the Cookies library to handle browser cookies
import Cookies from 'js-cookie';

// Importing Swal (SweetAlert2) for displaying toast notifications
import Swal from 'sweetalert2';

// Configuring global toast notifications using Swal.mixin
const Toast = Swal.mixin({
    toast: true,
    position: 'top',
    showConfirmButton: false,
    timer: 1500,
    timerProgressBar: true,
});

// Function to handle user login
export const login = async (email, password) => {
    try {
        // Making a POST request to obtain user tokens
        const { data, status } = await axios.post('user/token/', {
            email,
            password,
        });

        // If the request is successful (status code 200), set authentication user and display success toast
        if (status === 200) {
            setAuthUser(data.access, data.refresh);

            // Displaying a success toast notification
            Toast.fire({
                icon: 'success',
                title: 'Signed in successfully'
            });
        }

        // Returning data and error information
        return { data, error: null };
    } catch (error) {
        // Handling errors and returning data and error information
        return {
            data: null,
            error: error.response.data?.detail || 'Something went wrong',
        };
    }
};

// Function to handle user registration
export const register = async (full_name, email, phone, password, password2) => {
    try {
        // Making a POST request to register a new user
        const { data } = await axios.post('user/register/', {
            full_name,
            email,
            phone,
            password,
            password2,
        });

        // Logging in the newly registered user and displaying success toast
        await login(email, password);

        // Displaying a success toast notification
        Toast.fire({
            icon: 'success',
            title: 'Signed Up Successfully'
        });

        // Returning data and error information
        return { data, error: null };

    } catch (error) {
        // Handling errors and returning data and error information
        return {
            data: null,
            error: error.response.data || 'Something went wrong',
        };
    }
};

// Function to handle user logout
export const logout = () => {
    // Removing access and refresh tokens from cookies, resetting user state, and displaying success toast
    Cookies.remove('access_token');
    Cookies.remove('refresh_token');
    useAuthStore.getState().setUser(null);

    // Displaying a success toast notification
    Toast.fire({
        icon: 'success',
        title: 'You have been logged out.'
    });
};

// Function to set the authenticated user on page load
export const setUser = async () => {
    const accessToken = Cookies.get('access_token');
    const refreshToken = Cookies.get('refresh_token');

    if (!accessToken || !refreshToken) {
        useAuthStore.getState().setLoading(false);
        return;
    }

    try {
        if (isAccessTokenExpired(accessToken)) {
            const response = await getRefreshToken();
            setAuthUser(response.access, response.refresh);
        } else {
            setAuthUser(accessToken, refreshToken);
        }
    } catch (error) {
        // Session could not be restored (refresh token expired or revoked): continue as a guest.
        Cookies.remove('access_token');
        Cookies.remove('refresh_token');
        useAuthStore.getState().setUser(null);
        useAuthStore.getState().setLoading(false);
    }
};

// Function to set the authenticated user and update user state
export const setAuthUser = (access_token, refresh_token) => {
    // Setting access and refresh tokens in cookies with expiration dates
    Cookies.set('access_token', access_token, {
        expires: 1,  // Access token expires in 1 day
        secure: true,
        sameSite: 'Lax',
    });

    Cookies.set('refresh_token', refresh_token, {
        expires: 7,  // Refresh token expires in 7 days
        secure: true,
        sameSite: 'Lax',
    });

    // Decoding access token to get user information
    const user = jwt_decode(access_token) ?? null;

    // If user information is present, update user state; otherwise, set loading state to false
    if (user) {
        useAuthStore.getState().setUser(user);
    }
    useAuthStore.getState().setLoading(false);
};

// Function to refresh the access token using the refresh token.
// Uses the same single-flight refresh as the axios interceptor so a rotated refresh token
// is never sent twice.
export const getRefreshToken = async () => {
    const access = await refreshAccessToken();
    if (!access) {
        throw new Error('Session expired');
    }
    return { access, refresh: Cookies.get('refresh_token') };
};

// Function to check if the access token is expired
export const isAccessTokenExpired = (accessToken) => {
    try {
        // Decoding the access token and checking if it has expired
        const decodedToken = jwt_decode(accessToken);
        return decodedToken.exp < Date.now() / 1000;
    } catch (err) {
        // Returning true if the token is invalid or expired
        return true;
    }
};
