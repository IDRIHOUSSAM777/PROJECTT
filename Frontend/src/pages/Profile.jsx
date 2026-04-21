import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const emptyPasswordForm = {
  current_password: '',
  password: '',
  confirm_password: '',
};

const getErrorMessage = (err, fallback, validationLabel) => {
  const detail = err?.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail.map((d) => d?.msg || d?.message || validationLabel).join(', ');
  }

  if (typeof detail === 'string') {
    return detail;
  }

  return fallback;
};

const Profile = () => {
  const navigate = useNavigate();
  const { t, language, setLanguage, languageOptions, translateData } = useI18n();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const [editingField, setEditingField] = useState(null);
  const [nomInput, setNomInput] = useState('');
  const [prenomInput, setPrenomInput] = useState('');
  const [passwordForm, setPasswordForm] = useState(emptyPasswordForm);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState({ type: '', message: '' });

  useEffect(() => {
    let mounted = true;

    api
      .get('/users/me')
      .then((res) => {
        if (!mounted) return;
        setUser(res.data);
      })
      .catch(() => {
        if (!mounted) return;
        localStorage.removeItem('access_token');
        navigate('/login');
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [navigate]);

  const resetEditState = () => {
    setEditingField(null);
    setPasswordForm(emptyPasswordForm);
    setFeedback({ type: '', message: '' });
  };

  const openEdit = (field) => {
    setEditingField(field);
    setFeedback({ type: '', message: '' });
    if (field === 'nom') setNomInput(user?.nom || '');
    if (field === 'prenom') setPrenomInput(user?.prenom || '');
    if (field === 'password') setPasswordForm(emptyPasswordForm);
  };

  const cancelEdit = () => {
    if (saving) return;
    resetEditState();
  };

  const flashFeedback = (type, message) => {
    setFeedback({ type, message });
    if (type === 'success') {
      setTimeout(() => {
        setFeedback((prev) => (prev.message === message ? { type: '', message: '' } : prev));
      }, 3500);
    }
  };

  const submitNom = async (event) => {
    event.preventDefault();
    if (!nomInput.trim()) {
      setFeedback({ type: 'error', message: t('profile.nameRequired') });
      return;
    }
    try {
      setSaving(true);
      const res = await api.put('/users/me', { nom: nomInput.trim() });
      setUser(res.data);
      resetEditState();
      flashFeedback('success', t('profile.nameUpdated'));
    } catch (err) {
      setFeedback({
        type: 'error',
        message: getErrorMessage(err, t('profile.saveFailed'), t('profile.validationError')),
      });
    } finally {
      setSaving(false);
    }
  };

  const submitPrenom = async (event) => {
    event.preventDefault();
    if (!prenomInput.trim()) {
      setFeedback({ type: 'error', message: t('profile.firstNameRequired') });
      return;
    }
    try {
      setSaving(true);
      const res = await api.put('/users/me', { prenom: prenomInput.trim() });
      setUser(res.data);
      resetEditState();
      flashFeedback('success', t('profile.firstNameUpdated'));
    } catch (err) {
      setFeedback({
        type: 'error',
        message: getErrorMessage(err, t('profile.saveFailed'), t('profile.validationError')),
      });
    } finally {
      setSaving(false);
    }
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    const { current_password, password, confirm_password } = passwordForm;

    if (!current_password || !password || !confirm_password) {
      setFeedback({ type: 'error', message: t('profile.fillAllFields') });
      return;
    }
    if (password.length < 6) {
      setFeedback({ type: 'error', message: t('profile.passwordMin') });
      return;
    }
    if (password !== confirm_password) {
      setFeedback({ type: 'error', message: t('profile.passwordMismatch') });
      return;
    }

    try {
      setSaving(true);
      await api.put('/users/me', { current_password, password });
      resetEditState();
      flashFeedback('success', t('profile.passwordUpdated'));
    } catch (err) {
      setFeedback({
        type: 'error',
        message: getErrorMessage(err, t('profile.saveFailed'), t('profile.validationError')),
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="page-pad container">{t('common.loading')}</div>;
  }

  if (!user) {
    return <div className="page-pad container">{t('profile.userNotFound')}</div>;
  }

  const isAdmin = user.email === 'admin@smartfind.com';
  const avatarText = `${user.prenom?.[0] || ''}${user.nom?.[0] || ''}`.trim().toUpperCase() || 'U';
  const roleLabel = translateData('role', isAdmin ? 'Admin' : 'Utilisateur');

  return (
    <main className="page-pad">
      <div className="container">
        <div className="pf-wrap">
          <section className="pf-header">
            <div className="pf-banner" />
            <div className="pf-header-body">
              <div className="pf-header-left">
                <div className="pf-avatar-xl">{avatarText}</div>
                <div className="pf-header-text">
                  <div className="pf-display-name">{user.prenom} {user.nom}</div>
                  <div className="pf-display-sub">
                    <span className="pf-role-pill">
                      <i className="fa-solid fa-shield-halved" /> {roleLabel}
                    </span>
                    <span><i className="fa-solid fa-envelope" /> {user.email}</span>
                  </div>
                </div>
              </div>
              <div className="pf-header-actions">
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => {
                    localStorage.removeItem('access_token');
                    navigate('/login');
                  }}
                >
                  <i className="fa-solid fa-right-from-bracket" /> {t('nav.logout')}
                </button>
              </div>
            </div>
          </section>

          {feedback.message && (
            <div className={`pf-feedback ${feedback.type}`} role="alert">
              {feedback.message}
            </div>
          )}

          <section className="pf-section">
            <div className="pf-section-title">{t('profile.sectionAccount')}</div>

            <div className="pf-row">
              {editingField === 'prenom' ? (
                <form className="pf-edit-form" onSubmit={submitPrenom}>
                  <div className="pf-row-label">{t('profile.firstName')}</div>
                  <div className="pf-edit-row">
                    <input
                      className="input"
                      type="text"
                      value={prenomInput}
                      onChange={(e) => setPrenomInput(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>
                  <div className="pf-edit-actions">
                    <button type="button" className="btn" onClick={cancelEdit} disabled={saving}>
                      {t('profile.cancel')}
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={saving}>
                      {saving ? t('profile.saveInProgress') : t('profile.save')}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="pf-row-info">
                    <div className="pf-row-label">{t('profile.firstName')}</div>
                    <div className="pf-row-value">{user.prenom}</div>
                  </div>
                  <button
                    type="button"
                    className="pf-btn-edit"
                    onClick={() => openEdit('prenom')}
                    disabled={isAdmin}
                    title={isAdmin ? user.email : ''}
                  >
                    {t('profile.edit')}
                  </button>
                </>
              )}
            </div>

            <div className="pf-row">
              {editingField === 'nom' ? (
                <form className="pf-edit-form" onSubmit={submitNom}>
                  <div className="pf-row-label">{t('profile.lastName')}</div>
                  <div className="pf-edit-row">
                    <input
                      className="input"
                      type="text"
                      value={nomInput}
                      onChange={(e) => setNomInput(e.target.value)}
                      autoFocus
                      required
                    />
                  </div>
                  <div className="pf-edit-actions">
                    <button type="button" className="btn" onClick={cancelEdit} disabled={saving}>
                      {t('profile.cancel')}
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={saving}>
                      {saving ? t('profile.saveInProgress') : t('profile.save')}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="pf-row-info">
                    <div className="pf-row-label">{t('profile.lastName')}</div>
                    <div className="pf-row-value">{user.nom}</div>
                  </div>
                  <button
                    type="button"
                    className="pf-btn-edit"
                    onClick={() => openEdit('nom')}
                    disabled={isAdmin}
                    title={isAdmin ? user.email : ''}
                  >
                    {t('profile.edit')}
                  </button>
                </>
              )}
            </div>

            <div className="pf-row">
              <div className="pf-row-info">
                <div className="pf-row-label">{t('profile.email')}</div>
                <div className="pf-row-value">{user.email}</div>
              </div>
              <span className="pf-row-label" style={{ color: 'var(--muted)' }}>
                <i className="fa-solid fa-lock" /> {t('profile.emailReadOnly')}
              </span>
            </div>
          </section>

          <section className="pf-section">
            <div className="pf-section-title">{t('profile.sectionSecurity')}</div>

            <div className="pf-row">
              {editingField === 'password' ? (
                <form className="pf-edit-form" onSubmit={submitPassword}>
                  <div className="pf-row-label">{t('profile.changePassword')}</div>
                  <input
                    className="input"
                    type="password"
                    placeholder={t('profile.currentPassword')}
                    value={passwordForm.current_password}
                    onChange={(e) => setPasswordForm((p) => ({ ...p, current_password: e.target.value }))}
                    autoComplete="current-password"
                    required
                  />
                  <input
                    className="input"
                    type="password"
                    placeholder={t('profile.newPassword')}
                    value={passwordForm.password}
                    onChange={(e) => setPasswordForm((p) => ({ ...p, password: e.target.value }))}
                    autoComplete="new-password"
                    required
                  />
                  <input
                    className="input"
                    type="password"
                    placeholder={t('profile.confirmPassword')}
                    value={passwordForm.confirm_password}
                    onChange={(e) => setPasswordForm((p) => ({ ...p, confirm_password: e.target.value }))}
                    autoComplete="new-password"
                    required
                  />
                  <div className="pf-edit-actions">
                    <button type="button" className="btn" onClick={cancelEdit} disabled={saving}>
                      {t('profile.cancel')}
                    </button>
                    <button type="submit" className="btn btn-primary" disabled={saving}>
                      {saving ? t('profile.saveInProgress') : t('profile.save')}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="pf-row-info">
                    <div className="pf-row-label">{t('profile.password')}</div>
                    <div className="pf-row-value muted">{t('profile.passwordHidden')}</div>
                  </div>
                  <button
                    type="button"
                    className="pf-btn-edit"
                    onClick={() => openEdit('password')}
                    disabled={isAdmin}
                    title={isAdmin ? user.email : ''}
                  >
                    {t('profile.edit')}
                  </button>
                </>
              )}
            </div>
          </section>

          <section className="pf-section">
            <div className="pf-section-title">{t('profile.sectionPreferences')}</div>
            <div className="pf-pref-row">
              <div className="pf-row-info">
                <div className="pf-row-label">{t('profile.interfaceLanguage')}</div>
                <div className="pf-row-value" style={{ color: 'var(--muted)', fontSize: 13, fontWeight: 600 }}>
                  <i className="fa-solid fa-language" /> {t('common.language')}
                </div>
              </div>
              <select
                className="select"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {languageOptions.map((option) => (
                  <option key={option.code} value={option.code}>{option.label}</option>
                ))}
              </select>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
};

export default Profile;
