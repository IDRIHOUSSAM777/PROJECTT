import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../services/api';
import { useI18n } from '../i18n';

const parseBackendDate = (value) => {
  if (!value) return null;
  const raw = String(value);
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(raw);
  const parsed = new Date(hasTimezone ? raw : `${raw}Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
};

const formatRelativeTime = (value, language) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return '';

  const diffMs = Date.now() - parsed.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (language === 'en') {
    if (diffMs < minute) return 'just now';
    if (diffMs < hour) return `${Math.floor(diffMs / minute)} min ago`;
    if (diffMs < day) return `${Math.floor(diffMs / hour)} h ago`;
    return `${Math.floor(diffMs / day)} d ago`;
  }

  if (language === 'es') {
    if (diffMs < minute) return 'ahora';
    if (diffMs < hour) return `hace ${Math.floor(diffMs / minute)} min`;
    if (diffMs < day) return `hace ${Math.floor(diffMs / hour)} h`;
    return `hace ${Math.floor(diffMs / day)} d`;
  }

  if (language === 'ar') {
    if (diffMs < minute) return 'الآن';
    if (diffMs < hour) return `منذ ${Math.floor(diffMs / minute)} دقيقة`;
    if (diffMs < day) return `منذ ${Math.floor(diffMs / hour)} ساعة`;
    return `منذ ${Math.floor(diffMs / day)} يوم`;
  }

  if (diffMs < minute) return "à l'instant";
  if (diffMs < hour) return `il y a ${Math.floor(diffMs / minute)} min`;
  if (diffMs < day) return `il y a ${Math.floor(diffMs / hour)} h`;
  return `il y a ${Math.floor(diffMs / day)} j`;
};

const Navbar = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { language, t, translateData } = useI18n();

  const [user, setUser] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const token = localStorage.getItem('access_token');

  useEffect(() => {
    if (!token) return;
    api.get('/users/me')
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem('access_token');
        navigate('/login');
      });
  }, [token, navigate]);

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setIsDarkMode(true);
      return;
    }
    if (savedTheme === 'light') {
      setIsDarkMode(false);
      return;
    }
    const prefersDark = typeof window !== 'undefined'
      && window.matchMedia
      && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setIsDarkMode(prefersDark);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDarkMode);
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  if (!token || ['/login', '/signup'].includes(location.pathname)) return null;

  const isActive = (paths) => {
    const list = Array.isArray(paths) ? paths : [paths];
    return list.some((path) => {
      if (path === '/') return location.pathname === '/';
      return location.pathname === path || location.pathname.startsWith(`${path}/`);
    }) ? 'active' : '';
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    navigate('/login');
  };

  const firstName = user?.prenom || '';
  const lastName = user?.nom || '';
  const fullName = `${firstName} ${lastName}`.trim() || translateData('role', 'Utilisateur');
  const roleLabel = translateData('role', user?.email === 'admin@smartfind.com' ? 'Admin' : 'Utilisateur');
  const initials = `${firstName[0] || ''}${lastName[0] || ''}`.toUpperCase() || 'U';

  return (
    <header className="topbar">
      <div className="brand">
        <button className="icon-btn" aria-label={t('nav.search')} onClick={() => navigate('/search')}>
          <i className="fa-solid fa-magnifying-glass" />
        </button>
        <div className="logo">
          <span className="logo-strong">SMART</span>
          <span className="logo-soft">FIND</span>
        </div>
      </div>

      <nav className="nav">
        <Link className={`nav-item ${isActive('/')}`} to="/">
          <i className="fa-solid fa-house" />
          <span>{t('nav.home')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/carte')}`} to="/carte">
          <i className="fa-solid fa-map" />
          <span>{t('nav.map')}</span>
        </Link>
        <Link className={`nav-item ${isActive('/categories')}`} to="/categories">
          <i className="fa-solid fa-table-cells-large" />
          <span>{t('nav.categories')}</span>
        </Link>
        {user?.email !== 'admin@smartfind.com' && (
          <Link className={`nav-item ${isActive('/favorites')}`} to="/favorites">
            <i className="fa-solid fa-star" />
            <span>{t('nav.favorites')}</span>
          </Link>
        )}
        {user?.email !== 'admin@smartfind.com' && (
          <Link className={`nav-item ${isActive('/history')}`} to="/history">
            <i className="fa-regular fa-clock" />
            <span>{t('nav.history')}</span>
          </Link>
        )}
        {user?.email === 'admin@smartfind.com' && (
          <Link className={`nav-item ${isActive(['/admin', '/admin/inventory'])}`} to="/admin">
            <i className="fa-solid fa-shield-halved" />
            <span>{t('nav.admin')}</span>
          </Link>
        )}
      </nav>

      <div className="userbox">
        <div className="usertext">
          <div className="username">{fullName}</div>
          <div className="role">{roleLabel}</div>
        </div>

        <button
          className="icon-btn mode-btn"
          onClick={() => setIsDarkMode((prev) => !prev)}
          aria-label={isDarkMode ? t('nav.switchToLight') : t('nav.switchToDark')}
          title={isDarkMode ? t('nav.modeLight') : t('nav.modeDark')}
        >
          <i className={`fa-solid ${isDarkMode ? 'fa-sun' : 'fa-moon'}`} />
        </button>
        <div className="avatar" onClick={() => navigate('/profile')} title={t('nav.myProfile')} style={{ cursor: 'pointer' }}>
          {initials}
        </div>

        <button className="icon-btn" onClick={handleLogout} aria-label={t('nav.logout')} title={t('nav.logout')}>
          <i className="fa-solid fa-right-from-bracket" />
        </button>
      </div>
    </header>
  );
};

export default Navbar;
