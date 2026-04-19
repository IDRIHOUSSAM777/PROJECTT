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
    const [info, setInfo] = useState('');
    const [loading, setLoading] = useState(false);
    const [cooldown, setCooldown] = useState(0);

    useEffect(() => {
        if (!email) {
            navigate('/login');
        }
    }, [email, navigate]);

    useEffect(() => {
        if (cooldown > 0) {
            const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
            return () => clearTimeout(timer);
        }
    }, [cooldown]);

    const extractError = (err, fallback) => {
        if (err.response?.status === 429) return 'Trop de tentatives. Réessayez dans une minute.';
        const detail = err.response?.data?.detail;
        if (Array.isArray(detail)) return detail[0].msg;
        return detail || fallback;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!code) return;

        setError('');
        setInfo('');
        setLoading(true);
        try {
            await api.post('/verify-email', { email, code });
            navigate('/login', { state: { verified: true } });
        } catch (err) {
            setError(extractError(err, t('auth.verifyError') || 'Erreur.'));
        } finally {
            setLoading(false);
        }
    };

    const handleResend = async () => {
        if (cooldown > 0 || loading) return;
        setError('');
        setInfo('');
        setLoading(true);
        try {
            await api.post('/resend-otp', { email });
            setCooldown(30);
            setInfo('Nouveau code envoyé. Vérifiez votre boîte mail (et le dossier spam).');
        } catch (err) {
            setError(extractError(err, 'Erreur lors du renvoi.'));
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
                    Un code à 8 chiffres a été envoyé à <strong>{email}</strong>.
                </p>

                {error && <div className="chip chip-busy" style={{ width: '100%', justifyContent: 'center', marginBottom: '16px' }}>{error}</div>}
                {info && <div className="chip" style={{ width: '100%', justifyContent: 'center', marginBottom: '16px', background: '#ecfdf5', color: '#065f46', border: '1px solid #a7f3d0' }}>{info}</div>}

                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <input
                        type="text"
                        className="input"
                        placeholder={t('auth.code') || 'Code à 8 chiffres'}
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                        maxLength={8}
                        inputMode="numeric"
                        required
                        style={{ textAlign: 'center', letterSpacing: '4px', fontSize: '20px', fontWeight: 'bold' }}
                    />

                    <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={loading || code.length < 8}>
                        {loading ? t('common.loading') : (t('auth.verify') || 'Vérifier')}
                    </button>

                    <p style={{ textAlign: 'center', fontSize: '14px', marginTop: '16px' }}>
                        Vous n'avez pas reçu le code ?{' '}
                        <button
                            type="button"
                            onClick={handleResend}
                            disabled={loading || cooldown > 0}
                            style={{
                                background: 'none',
                                border: 'none',
                                color: cooldown > 0 ? 'var(--text-light)' : '#3b82f6',
                                cursor: cooldown > 0 ? 'default' : 'pointer',
                                fontWeight: 'bold'
                            }}
                        >
                            {cooldown > 0 ? `Renvoyer (${cooldown}s)` : 'Renvoyer le code'}
                        </button>
                    </p>
                </form>
            </div>
        </div>
    );
};

export default VerifyEmail;
