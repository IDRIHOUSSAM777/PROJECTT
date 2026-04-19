import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';

const ForgotPassword = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState('email'); // 'email' | 'reset'
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState('');
  const [error, setError] = useState('');

  const askCode = async (e) => {
    e.preventDefault();
    setError(''); setInfo('');
    if (!email) return;
    setBusy(true);
    try {
      await api.post('/forgot-password', { email });
      setInfo("Si l'email est enregistré, un code à 6 chiffres a été généré (visible dans les logs serveur en dev).");
      setStep('reset');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : "Une erreur est survenue");
    } finally {
      setBusy(false);
    }
  };

  const submitReset = async (e) => {
    e.preventDefault();
    setError(''); setInfo('');
    if (!code || !newPassword) return;
    if (newPassword !== confirmPassword) {
      setError("Les deux mots de passe ne correspondent pas");
      return;
    }
    if (newPassword.length < 6) {
      setError("Le mot de passe doit contenir au moins 6 caractères");
      return;
    }
    setBusy(true);
    try {
      await api.post('/reset-password', { email, code, new_password: newPassword });
      setInfo("Mot de passe réinitialisé. Redirection vers la connexion...");
      setTimeout(() => navigate('/login'), 1500);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : "Code ou email invalide");
    } finally {
      setBusy(false);
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

        <h2>Mot de passe oublié</h2>

        {error && (
          <div className="chip chip-busy" style={{ width: '100%', justifyContent: 'center', marginBottom: '14px' }}>
            {error}
          </div>
        )}
        {info && (
          <div
            style={{
              width: '100%', marginBottom: '14px', padding: '10px 14px',
              background: '#dcfce7', color: '#166534', borderRadius: '8px',
              border: '1px solid #86efac', fontSize: '0.9rem',
            }}
          >
            {info}
          </div>
        )}

        {step === 'email' && (
          <form onSubmit={askCode} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem' }}>
              Entrez votre email pour recevoir un code de réinitialisation.
            </p>
            <input
              type="email"
              className="input"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
              {busy ? 'Envoi...' : 'Envoyer le code'}
            </button>
          </form>
        )}

        {step === 'reset' && (
          <form onSubmit={submitReset} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem' }}>
              Saisissez le code reçu et choisissez un nouveau mot de passe.
            </p>
            <input
              type="text"
              className="input"
              placeholder="Code à 6 chiffres"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              maxLength={6}
              required
              autoFocus
            />
            <input
              type="password"
              className="input"
              placeholder="Nouveau mot de passe (min. 6 caractères)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
            />
            <input
              type="password"
              className="input"
              placeholder="Confirmer le mot de passe"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={6}
            />
            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
              {busy ? 'Validation...' : 'Réinitialiser'}
            </button>
            <button
              type="button"
              onClick={() => { setStep('email'); setCode(''); setNewPassword(''); setConfirmPassword(''); }}
              style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '0.85rem' }}
            >
              ← Changer d'email
            </button>
          </form>
        )}

        <Link to="/login" className="auth-link">Retour à la connexion</Link>
      </div>
    </div>
  );
};

export default ForgotPassword;
