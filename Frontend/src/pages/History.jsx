import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const PAGE_SIZE = 10;

const parseBackendDate = (value) => {
  if (!value) return null;
  const dateString = String(value);

  // FastAPI may send naive UTC datetime (without timezone). Force UTC parsing in that case.
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(dateString);
  const parsed = new Date(hasTimezone ? dateString : `${dateString}Z`);

  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
};

const formatRelativeTime = (value, t, locale) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return t('history.unknownDate');

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

const formatActionDate = (value, t, locale) => {
  const parsed = parseBackendDate(value);
  if (!parsed) return t('history.unknownDate');

  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
};

const statusClass = (status) => {
  const normalized = String(status || '').toUpperCase();
  return normalized === 'ACTIVE' || normalized === 'WAITING'
    ? 'history-status-progress'
    : 'history-status-done';
};

const History = () => {
  const { t, translateData, locale } = useI18n();
  const [history, setHistory] = useState([]);
  const [searchPage, setSearchPage] = useState(1);
  const [selectedId, setSelectedId] = useState(null);
  const navigate = useNavigate();

  const deleteEntry = async (id, e) => {
    e?.stopPropagation();
    try {
      await api.delete(`/users/me/history/${id}`);
      setHistory((prev) => prev.filter((h) => h.id_historique !== id));
      setSelectedId(null);
    } catch {
      // silencieux : rollback non nécessaire si la requête échoue
    }
  };

  useEffect(() => {
    api.get('/users/me/history')
      .then((h) => {
        setHistory(Array.isArray(h.data) ? h.data : []);
      })
      .catch(() => {
        setHistory([]);
      });
  }, []);

  useEffect(() => {
    setSearchPage(1);
  }, [history.length]);

  const searchTotalPages = Math.max(1, Math.ceil(history.length / PAGE_SIZE));

  const pagedHistory = useMemo(() => {
    const start = (searchPage - 1) * PAGE_SIZE;
    return history.slice(start, start + PAGE_SIZE);
  }, [history, searchPage]);

  return (
    <main className="page-pad history-page">
      <div className="container">
        <header className="history-head">
          <h1 className="history-title">{t('history.title')}</h1>
          <p className="history-subtitle">{t('history.subtitle')}</p>
        </header>

        <section className="history-panel card">
          <div className="history-panel-head">
            <h2><i className="fa-solid fa-magnifying-glass" /> {t('history.searchHistory')}</h2>
          </div>
          <div className="history-panel-body">
            {history.length === 0 && <div className="history-empty">{t('history.noSearchHistory')}</div>}

            {pagedHistory.map((h, i) => {
              const isSelected = selectedId === h.id_historique;
              return (
                <article
                  key={h.id_historique ?? `${h.date_his}-${i}`}
                  className="history-search-simple"
                  style={{ position: 'relative' }}
                  onClick={() => setSelectedId(isSelected ? null : h.id_historique)}
                >
                  <span className="history-query-text">{h.requete_search}</span>
                  <span className="history-search-time" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span><i className="fa-regular fa-clock" /> {formatRelativeTime(h.date_his, t, locale)}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/search?q=${encodeURIComponent(h.requete_search)}`);
                      }}
                      title={t('history.searchAgain') || 'Relancer la recherche'}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--primary)',
                        cursor: 'pointer',
                        fontSize: '14px',
                        padding: '4px 8px',
                        borderRadius: '6px',
                      }}
                    >
                      <i className="fa-solid fa-arrow-right"></i>
                    </button>
                  </span>
                  {isSelected && (
                    <button
                      type="button"
                      onClick={(e) => deleteEntry(h.id_historique, e)}
                      title={t('common.delete') || 'Supprimer'}
                      style={{
                        position: 'absolute',
                        top: '-10px',
                        right: '-10px',
                        width: '28px',
                        height: '28px',
                        borderRadius: '50%',
                        background: '#dc2626',
                        color: 'white',
                        border: '2px solid white',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 4px 10px rgba(220, 38, 38, 0.4)',
                        fontSize: '12px',
                        fontWeight: 'bold',
                        animation: 'fadeIn 0.18s ease-out',
                        zIndex: 2,
                      }}
                    >
                      <i className="fa-solid fa-xmark"></i>
                    </button>
                  )}
                </article>
              );
            })}
          </div>

          {searchTotalPages > 1 && (
            <div className="pagination history-pagination">
              <button className="btn pagination-btn" disabled={searchPage === 1} onClick={() => setSearchPage((p) => Math.max(1, p - 1))}>
                {t('common.previous')}
              </button>
              <span className="pagination-info">{t('common.page')} {searchPage} / {searchTotalPages}</span>
              <button className="btn pagination-btn" disabled={searchPage === searchTotalPages} onClick={() => setSearchPage((p) => Math.min(searchTotalPages, p + 1))}>
                {t('common.next')}
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
};

export default History;
