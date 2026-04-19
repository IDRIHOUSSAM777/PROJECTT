import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const parseBackendDate = (value) => {
  if (!value) return null;
  const raw = String(value);
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(raw);
  const parsed = new Date(hasTimezone ? raw : `${raw}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatRelativeTime = (value, locale) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return '';
  const diffMs = Date.now() - parsed.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (diffMs < minute) return rtf.format(0, 'second');
  if (diffMs < hour) return rtf.format(-Math.floor(diffMs / minute), 'minute');
  if (diffMs < day) return rtf.format(-Math.floor(diffMs / hour), 'hour');
  return rtf.format(-Math.floor(diffMs / day), 'day');
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

const isAvailableStatus = (status) => String(status || '').toLowerCase().includes('disponible') || String(status || '').toLowerCase().includes('available');
const isBrokenStatus = (status) => {
  const lower = String(status || '').toLowerCase();
  return lower.includes('panne') || lower.includes('out of order') || lower.includes('aver');
};

const Favorites = () => {
  const { t, translateData, locale } = useI18n();
  const navigate = useNavigate();

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/users/me/favorites');
      setItems(Array.isArray(res.data) ? res.data : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleRemove = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm(t('favorites.removeConfirm'))) return;
    setRemovingId(id);
    try {
      await api.delete(`/users/me/favorites/${id}`);
      setItems((prev) => prev.filter((f) => f.id_objet !== id));
    } catch {
      // silencieux
    } finally {
      setRemovingId(null);
    }
  };

  const statusClassFor = (status) => {
    if (isAvailableStatus(status)) return 'ok';
    if (isBrokenStatus(status)) return 'busy';
    return 'warning';
  };

  return (
    <main className="page-pad favorites-page">
      <div className="container">
        <header className="favorites-head">
          <div>
            <h1 className="favorites-title">
              <i className="fa-solid fa-star favorites-title-icon" /> {t('favorites.title')}
            </h1>
            <p className="favorites-subtitle">{t('favorites.subtitle')}</p>
          </div>
        </header>

        {loading ? (
          <div className="favorites-grid">
            {[0, 1, 2].map((k) => (
              <div key={k} className="favorites-skeleton-card">
                <div className="favorites-skel-img" />
                <div className="favorites-skel-body">
                  <div className="favorites-skel-line" />
                  <div className="favorites-skel-line short" />
                </div>
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <section className="favorites-empty-container">
            <div className="favorites-empty-glass">
              <div className="favorites-empty-illustration">
                <div className="fav-star-glow" />
                <i className="fa-solid fa-star-half-stroke" />
              </div>
              <h2 className="favorites-empty-title">{t('favorites.empty')}</h2>
              <p className="favorites-empty-hint">{t('favorites.emptyHint')}</p>
              <button
                className="btn-premium-action"
                onClick={() => navigate('/categories')}
              >
                <span>{t('favorites.browse')}</span>
                <i className="fa-solid fa-arrow-right" />
              </button>
            </div>
          </section>
        ) : (
          <section className="favorites-grid">
            {items.map((fav) => {
              const removing = removingId === fav.id_objet;
              return (
                <article
                  key={fav.id_objet}
                  className={`card favorites-card ${removing ? 'is-removing' : ''}`}
                  onClick={() => navigate(`/equipment/${fav.id_objet}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') navigate(`/equipment/${fav.id_objet}`);
                  }}
                >
                  <div className="favorites-card-media">
                    {fav.url_photo ? (
                      <img
                        src={`http://127.0.0.1:8000${fav.url_photo}`}
                        alt={fav.nom_model}
                      />
                    ) : (
                      <i className={`fa-solid ${getIcon(fav.type_objet)}`} />
                    )}
                    <button
                      type="button"
                      className="favorites-card-remove"
                      onClick={(e) => handleRemove(e, fav.id_objet)}
                      aria-label={t('favorites.remove')}
                      title={t('favorites.remove')}
                      disabled={removing}
                    >
                      <i className="fa-solid fa-star" />
                    </button>
                  </div>

                  <div className="favorites-card-body">
                    <div className="favorites-card-head">
                      <h3 className="favorites-card-title">{fav.nom_model}</h3>
                      <span className={`badge ${statusClassFor(fav.statut)}`}>
                        {translateData('status', fav.statut)}
                      </span>
                    </div>
                    <p className="favorites-card-meta">
                      {translateData('type', fav.type_objet) || '—'}
                      {fav.nom_marque ? ` · ${fav.nom_marque}` : ''}
                    </p>
                    <p className="favorites-card-date">
                      <i className="fa-regular fa-clock" />{' '}
                      {t('favorites.added')} {formatRelativeTime(fav.date_ajout, locale)}
                    </p>
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
};

export default Favorites;
