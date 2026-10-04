import apiInstance from './axios';

// Kept for backwards compatibility with components that call useAxios().
// The shared instance already attaches and refreshes the JWT on every request.
const useAxios = () => apiInstance;

export default useAxios;
