import axios from 'axios';

// On pointe vers ton Backend FastAPI
const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// INTERCEPTEUR (Le "Douanier")
// Avant chaque requête, on regarde si on a un token et on l'ajoute
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
