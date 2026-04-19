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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [actionLoading, setActionLoading] = useState(false);
  const [feedback, setFeedback] = useState({ text: '', type: '' });
  const [isAdmin, setIsAdmin] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);
  const [favBusy, setFavBusy] = useState(false);
  const [favPulse, setFavPulse] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportText, setReportText] = useState('');
  const [reportBusy, setReportBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState('');

  const loadData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError('');

    try {
      const [detailsRes, userRes] = await Promise.all([
        api.get(`/objets/${id}`),
        api.get('/users/me').catch(() => ({ data: {} })),
      ]);

      setEquipment(detailsRes.data || null);
      const admin = userRes.data?.email === 'admin@smartfind.com';
      setIsAdmin(admin);

      try {
        const favRes = await api.get('/users/me/favorites');
        const list = Array.isArray(favRes.data) ? favRes.data : [];
        setIsFavorite(list.some((f) => Number(f.id_objet) === Number(id)));
      } catch {
        setIsFavorite(false);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('equipment.notFoundTitle'));
      setEquipment(null);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const toggleFavorite = async () => {
    if (favBusy) return;
    const wasFavorite = isFavorite;
    setIsFavorite(!wasFavorite);
    setFavPulse(true);
    setTimeout(() => setFavPulse(false), 450);
    setFavBusy(true);
    try {
      if (wasFavorite) {
        await api.delete(`/users/me/favorites/${id}`);
      } else {
        await api.post(`/users/me/favorites/${id}`);
      }
    } catch (err) {
      setIsFavorite(wasFavorite);
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : 'Erreur', type: 'error' });
      setTimeout(() => setFeedback({ text: '', type: '' }), 2500);
    } finally {
      setFavBusy(false);
    }
  };

  const submitReport = async () => {
    const text = reportText.trim();
    if (!text) return;
    setReportBusy(true);
    try {
      await api.post(`/objets/${id}/report`, { description: text });
      setFeedback({ text: 'Panne signalée. Merci !', type: 'success' });
      setReportOpen(false);
      setReportText('');
      loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : 'Échec du signalement', type: 'error' });
    } finally {
      setReportBusy(false);
      setTimeout(() => setFeedback({ text: '', type: '' }), 3000);
    }
  };

  const wakeObjet = async () => {
    if (actionBusy) return;
    setActionBusy('wake');
    try {
      const res = await api.post(`/objets/${id}/wake`);
      const msg = res?.data?.message || 'Magic Packet envoyé.';
      setFeedback({ text: msg, type: 'success' });
      loadData(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({
        text: typeof detail === 'string' ? detail : 'Échec du réveil WoL',
        type: 'error',
      });
    } finally {
      setActionBusy('');
      setTimeout(() => setFeedback({ text: '', type: '' }), 3500);
    }
  };

  const invokeAction = async (actionName) => {
    if (actionBusy) return;
    setActionBusy(actionName);
    try {
      const res = await api.post(`/objets/${id}/action`, { action: actionName });
      const msg = res?.data?.message || `Action "${actionName}" exécutée`;
      setFeedback({ text: msg, type: 'success' });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setFeedback({ text: typeof detail === 'string' ? detail : `Échec de l'action ${actionName}`, type: 'error' });
    } finally {
      setActionBusy('');
      setTimeout(() => setFeedback({ text: '', type: '' }), 3000);
    }
  };

  useEffect(() => {
    loadData(true);
  }, [id]);

  // Reservation logic removed
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
        {feedback.text && (
          <div
            style={{
              padding: '12px 16px',
              borderRadius: '8px',
              marginBottom: '14px',
              fontWeight: 'bold',
              background: feedback.type === 'success' ? '#dcfce7' : '#fee2e2',
              color: feedback.type === 'success' ? '#166534' : '#991b1b',
              border: `1px solid ${feedback.type === 'success' ? '#86efac' : '#fecaca'}`,
            }}
          >
            {feedback.text}
          </div>
        )}
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

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            {equipment.supports_wol && (
              <button
                type="button"
                onClick={wakeObjet}
                disabled={!!actionBusy}
                title="Envoyer un Magic Packet Wake-on-LAN"
                style={{
                  background: actionBusy === 'wake' ? '#94a3b8' : '#f59e0b',
                  color: 'white',
                  border: 'none',
                  padding: '10px 16px',
                  borderRadius: '8px',
                  cursor: actionBusy ? 'wait' : 'pointer',
                  fontWeight: 'bold',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <i className={`fa-solid ${actionBusy === 'wake' ? 'fa-spinner fa-spin' : 'fa-power-off'}`}></i>
                {actionBusy === 'wake' ? 'Réveil…' : 'Réveiller (WoL)'}
              </button>
            )}
            {!isAdmin && (
              <>
                <button
                  type="button"
                  onClick={() => setReportOpen(true)}
                  title="Signaler une panne"
                  style={{
                    background: '#fee2e2',
                    color: '#b91c1c',
                    border: '1px solid #fecaca',
                    padding: '10px 16px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <i className="fa-solid fa-triangle-exclamation"></i>
                  Signaler une panne
                </button>
                <button
                  type="button"
                  className={`fav-btn ${isFavorite ? 'is-active' : ''} ${favPulse ? 'is-pulse' : ''}`}
                  onClick={toggleFavorite}
                  disabled={favBusy}
                  aria-pressed={isFavorite}
                  aria-label={isFavorite ? t('equipment.removeFavorite') : t('equipment.addFavorite')}
                  title={isFavorite ? t('equipment.removeFavorite') : t('equipment.addFavorite')}
                >
                  <i className={`fa-${isFavorite ? 'solid' : 'regular'} fa-star fav-btn-icon`} />
                  <span className="fav-btn-label">
                    {isFavorite ? t('equipment.removeFavorite') : t('equipment.addFavorite')}
                  </span>
                </button>
              </>
            )}
            {isAdmin && (
              <>
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
              </>
            )}
          </div>
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
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span className={`badge ${statusClass}`}>{translateData('status', equipment.status)}</span>
                {equipment.supports_wol && (
                  <span
                    className="badge"
                    style={{
                      background: equipment.power_state === 'on' ? '#dcfce7' : equipment.power_state === 'sleep' ? '#e0e7ff' : '#f1f5f9',
                      color: equipment.power_state === 'on' ? '#166534' : equipment.power_state === 'sleep' ? '#3730a3' : '#475569',
                      border: `1px solid ${equipment.power_state === 'on' ? '#86efac' : equipment.power_state === 'sleep' ? '#a5b4fc' : '#cbd5e1'}`,
                    }}
                    title="État d'alimentation (WoL)"
                  >
                    <i className={`fa-solid ${equipment.power_state === 'on' ? 'fa-bolt' : equipment.power_state === 'sleep' ? 'fa-moon' : 'fa-circle-question'}`} style={{ marginRight: 6 }} />
                    {equipment.power_state === 'on' ? 'Allumé' : equipment.power_state === 'sleep' ? 'En veille' : 'État inconnu'}
                  </span>
                )}
              </div>
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
                {equipment.fonctionnalites.map((feature) => {
                  const actionName = String(feature || '').toLowerCase();
                  const busy = actionBusy === actionName;
                  return (
                    <li key={feature} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <i className="fa-solid fa-check" />
                        <span>{feature}</span>
                      </span>
                      {!isAdmin && isAvailableStatus(equipment.status) && (
                        <button
                          type="button"
                          onClick={() => invokeAction(actionName)}
                          disabled={!!actionBusy}
                          title={`Actionner : ${feature}`}
                          style={{
                            background: busy ? '#94a3b8' : 'var(--primary)',
                            color: 'white',
                            border: 'none',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            cursor: busy ? 'wait' : 'pointer',
                            fontSize: '0.85rem',
                            fontWeight: 'bold',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                          }}
                        >
                          <i className={`fa-solid ${busy ? 'fa-spinner fa-spin' : 'fa-play'}`}></i>
                          {busy ? '...' : 'Actionner'}
                        </button>
                      )}
                    </li>
                  );
                })}
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

        </section>
      </div>

      {reportOpen && (
        <div
          onClick={() => !reportBusy && setReportOpen(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000, padding: '20px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--surface)', borderRadius: '12px',
              padding: '24px', width: '100%', maxWidth: '480px',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            }}
          >
            <h3 style={{ margin: '0 0 6px 0', display: 'flex', alignItems: 'center', gap: '10px', color: '#b91c1c' }}>
              <i className="fa-solid fa-triangle-exclamation"></i>
              Signaler une panne
            </h3>
            <p style={{ margin: '0 0 16px 0', color: 'var(--muted)', fontSize: '0.9rem' }}>
              Décrivez brièvement le problème observé sur <strong>{equipment.name}</strong>.
            </p>
            <textarea
              autoFocus
              value={reportText}
              onChange={(e) => setReportText(e.target.value)}
              placeholder="Ex: Bourrage papier, écran noir, appareil ne s'allume plus..."
              rows={4}
              style={{
                width: '100%', padding: '12px', borderRadius: '8px',
                border: '1px solid var(--border)', background: 'var(--surface-2)',
                color: 'var(--text)', fontSize: '0.95rem', resize: 'vertical',
                fontFamily: 'inherit',
              }}
            />
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button
                type="button"
                onClick={() => { setReportOpen(false); setReportText(''); }}
                disabled={reportBusy}
                style={{
                  background: 'transparent', color: 'var(--text)',
                  border: '1px solid var(--border)', padding: '10px 16px',
                  borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold',
                }}
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={submitReport}
                disabled={reportBusy || !reportText.trim()}
                style={{
                  background: reportBusy ? '#94a3b8' : '#dc2626', color: 'white',
                  border: 'none', padding: '10px 18px', borderRadius: '8px',
                  cursor: reportBusy ? 'wait' : 'pointer', fontWeight: 'bold',
                  display: 'flex', alignItems: 'center', gap: '8px',
                }}
              >
                <i className={`fa-solid ${reportBusy ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`}></i>
                {reportBusy ? 'Envoi...' : 'Envoyer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
};

export default Equipment;
