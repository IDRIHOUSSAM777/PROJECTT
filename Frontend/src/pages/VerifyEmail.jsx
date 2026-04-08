import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const VerifyEmail = () => {
    const { t } = useI18n();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const email = searchParams.get('email') || '';

    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!email) {
            navigate('/login');
        }
    }, [email, navigate]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!code) return;

        setError('');
        setLoading(true);
        try {
            await api.post('/verify-email', { email, code });
            alert(t('auth.verifySuccess') || 'Email vérifié avec succès. Vous pouvez maintenant vous connecter.');
            navigate('/login');
        } catch (err) {
            setError(err.response?.data?.detail || t('auth.verifyError') || 'Erreur lors de la vérification.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-wrapper">
            <div className="card auth-card">
                <div className="brand" style={{ marginBottom: '24px' }}>
                    <div className="logo">
                        <span className="logo-strong">SMART</span><span className="logo-soft">FIND</span>
                    </div>
                </div>

                <h2 style={{ textAlign: 'center', marginBottom: '8px' }}>{t('auth.verifyEmail') || 'Vérification Email'}</h2>
                <p style={{ textAlign: 'center', color: 'var(--text-light)', marginBottom: '24px', fontSize: '14px' }}>
                    Un code à 6 chiffres a été envoyé à <strong>{email}</strong>.
                </p>

                {error && <div className="chip chip-busy" style={{ width: '100%', justifyContent: 'center', marginBottom: '16px' }}>{error}</div>}

                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <input
                        type="text"
                        className="input"
                        placeholder={t('auth.code') || 'Code à 6 chiffres'}
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        maxLength={6}
                        required
                        style={{ textAlign: 'center', letterSpacing: '4px', fontSize: '20px', fontWeight: 'bold' }}
                    />

                    <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading || code.length < 6}>
                        {loading ? t('common.loading') : (t('auth.verify') || 'Vérifier')}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default VerifyEmail;
