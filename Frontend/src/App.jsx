import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/Navbar';

// Import des pages
import Login from './pages/Login';
import Signup from './pages/Signup';
import VerifyEmail from './pages/VerifyEmail';
import ForgotPassword from './pages/ForgotPassword';
import Home from './pages/Home';
import Search from './pages/Search';
import Categories from './pages/Categories';
import Equipment from './pages/Equipment';
import History from './pages/History';
import Favorites from './pages/Favorites';
import Profile from './pages/Profile';
import Admin from './pages/Admin';
import Inventory from './pages/Inventory';
import Carte from './pages/Carte';
import EditEquipment from './pages/EditEquipment';

// --- LE GARDIEN (PrivateRoute) ---
// Ce composant vérifie si l'utilisateur est connecté.
// Si OUI : il affiche la page demandée (children).
// Si NON : il redirige vers /login.
const PrivateRoute = ({ children }) => {
  const token = localStorage.getItem('access_token');

  // Si pas de token, on redirige vers Login
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // Sinon, on affiche la page protégée
  return children;
};

function App() {
  return (
    <BrowserRouter>
      {/* La Navbar gère elle-même son affichage (cachée si pas de token) */}
      <Navbar />

      <Routes>
        {/* --- ROUTES PUBLIQUES (Accessibles sans connexion) --- */}
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />

        {/* --- ROUTES PROTÉGÉES (Nécessitent une connexion) --- */}
        {/* On enveloppe chaque page dans <PrivateRoute> */}

        <Route path="/" element={
          <PrivateRoute><Home /></PrivateRoute>
        } />

        <Route path="/search" element={
          <PrivateRoute><Search /></PrivateRoute>
        } />

        <Route path="/categories" element={
          <PrivateRoute><Categories /></PrivateRoute>
        } />

        <Route path="/equipment/:id" element={
          <PrivateRoute><Equipment /></PrivateRoute>
        } />

        <Route path="/carte" element={
          <PrivateRoute><Carte /></PrivateRoute>
        } />

        <Route path="/favorites" element={
          <PrivateRoute><Favorites /></PrivateRoute>
        } />

        <Route path="/history" element={
          <PrivateRoute><History /></PrivateRoute>
        } />

        <Route path="/profile" element={
          <PrivateRoute><Profile /></PrivateRoute>
        } />

        {/* Routes Admin (Protégées aussi) */}
        <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="/admin/dashboard" element={
          <PrivateRoute><Admin /></PrivateRoute>
        } />
        <Route path="/admin/alerts" element={
          <PrivateRoute><Admin /></PrivateRoute>
        } />
        <Route path="/admin/add" element={
          <PrivateRoute><Admin /></PrivateRoute>
        } />

        <Route path="/admin/inventory" element={
          <PrivateRoute><Inventory /></PrivateRoute>
        } />

        <Route path="/admin/equipment/:id/edit" element={
          <PrivateRoute><EditEquipment /></PrivateRoute>
        } />

        {/* Redirection par défaut : Si l'URL n'existe pas, on renvoie vers l'accueil (qui renverra vers login si besoin) */}
        <Route path="*" element={<Navigate to="/" />} />

      </Routes>
    </BrowserRouter>
  );
}

export default App;