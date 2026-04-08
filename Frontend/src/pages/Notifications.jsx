import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const PAGE_SIZE = 10;

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

const Notifications = () => {
    const { t, language } = useI18n();
    const [notifications, setNotifications] = useState([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const navigate = useNavigate();

    const fetchNotifications = useCallback(async () => {
        setLoading(true);
        try {
            // Fetch more to show pagination accurately
            const res = await api.get('/users/me/notifications?limit=200');
            setNotifications(Array.isArray(res?.data?.items) ? res.data.items : []);
        } catch {
            setNotifications([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchNotifications();
    }, [fetchNotifications]);

    const handleOpenNotification = async (notification) => {
        if (!notification) return;
        if (!notification.est_lu) {
            try {
                await api.post(`/users/me/notifications/${notification.id_notification}/read`);
                setNotifications((prev) =>
                    prev.map((item) =>
                        item.id_notification === notification.id_notification
                            ? { ...item, est_lu: true }
                            : item
                    )
                );
            } catch {
                // keep UI usable
            }
        }
        if (notification.id_objet) {
            navigate(`/equipment/${notification.id_objet}`);
        }
    };

    const handleMarkAllNotificationsRead = async () => {
        try {
            await api.post('/users/me/notifications/read-all');
            setNotifications((prev) => prev.map((item) => ({ ...item, est_lu: true })));
        } catch {
            // ignore
        }
    };

    const totalPages = Math.max(1, Math.ceil(notifications.length / PAGE_SIZE));
    const pagedNotifications = useMemo(() => {
        const start = (page - 1) * PAGE_SIZE;
        return notifications.slice(start, start + PAGE_SIZE);
    }, [notifications, page]);

    // Compute unread count from the loaded list
    const unreadCount = notifications.filter((n) => !n.est_lu).length;

    return (
        <main className="page-pad history-page">
            <div className="container">
                <header className="history-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 className="history-title">{t('nav.notifications')}</h1>
                        <p className="history-subtitle">
                            {language === 'fr' ? 'Consultez et gérez vos alertes' :
                                language === 'en' ? 'View and manage your alerts' :
                                    language === 'es' ? 'Vea y administre sus alertas' :
                                        'عرض وإدارة التنبيهات الخاصة بك'}
                        </p>
                    </div>
                    {unreadCount > 0 && (
                        <button
                            className="btn btn-primary"
                            onClick={handleMarkAllNotificationsRead}
                            style={{ display: 'flex', gap: '8px', alignItems: 'center' }}
                        >
                            <i className="fa-solid fa-check-double" />
                            {t('nav.markAllRead')}
                        </button>
                    )}
                </header>

                <section className="history-panel card">
                    <div className="history-panel-head">
                        <h2><i className="fa-regular fa-bell" /> {t('nav.notifications')}</h2>
                    </div>
                    <div className="history-panel-body">
                        {loading && notifications.length === 0 && <div className="history-empty">{t('nav.loading') || 'Loading...'}</div>}
                        {!loading && notifications.length === 0 && <div className="history-empty">{t('nav.noNotifications') || 'No notifications'}</div>}

                        {pagedNotifications.map((n, i) => {
                            const iconName = n.est_lu ? 'fa-envelope-open' : 'fa-envelope';
                            return (
                                <article
                                    key={`${n.id_notification}-${i}`}
                                    className={`history-action-row ${n.est_lu ? 'read' : 'unread'}`}
                                    onClick={() => handleOpenNotification(n)}
                                    style={{ cursor: 'pointer', backgroundColor: n.est_lu ? 'transparent' : 'var(--bg-soft)' }}
                                >
                                    <div className="history-action-left">
                                        <div className="history-action-icon" style={{ backgroundColor: n.est_lu ? 'var(--bg-soft)' : 'var(--accent)' }}>
                                            <i className={`fa-solid ${iconName}`} style={{ color: n.est_lu ? 'var(--text-soft)' : 'white' }} />
                                        </div>
                                        <div>
                                            <div className="history-action-title" style={{ fontWeight: n.est_lu ? 'normal' : 'bold' }}>
                                                {notificationTypeLabel(n.type_notification, language)}
                                            </div>
                                            <div className="history-action-sub" style={{ whiteSpace: 'pre-wrap', color: n.est_lu ? 'var(--text-soft)' : 'var(--text-strong)' }}>
                                                {n.message}
                                            </div>
                                        </div>
                                    </div>

                                    <div className="history-action-right">
                                        <span className="history-action-date">
                                            <i className="fa-regular fa-clock" /> {formatRelativeTime(n.date_notification, language)}
                                        </span>
                                        {!n.est_lu && (
                                            <span className="history-status history-status-progress">
                                                {language === 'en' ? 'New' : language === 'ar' ? 'جديد' : language === 'es' ? 'Nuevo' : 'Nouveau'}
                                            </span>
                                        )}
                                    </div>
                                </article>
                            );
                        })}
                    </div>

                    {totalPages > 1 && (
                        <div className="pagination history-pagination">
                            <button className="btn pagination-btn" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                                {t('common.previous') || 'Previous'}
                            </button>
                            <span className="pagination-info">{t('common.page') || 'Page'} {page} / {totalPages}</span>
                            <button className="btn pagination-btn" disabled={page === totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                                {t('common.next') || 'Next'}
                            </button>
                        </div>
                    )}
                </section>
            </div>
        </main>
    );
};

export default Notifications;
