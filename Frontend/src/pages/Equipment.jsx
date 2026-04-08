import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const formatDistance = (value, t, locale) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return t('equipment.noDistance');
  if (n >= 1000) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(n / 1000)} km`;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.round(n))} m`;
};

const normalizeStatus = (status) => (status || '').toUpperCase();
const isAvailableStatus = (status) => String(status || '').toLowerCase().includes('disponible') || String(status || '').toLowerCase().includes('available');
const isBrokenStatus = (status) => {
  const lower = String(status || '').toLowerCase();
  return lower.includes('panne') || lower.includes('out of order') || lower.includes('aver');
};

const getIcon = (typeObj) => {
  const t = String(typeObj || '').toLowerCase();
  if (t.includes('imp')) return 'fa-print';
  if (t.includes('proj')) return 'fa-video';
  if (t.includes('pc') || t.includes('ordinateur')) return 'fa-desktop';
  if (t.includes('wifi') || t.includes('routeur')) return 'fa-wifi';
  if (t.includes('contrôle') || t.includes('acces') || t.includes('accès')) return 'fa-id-badge';
  return 'fa-cube';
};

const Equipment = () => {
  const { t, translateData, locale } = useI18n();
  const { id } = useParams();
  const navigate = useNavigate();

  const [equipment, setEquipment] = useState(null);
  const [queueInfo, setQueueInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState({ text: '', type: '' });
  const [isAdmin, setIsAdmin] = useState(false);

  const loadData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError('');

    try {
      const [detailsRes, queueRes, userRes] = await Promise.all([
        api.get(`/objects/${id}`),
        api.get(`/objects/${id}/queue`),
        api.get('/users/me').catch(() => ({ data: {} })),
      ]);

      setEquipment(detailsRes.data || null);
      setQueueInfo(queueRes.data || null);
      setIsAdmin(userRes.data?.role === 'Admin');
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('equipment.notFoundTitle'));
      setEquipment(null);
      setQueueInfo(null);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    loadData(true);
  }, [id]);

  const reservationStatus = normalizeStatus(equipment?.my_reservation_status);

  const isMyReservationActive = reservationStatus === 'ACTIVE';
  const isMyReservationWaiting = reservationStatus === 'WAITING';
  const hasMyReservation = isMyReservationActive || isMyReservationWaiting;

  const waitingCount = useMemo(() => {
    const queueCount = Number(queueInfo?.waiting_count);
    if (Number.isFinite(queueCount)) return queueCount;

    const detailsCount = Number(equipment?.queue_count);
    if (Number.isFinite(detailsCount)) return detailsCount;

    return 0;
  }, [queueInfo, equipment]);

  const handleReserve = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      const res = await api.post('/reservations', { object_id: Number(id) });
      setFeedback({ text: res.data?.message || t('equipment.reservationHandled'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.reserveError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelReservation = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      let res;
      if (equipment?.my_reservation_id) {
        res = await api.delete(`/reservations/${equipment.my_reservation_id}`);
      } else {
        res = await api.delete(`/reservations?object_id=${id}`);
      }

      setFeedback({ text: res?.data?.message || t('equipment.cancelledSuccess'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.cancelError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCompleteReservation = async () => {
    setActionLoading(true);
    setFeedback({ text: '', type: '' });

    try {
      if (!equipment?.my_reservation_id) {
        setFeedback({ text: t('equipment.completeMissing'), type: 'error' });
        return;
      }

      const res = await api.post(`/reservations/${equipment.my_reservation_id}/complete`);
      setFeedback({ text: res.data?.message || t('equipment.completedSuccess'), type: 'success' });
      await loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : t('equipment.completeError'), type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="page-pad equipment-page">
        <div className="container">
          <div className="equip-loading card">
            <div className="equip-skeleton equip-skeleton-title" />
            <div className="equip-skeleton equip-skeleton-line" />
            <div className="equip-skeleton equip-skeleton-line short" />
            <div className="equip-skeleton equip-skeleton-box" />
          </div>
        </div>
      </main>
    );
  }

  if (error || !equipment) {
    return (
      <main className="page-pad equipment-page">
        <div className="container">
          <section className="card equip-error">
            <h2>{t('equipment.notFoundTitle')}</h2>
            <p>{error || t('equipment.notFoundBody')}</p>
            <button className="btn" onClick={() => navigate(-1)}>
              {t('equipment.back')}
            </button>
          </section>
        </div>
      </main>
    );
  }

  const localisation = equipment.localisation || {};
  const locationText = `${localisation.floor !== null && localisation.floor !== undefined ? `${t('common.floor')} ${localisation.floor}` : t('equipment.noFloor')
    } - ${localisation.room || t('equipment.noRoom')}`;

  let statusClass = 'warning';
  if (isAvailableStatus(equipment.status)) statusClass = 'ok';
  else if (isBrokenStatus(equipment.status)) statusClass = 'busy';

  return (
    <main className="page-pad equipment-page">
      <div className="container">
        <div className="equip-topbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button className="icon-btn" onClick={() => navigate(-1)}>
              <i className="fa-solid fa-arrow-left" />
            </button>
            <div>
              <h1 className="section-title" style={{ margin: 0 }}>{t('equipment.title')}</h1>
              <p className="subtitle" style={{ margin: 0 }}>{t('equipment.subtitle')}</p>
            </div>
          </div>

          {isAdmin && (
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => navigate(`/admin/equipment/${id}/edit`)}
                style={{ background: '#3b82f6', color: 'white', border: 'none', padding: '10px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <i className="fa-solid fa-pen"></i> Modifier
              </button>
              <button
                onClick={async () => {
                  if (window.confirm("Êtes-vous sûr de vouloir supprimer cet équipement définitivement ?")) {
                    try {
                      await api.delete(`/objets/${id}`);
                      alert("Équipement supprimé");
                      navigate(-1);
                    } catch (err) {
                      alert("Erreur lors de la suppression.");
                    }
                  }
                }}
                style={{ background: '#ef4444', color: 'white', border: 'none', padding: '10px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}
              >
                <i className="fa-solid fa-trash"></i> Supprimer
              </button>
            </div>
          )}
        </div>

        <section className="card equip-hero-card" style={{ display: 'flex', flexDirection: 'row', gap: '24px', alignItems: 'center', padding: '24px' }}>

          <div style={{ flexShrink: 0, width: '180px', height: '180px', backgroundColor: 'var(--surface-2)', borderRadius: '14px', border: '1px solid var(--border)', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {equipment.url_photo ? (
              <img
                src={`http://127.0.0.1:8000${equipment.url_photo}`}
                alt={equipment.name}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <i className={`fa-solid ${getIcon(equipment.type)}`} style={{ fontSize: '64px', color: 'var(--primary)', opacity: 0.6 }}></i>
            )}
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignSelf: 'stretch', justifyContent: 'space-between' }}>
            <div className="equip-hero-top" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px', padding: 0, border: 'none' }}>
              <div>
                <h2 className="equip-name" style={{ margin: '0 0 6px 0', fontSize: '1.8rem', fontWeight: 'bold' }}>{equipment.name}</h2>
                <p className="equip-subtype" style={{ margin: 0, color: 'var(--muted)', fontSize: '1rem' }}>{translateData('type', equipment.type) || '-'} - {equipment.marque || '-'}</p>
              </div>
              <span className={`badge ${statusClass}`}>{translateData('status', equipment.status)}</span>
            </div>

            <div className="equip-meta-lines" style={{ display: 'flex', flexDirection: 'column', gap: '8px', margin: 0 }}>
              <div className="equip-meta-line" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-soft)', fontSize: '0.95rem' }}>
                <i className="fa-solid fa-location-dot" style={{ color: 'var(--primary)', width: '16px', textAlign: 'center' }} />
                <span>{locationText}</span>
              </div>
              <div className="equip-meta-line" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-soft)', fontSize: '0.95rem' }}>
                <i className="fa-regular fa-compass" style={{ color: 'var(--primary)', width: '16px', textAlign: 'center' }} />
                <span>{formatDistance(equipment.distance_m, t, locale)}</span>
              </div>
              {isAdmin && (
                <>
                  <div className="equip-meta-line" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-soft)', fontSize: '0.95rem' }}>
                    <i className="fa-solid fa-microchip" style={{ color: 'var(--primary)', width: '16px', textAlign: 'center' }} />
                    <span style={{ fontFamily: 'monospace' }}>MAC: {equipment.mac_adresse || 'N/A'}</span>
                  </div>
                  <div className="equip-meta-line" style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-soft)', fontSize: '0.95rem' }}>
                    <i className="fa-solid fa-network-wired" style={{ color: 'var(--primary)', width: '16px', textAlign: 'center' }} />
                    <span style={{ fontFamily: 'monospace' }}>IP: {equipment.ip_adress || 'Non assignée'}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </section>

        <section className="equip-details-grid">
          <article className="card equip-block">
            <h3>{t('common.features')}</h3>
            {Array.isArray(equipment.fonctionnalites) && equipment.fonctionnalites.length > 0 ? (
              <ul className="equip-list">
                {equipment.fonctionnalites.map((feature) => (
                  <li key={feature}>
                    <i className="fa-solid fa-check" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="equip-empty">{t('equipment.noFeatures')}</p>
            )}
          </article>

          <article className="card equip-block">
            <h3>{t('common.description')}</h3>
            <p className="equip-description">
              {equipment.description || t('equipment.noDescription')}
            </p>
          </article>

          <aside className="card equip-block equip-actions">
            <h3>{t('equipment.reservation')}</h3>

            {!hasMyReservation && (
              <button
                className="btn btn-primary equip-action-btn"
                onClick={handleReserve}
                disabled={actionLoading || isBrokenStatus(equipment.status)}
              >
                {isBrokenStatus(equipment.status)
                  ? t('equipment.unavailable')
                  : actionLoading
                    ? t('equipment.processing')
                    : normalizeStatus(equipment.status) === 'OCCUPÉ' || normalizeStatus(equipment.status) === 'RESERVÉ' || normalizeStatus(equipment.status) === 'RESERVED'
                      ? t('equipment.joinQueue')
                      : t('equipment.reserve')}
              </button>
            )}

            {isMyReservationActive && (
              <button
                className="btn btn-primary equip-action-btn"
                onClick={handleCompleteReservation}
                disabled={actionLoading}
              >
                {actionLoading ? t('equipment.processing') : t('equipment.complete')}
              </button>
            )}

            {isMyReservationWaiting && (
              <button
                className="btn equip-action-btn"
                onClick={handleCancelReservation}
                disabled={actionLoading}
              >
                {actionLoading ? t('equipment.processing') : t('equipment.cancel')}
              </button>
            )}

            <div className="equip-queue">{t('equipment.queue')}: {waitingCount}</div>

            {isMyReservationWaiting && (
              <div className="chip chip-progress equip-chip">{t('equipment.waiting')}</div>
            )}

            {isMyReservationActive && (
              <div className="chip chip-done equip-chip">{t('equipment.active')}</div>
            )}

            {feedback.text && (
              <div className={`chip equip-chip ${feedback.type === 'error' ? 'chip-busy' : 'chip-done'}`}>
                {feedback.text}
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
};

export default Equipment;
