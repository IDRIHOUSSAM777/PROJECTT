import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const Login = () => {
  const { t } = useI18n();
  const [email, setEmail] = useState('admin@smart.com');
  const [password, setPassword] = useState('admin');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');

    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    try {
      const response = await api.post('/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      localStorage.setItem('access_token', response.data.access_token);
      navigate('/');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail[0].msg : (detail || t('auth.loginError') || 'Erreur de connexion.'));
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="card auth-card">
        <div className="brand">
          <div className="logo">
            <span className="logo-strong">SMART</span><span className="logo-soft">FIND</span>
          </div>
        </div>

        <h2>{t('auth.login')}</h2>

        {error && <div className="chip chip-busy" style={{ width: '100%', justifyContent: 'center', marginBottom: '16px' }}>{error}</div>}

        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <input
            type="email"
            className="input"
            placeholder={t('auth.email')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            type="password"
            className="input"
            placeholder={t('auth.password')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>{t('auth.signIn')}</button>
        </form>

        <Link to="/forgot-password" className="auth-link" style={{ marginTop: '12px' }}>
          Mot de passe oublié ?
        </Link>
        <Link to="/signup" className="auth-link">{t('auth.noAccount')}</Link>
      </div>
    </div>
  );
};

export default Login;
