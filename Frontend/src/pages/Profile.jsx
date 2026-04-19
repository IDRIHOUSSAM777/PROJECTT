import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const emptyPrefs = {
  current_password: '',
  password: '',
  confirm_password: '',
};

const getErrorMessage = (err, fallback, validationLabel) => {
  const detail = err?.response?.data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((d) => d?.msg || d?.message || validationLabel)
      .join(', ');
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

  const [prefsOpen, setPrefsOpen] = useState(false);
  const [prefsForm, setPrefsForm] = useState(emptyPrefs);
  const [prefsError, setPrefsError] = useState('');
  const [prefsSuccess, setPrefsSuccess] = useState('');
  const [savingPrefs, setSavingPrefs] = useState(false);

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

  const openPreferences = () => {
    setPrefsOpen(true);
    setPrefsError('');
    setPrefsSuccess('');
  };

  const closePreferences = () => {
    if (savingPrefs) return;
    setPrefsOpen(false);
    setPrefsError('');
    setPrefsSuccess('');
    setPrefsForm(emptyPrefs);
  };

  const onPrefsChange = (event) => {
    const { name, value } = event.target;
    setPrefsForm((prev) => ({ ...prev, [name]: value }));
    if (prefsError) setPrefsError('');
    if (prefsSuccess) setPrefsSuccess('');
  };

  const onSubmitPreferences = async (event) => {
    event.preventDefault();
    setPrefsError('');
    setPrefsSuccess('');

    if (!prefsForm.current_password || !prefsForm.password || !prefsForm.confirm_password) {
      setPrefsError(t('profile.fillAllFields'));
      return;
    }

    if (prefsForm.password.length < 6) {
      setPrefsError(t('profile.passwordMin'));
      return;
    }

    if (prefsForm.password !== prefsForm.confirm_password) {
      setPrefsError(t('profile.passwordMismatch'));
      return;
    }

    try {
      setSavingPrefs(true);

      await api.put('/users/me', {
        current_password: prefsForm.current_password,
        password: prefsForm.password,
      });

      setPrefsSuccess(t('profile.passwordUpdated'));
      setPrefsForm(emptyPrefs);
    } catch (err) {
      setPrefsError(getErrorMessage(err, t('profile.saveFailed'), t('profile.validationError')));
    } finally {
      setSavingPrefs(false);
    }
  };

  if (loading) {
    return <div className="page-pad container">{t('common.loading')}</div>;
  }

  if (!user) {
    return <div className="page-pad container">{t('profile.userNotFound')}</div>;
  }

  const avatarText = `${user.nom?.[0] || ''}${user.prenom?.[0] || ''}`.trim() || 'U';

  return (
    <main className="page-pad">
      <div className="container">
        <section className="card profile">
          <div className="pf-left">
            <div className="pf-avatar">{avatarText.toUpperCase()}</div>
            <div>
              <div className="pf-name">{user.nom} {user.prenom}</div>
              <div className="pf-role"><i className="fa-solid fa-shield-halved" /> {translateData('role', user.email === 'admin@smartfind.com' ? 'Admin' : 'Utilisateur')}</div>
              <div className="pf-meta"><span className="pill">{user.email}</span></div>
            </div>
          </div>

          <div className="pf-actions">
            <div className="pf-action-row">
              <button type="button" className="btn" onClick={openPreferences}>
                <i className="fa-solid fa-sliders" /> {t('profile.preferences')}
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => {
                  localStorage.removeItem('access_token');
                  navigate('/login');
                }}
              >
                {t('nav.logout')}
              </button>
            </div>
            <label className="pf-lang-select">
              <span><i className="fa-solid fa-language" /> {t('common.language')}</span>
              <select className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
                {languageOptions.map((option) => (
                  <option key={option.code} value={option.code}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
        </section>
      </div>

      <div className={`modal-backdrop ${prefsOpen ? 'open' : ''}`} onClick={closePreferences}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-head">
            <h3><i className="fa-solid fa-key" /> {t('profile.changePassword')}</h3>
            <button type="button" className="icon-btn" onClick={closePreferences} aria-label={t('common.cancel')}>
              <i className="fa-solid fa-xmark" />
            </button>
          </div>

          <form onSubmit={onSubmitPreferences}>
            <div className="modal-body prefs-body">
              <input
                className="input"
                type="password"
                name="current_password"
                placeholder={t('profile.currentPassword')}
                value={prefsForm.current_password}
                onChange={onPrefsChange}
                autoComplete="current-password"
                required
              />

              <input
                className="input"
                type="password"
                name="password"
                placeholder={t('profile.newPassword')}
                value={prefsForm.password}
                onChange={onPrefsChange}
                autoComplete="new-password"
                required
              />

              <input
                className="input"
                type="password"
                name="confirm_password"
                placeholder={t('profile.confirmPassword')}
                value={prefsForm.confirm_password}
                onChange={onPrefsChange}
                autoComplete="new-password"
                required
              />

              {prefsError && <div className="chip chip-busy prefs-message">{prefsError}</div>}
              {prefsSuccess && <div className="chip chip-done prefs-message">{prefsSuccess}</div>}
            </div>

            <div className="modal-foot prefs-foot">
              <button type="button" className="btn" onClick={closePreferences} disabled={savingPrefs}>
                {t('common.cancel')}
              </button>
              <button type="submit" className="btn btn-primary" disabled={savingPrefs}>
                {savingPrefs ? t('profile.saveInProgress') : t('common.save')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
};

export default Profile;
