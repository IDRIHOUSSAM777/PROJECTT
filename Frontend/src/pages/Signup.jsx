import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const Signup = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({ nom: '', prenom: '', email: '', password: '' });
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await api.post('/signup', formData);
      alert(t('auth.signupSuccess'));
      navigate(`/verify-email?email=${encodeURIComponent(formData.email)}`);
    } catch (err) {
      setError(err.response?.data?.detail || t('auth.signupError'));
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

        <h2>{t('auth.signup')}</h2>

        {error && <div className="chip chip-busy" style={{ width: '100%', justifyContent: 'center', marginBottom: '16px' }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input className="input" placeholder={t('auth.lastName')} onChange={e => setFormData({ ...formData, nom: e.target.value })} required style={{ flex: 1 }} />
            <input className="input" placeholder={t('auth.firstName')} onChange={e => setFormData({ ...formData, prenom: e.target.value })} required style={{ flex: 1 }} />
          </div>
          <input type="email" className="input" placeholder={t('auth.email')} onChange={e => setFormData({ ...formData, email: e.target.value })} required />
          <input type="password" className="input" placeholder={t('auth.password')} onChange={e => setFormData({ ...formData, password: e.target.value })} required />

          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>{t('auth.createMyAccount')}</button>
        </form>

        <Link to="/login" className="auth-link">{t('auth.alreadyAccount')}</Link>
      </div>
    </div>
  );
};

export default Signup;
