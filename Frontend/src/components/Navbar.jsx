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

const notificationTypeLabel = (type, language) => {
  const normalized = String(type || '').toUpperCase();
  if (normalized === 'TURN_READY') {
    if (language === 'en') return 'Your turn';
    if (language === 'es') return 'Tu turno';
    if (language === 'ar') return 'حان دورك';
    return 'Votre tour';
  }
  if (normalized === 'RESERVATION') {
    if (language === 'en') return 'Reservation';
    if (language === 'es') return 'Reserva';
    if (language === 'ar') return 'حجز';
    return 'Réservation';
  }
  if (normalized === 'PANNE_ALERTE' || normalized === 'PANNE_IOT') {
    if (language === 'en') return 'Breakdown Alert';
    if (language === 'es') return 'Alerta de avería';
    if (language === 'ar') return 'تنبيه عطل';
    return 'Alerte Panne';
  }
  if (normalized === 'ALERT') {
    if (language === 'en') return 'Alert';
    if (language === 'es') return 'Alerta';
    if (language === 'ar') return 'تنبيه';
    return 'Alerte';
  }
  if (language === 'ar') return 'معلومة';
  return 'Info';
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
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifLoading, setNotifLoading] = useState(false);
  const token = localStorage.getItem('access_token');

  const fetchNotifications = useCallback(async () => {
    if (!token) return;
    setNotifLoading(true);
    try {
      const res = await api.get('/users/me/notifications?limit=12');
      const items = Array.isArray(res?.data?.items) ? res.data.items : [];
      const unread = Number(res?.data?.unread_count);
      setNotifications(items);
      setUnreadCount(Number.isFinite(unread) ? unread : 0);
    } catch {
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setNotifLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    api.get('/users/me')
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem('access_token');
        setNotifications([]);
        setUnreadCount(0);
        navigate('/login');
      });
  }, [token, navigate]);

  useEffect(() => {
    if (!token) return undefined;
    fetchNotifications();
    const timer = window.setInterval(fetchNotifications, 30000);
    return () => window.clearInterval(timer);
  }, [token, fetchNotifications]);

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
    setNotifications([]);
    setUnreadCount(0);
    navigate('/login');
  };

  const firstName = user?.prenom || '';
  const lastName = user?.nom || '';
  const fullName = `${firstName} ${lastName}`.trim() || translateData('role', 'Utilisateur');
  const roleLabel = translateData('role', user?.role || 'Utilisateur');
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
        <Link className={`nav-item ${isActive('/history')}`} to="/history">
          <i className="fa-regular fa-clock" />
          <span>{t('nav.history')}</span>
        </Link>
        {String(user?.role || '').toLowerCase() === 'admin' && (
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

        <div className="notif-wrap">
          <button
            className={`icon-btn notif-btn ${isActive('/notifications')}`}
            onClick={() => {
              navigate('/notifications');
              fetchNotifications(); // Refresh badge on click
            }}
            aria-label={t('nav.notifications')}
            title={t('nav.notifications')}
          >
            <i className="fa-regular fa-bell" />
            {unreadCount > 0 && <span className="notif-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>}
          </button>
        </div>

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
