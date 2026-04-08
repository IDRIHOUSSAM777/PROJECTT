import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const PAGE_SIZE = 10;

const parseBooleanParam = (value) => value === '1' || value === 'true';

const filtersFromParams = (params) => ({
  type: params.get('type') || '',
  marque: params.get('marque') || '',
  fonction: params.get('fonction') || '',
  statut: params.get('statut') || '',
  etage: params.get('etage') || '',
  salle: params.get('salle') || '',
  distance: parseBooleanParam(params.get('distance')),
  distance_max: params.get('distance_max') || '',
  sort_by: params.get('sort_by') || '',
});

const buildParams = (query, filters, saveClick = false) => {
  const urlParams = new URLSearchParams();
  const value = query.trim();

  if (value) urlParams.set('q', value);
  if (filters.type) urlParams.set('type', filters.type);
  if (filters.marque) urlParams.set('marque', filters.marque);
  if (filters.fonction) urlParams.set('fonction', filters.fonction);
  if (filters.statut) urlParams.set('statut', filters.statut);
  if (filters.etage) urlParams.set('etage', filters.etage);
  if (filters.salle) urlParams.set('salle', filters.salle);
  if (filters.distance) {
    urlParams.set('distance', '1');
    if (filters.distance_max !== '' && Number(filters.distance_max) >= 0) {
      urlParams.set('distance_max', String(filters.distance_max));
    }
  }
  if (filters.sort_by) urlParams.set('sort_by', filters.sort_by);

  if (saveClick && value) {
    urlParams.set('save', '1');
  }

  return urlParams;
};

const asNumber = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const isAvailableStatus = (value) => {
  const lower = String(value || '').toLowerCase();
  return lower.includes('disponible') || lower.includes('available');
};

const getStatusClass = (status) => {
  const lower = String(status || '').toLowerCase();
  if (lower.includes('disponible') || lower.includes('available')) return 'ok';
  if (lower.includes('panne') || lower.includes('out of order') || lower.includes('aver')) return 'busy';
  return 'warning';
};

const formatDistance = (value, t, locale) => {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return t('search.unknownDistance');
  }

  if (value >= 1000) {
    const km = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value / 1000);
    return `${km} km`;
  }

  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.round(value))} m`;
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

const Search = () => {
  const { t, translateData, locale } = useI18n();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const searchBoxRef = useRef(null);

  const [query, setQuery] = useState(params.get('q') || '');
  const [filters, setFilters] = useState(filtersFromParams(params));

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [page, setPage] = useState(1);

  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);

  const [userPos, setUserPos] = useState(() => {
    try {
      const saved = localStorage.getItem('smartfind_user_pos');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [options, setOptions] = useState({
    types: [],
    marques: [],
    statuts: [],
    fonctionnalites: [],
    etages: [],
    salles: [],
  });

  const fetchResults = async (searchParams, saveHistory = false) => {
    const q = (searchParams.get('q') || '').trim();

    const urlParams = new URLSearchParams();
    const keys = ['q', 'type', 'marque', 'fonction', 'statut', 'etage', 'salle', 'distance', 'distance_max', 'sort_by'];

    keys.forEach((key) => {
      const val = searchParams.get(key);
      if (val !== null && val !== '') {
        urlParams.set(key, val);
      }
    });

    if (saveHistory && q) {
      urlParams.set('save_history', 'true');
    }

    // ALWAYS inject user details if available so backend computes precise distance_m
    if (userPos) {
      urlParams.set('user_x', userPos.x);
      urlParams.set('user_y', userPos.y);
      if (userPos.etage !== undefined && userPos.etage !== null) {
        urlParams.set('user_etage', userPos.etage);
      }
    }

    const url = urlParams.toString() ? `/search?${urlParams.toString()}` : '/search';

    setLoading(true);
    try {
      const res = await api.get(url);
      setResults(Array.isArray(res.data) ? res.data : []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api
      .get('/search/filters?active_only=true')
      .then((res) => {
        const data = res.data || {};
        setOptions({
          types: Array.isArray(data.types) ? data.types : [],
          marques: Array.isArray(data.marques) ? data.marques : [],
          statuts: Array.isArray(data.statuts) ? data.statuts : [],
          fonctionnalites: Array.isArray(data.fonctionnalites) ? data.fonctionnalites : [],
          etages: Array.isArray(data.etages) ? data.etages : [],
          salles: Array.isArray(data.salles) ? data.salles : [],
        });
      })
      .catch(() => {
        setOptions({
          types: [],
          marques: [],
          statuts: [],
          fonctionnalites: [],
          etages: [],
          salles: [],
        });
      });
  }, []);

  useEffect(() => {
    setQuery(params.get('q') || '');
    setFilters(filtersFromParams(params));
  }, [params]);

  useEffect(() => {
    const shouldSave = params.get('save') === '1';

    fetchResults(params, shouldSave).finally(() => {
      if (shouldSave) {
        const cleaned = new URLSearchParams(params);
        cleaned.delete('save');
        setParams(cleaned, { replace: true });
      }
    });
  }, [params, setParams]);

  useEffect(() => {
    const timer = setTimeout(() => {
      const next = buildParams(query, filters, false);
      const current = new URLSearchParams(params);
      current.delete('save');

      if (next.toString() !== current.toString()) {
        setParams(next, { replace: true });
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query, filters, params, setParams]);

  useEffect(() => {
    setPage(1);
  }, [results.length]);

  useEffect(() => {
    const value = query.trim();
    if (!value) {
      setSuggestions([]);
      setSuggestionsOpen(false);
      setActiveSuggestionIndex(-1);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await api.get('/search/suggest', {
          params: { q: value, limit: 8 },
        });

        const nextSuggestions = Array.isArray(res.data?.suggestions) ? res.data.suggestions : [];
        setSuggestions(nextSuggestions);
        setSuggestionsOpen(nextSuggestions.length > 0);
        setActiveSuggestionIndex(-1);
      } catch {
        setSuggestions([]);
        setSuggestionsOpen(false);
        setActiveSuggestionIndex(-1);
      }
    }, 220);

    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (searchBoxRef.current && !searchBoxRef.current.contains(event.target)) {
        setSuggestionsOpen(false);
        setActiveSuggestionIndex(-1);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const roomById = useMemo(() => {
    const map = new Map();
    options.salles.forEach((room) => {
      map.set(String(room.id_salle), room);
    });
    return map;
  }, [options.salles]);

  const availableSalles = useMemo(() => {
    if (!filters.etage) return options.salles;
    return options.salles.filter((s) => String(s.num_etage) === String(filters.etage));
  }, [options.salles, filters.etage]);

  const handleDistanceCheck = (checked) => {
    if (checked) {
      if (userPos) {
        updateFilter('distance', true);
      } else {
        alert("📍 Vous devez d'abord définir votre position sur la Carte avant de pouvoir trier par distance.");
        navigate('/map');
      }
    } else {
      updateFilter('distance', false);
    }
  };

  const updateFilter = (name, value) => {
    setFilters((prev) => {
      const next = { ...prev, [name]: value };

      if (name === 'etage' && prev.salle) {
        const salleSelected = options.salles.find((s) => String(s.id_salle) === String(prev.salle));
        if (salleSelected && String(salleSelected.num_etage) !== String(value)) {
          next.salle = '';
        }
      }

      if (name === 'distance' && !value) {
        next.distance_max = '';
      }

      return next;
    });
  };

  const resetFilters = () => {
    setFilters({
      type: '',
      marque: '',
      fonction: '',
      statut: '',
      etage: '',
      salle: '',
      distance: false,
      distance_max: '',
      sort_by: '',
    });
  };

  const submitSearch = (rawValue = query) => {
    const value = (rawValue || '').trim();
    setSuggestionsOpen(false);
    setActiveSuggestionIndex(-1);

    if (value !== query) {
      setQuery(value);
    }

    const payload = {
      query: value,
      type: filters.type,
      marque: filters.marque,
      fonction: filters.fonction,
      statut: filters.statut,
      etage: filters.etage,
      salle: filters.salle,
      distance: filters.distance,
      distance_max: filters.distance_max,
      sort_by: filters.sort_by,
      ...(filters.distance && userPos ? { user_x: userPos.x, user_y: userPos.y, user_etage: userPos.etage } : {})
    };
    console.log("🚀 Payload backend :", JSON.stringify(payload, null, 2));

    const p = buildParams(value, filters, true);
    if (filters.distance && userPos) {
      p.set('user_x', userPos.x);
      p.set('user_y', userPos.y);
      if (userPos.etage) p.set('user_etage', userPos.etage);
    }
    setParams(p);
  };

  const clickSearch = () => {
    submitSearch(query);
  };

  const chooseSuggestion = (value) => {
    submitSearch(value);
  };

  const handleInputKeyDown = (e) => {
    if (e.key === 'ArrowDown' && suggestions.length > 0) {
      e.preventDefault();
      setSuggestionsOpen(true);
      setActiveSuggestionIndex((idx) => (idx + 1) % suggestions.length);
      return;
    }

    if (e.key === 'ArrowUp' && suggestions.length > 0) {
      e.preventDefault();
      setSuggestionsOpen(true);
      setActiveSuggestionIndex((idx) => (idx <= 0 ? suggestions.length - 1 : idx - 1));
      return;
    }

    if (e.key === 'Escape') {
      setSuggestionsOpen(false);
      setActiveSuggestionIndex(-1);
      return;
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      if (suggestionsOpen && activeSuggestionIndex >= 0 && suggestions[activeSuggestionIndex]) {
        chooseSuggestion(suggestions[activeSuggestionIndex]);
      } else {
        clickSearch();
      }
    }
  };

  const activeFiltersCount = [
    filters.type,
    filters.marque,
    filters.fonction,
    filters.statut,
    filters.etage,
    filters.salle,
    filters.distance ? 'distance' : '',
    filters.distance_max,
  ].filter(Boolean).length;

  const getResultMeta = (objet) => {
    const salle = roomById.get(String(objet.id_salle));
    const salleName = salle?.nom_salle || (objet.id_salle ? `${t('common.room')} ${objet.id_salle}` : t('search.unknownRoom'));
    const etage = salle?.num_etage;

    const x = asNumber(salle?.coord_x);
    const y = asNumber(salle?.coord_y);

    let distance = null;
    if (Number.isFinite(asNumber(objet.distance_m))) {
      distance = asNumber(objet.distance_m);
    } else if (x !== null && y !== null) {
      distance = Math.hypot(x, y);
    }

    return {
      salleName,
      etage,
      distanceLabel: formatDistance(distance, t, locale),
    };
  };

  const totalPages = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const pagedResults = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return results.slice(start, start + PAGE_SIZE);
  }, [results, page]);

  return (
    <main className="page-pad">
      <div className="container">
        <section className="search-top">
          <button className="icon-btn" onClick={() => navigate(-1)}>
            <i className="fa-solid fa-arrow-left" />
          </button>

          <div className="searchbar card" ref={searchBoxRef}>
            <i className="fa-solid fa-magnifying-glass" />
            <input
              className="input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleInputKeyDown}
              onFocus={() => {
                if (suggestions.length > 0) setSuggestionsOpen(true);
              }}
              placeholder={t('search.placeholder')}
            />

            {suggestionsOpen && suggestions.length > 0 && (
              <div className="search-suggest card">
                {suggestions.map((item, idx) => (
                  <button
                    key={`${item}-${idx}`}
                    type="button"
                    className={`search-suggest-item ${idx === activeSuggestionIndex ? 'active' : ''}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => chooseSuggestion(item)}
                  >
                    <i className="fa-solid fa-magnifying-glass" />
                    <span>{item}</span>
                  </button>
                ))}
              </div>
            )}

            <button className="btn btn-primary" onClick={clickSearch}>{t('common.search')}</button>
          </div>

          <button
            className={`btn filter-toggle ${filtersOpen ? 'active' : ''}`}
            onClick={() => setFiltersOpen((v) => !v)}
          >
            <i className="fa-solid fa-sliders" />
            {t('common.filter')}
            {activeFiltersCount > 0 && <span className="filter-counter">{activeFiltersCount}</span>}
          </button>
        </section>

        {filtersOpen && (
          <section className="card filter-panel">
            <div className="filter-panel-head">
              <h3><i className="fa-solid fa-filter" /> {t('common.advancedFilters')}</h3>
              <button className="btn" onClick={resetFilters}>{t('common.reset')}</button>
            </div>

            <div className="filter-grid">
              <label className="filter-field">
                <span>{t('search.fonction')}</span>
                <select className="select" value={filters.fonction} onChange={(e) => updateFilter('fonction', e.target.value)}>
                  <option value="">{t('common.allF')}</option>
                  {options.fonctionnalites.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              </label>

              <label className="filter-field">
                <span>{t('common.type')}</span>
                <select className="select" value={filters.type} onChange={(e) => updateFilter('type', e.target.value)}>
                  <option value="">{t('common.all')}</option>
                  {options.types.map((t) => (
                    <option key={t} value={t}>{translateData('type', t)}</option>
                  ))}
                </select>
              </label>

              <label className="filter-field">
                <span>{t('common.brand')}</span>
                <select className="select" value={filters.marque} onChange={(e) => updateFilter('marque', e.target.value)}>
                  <option value="">{t('common.allF')}</option>
                  {options.marques.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>

              <label className="filter-field">
                <span>{t('common.status')}</span>
                <select className="select" value={filters.statut} onChange={(e) => updateFilter('statut', e.target.value)}>
                  <option value="">{t('common.all')}</option>
                  {(options.statuts.length > 0 ? options.statuts : ['Disponible', 'Occupé']).map((s) => (
                    <option key={s} value={s}>{translateData('status', s)}</option>
                  ))}
                </select>
              </label>

              <label className="filter-field">
                <span>{t('common.floor')}</span>
                <select className="select" value={filters.etage} onChange={(e) => updateFilter('etage', e.target.value)}>
                  <option value="">{t('common.all')}</option>
                  {options.etages.map((e) => (
                    <option key={e} value={e}>{t('search.floorPrefix')} {e}</option>
                  ))}
                </select>
              </label>

              <label className="filter-field">
                <span>{t('common.room')}</span>
                <select className="select" value={filters.salle} onChange={(e) => updateFilter('salle', e.target.value)}>
                  <option value="">{t('common.allF')}</option>
                  {availableSalles.map((s) => (
                    <option key={s.id_salle} value={s.id_salle}>
                      {s.nom_salle}
                    </option>
                  ))}
                </select>
              </label>

              <label className="filter-field filter-switch" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', justifyContent: 'space-between' }}>
                  <span>{t('search.distanceSort')} (proche → loin)</span>
                  <input
                    type="checkbox"
                    checked={filters.distance}
                    onChange={(e) => handleDistanceCheck(e.target.checked)}
                  />
                </div>
                {filters.distance && userPos && (
                  <div style={{ fontSize: '12px', color: 'var(--primary)', marginTop: '4px' }}>
                    📍 Position ({Math.round(userPos.x)}, {Math.round(userPos.y)})
                    <span
                      style={{ textDecoration: 'underline', cursor: 'pointer', marginLeft: '8px' }}
                      onClick={() => setShowMapModal(true)}
                    >
                      Modifier
                    </span>
                  </div>
                )}
              </label>

              <label className="filter-field">
                <span>{t('search.distanceMax')}</span>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  className="input"
                  placeholder={t('search.distanceExample')}
                  value={filters.distance_max}
                  onChange={(e) => updateFilter('distance_max', e.target.value)}
                  disabled={!filters.distance}
                />
              </label>
            </div>

            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button className="btn" onClick={resetFilters}>{t('common.reset')}</button>
              <button className="btn btn-primary" onClick={clickSearch}>Appliquer</button>
            </div>
          </section>
        )}



        <div className="found" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{loading ? t('search.searching') : `${results.length} ${t('search.results')}`}</span>

          <div className="sort-by-wrap" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '14px', color: 'var(--text-soft)' }}>
              {locale === 'ar' ? 'ترتيب حسب:' : locale === 'en' ? 'Sort by:' : locale === 'es' ? 'Ordenar por:' : 'Trier par :'}
            </span>
            <select
              className="select"
              style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '14px', minWidth: '150px' }}
              value={filters.sort_by}
              onChange={(e) => {
                updateFilter('sort_by', e.target.value);
                setParams(buildParams(query, { ...filters, sort_by: e.target.value }, false), { replace: true });
              }}
            >
              <option value="">{locale === 'ar' ? 'الصلة (اقتراضي)' : locale === 'en' ? 'Relevance (Default)' : locale === 'es' ? 'Relevancia (Por defecto)' : 'Pertinence (Défaut)'}</option>
              <option value="distance">{locale === 'ar' ? 'الأقرب' : locale === 'en' ? 'Nearest' : locale === 'es' ? 'Más cercano' : 'Le plus proche'}</option>
              <option value="popularity">{locale === 'ar' ? 'الأكثر استخداماً' : locale === 'en' ? 'Most Used' : locale === 'es' ? 'Más usado' : 'Le plus utilisé'}</option>
            </select>
          </div>
        </div>

        <section className="results">
          {pagedResults.map((r) => {
            const meta = getResultMeta(r);

            return (
              <article key={r.id_objet} className="card res res-card" onClick={() => navigate(`/equipment/${r.id_objet}`)} style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <div style={{ flexShrink: 0 }}>
                  {r.url_photo ? (
                    <img
                      src={`http://127.0.0.1:8000${r.url_photo}`}
                      alt={r.nom_model}
                      style={{ width: '90px', height: '90px', objectFit: 'cover', borderRadius: '10px', border: '1px solid var(--border)' }}
                    />
                  ) : (
                    <div style={{ width: '90px', height: '90px', background: 'var(--surface-2)', borderRadius: '10px', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)' }}>
                      <i className={`fa-solid ${getIcon(r.type_objet)}`} style={{ fontSize: '36px' }}></i>
                    </div>
                  )}
                </div>
                <div className="res-main" style={{ flex: 1 }}>
                  <div className="res-name">{r.nom_model}</div>
                  <div className="res-type-brand">{translateData('type', r.type_objet)} - {r.nom_marque}</div>

                  <div className="res-meta-line">
                    <i className="fa-solid fa-location-dot" />
                    <span>
                      {meta.salleName}
                      {meta.etage !== undefined && meta.etage !== null ? ` - ${t('search.floorPrefix')} ${meta.etage}` : ''}
                    </span>
                  </div>

                  <div className="res-meta-line">
                    <i className="fa-regular fa-compass" />
                    <span>{meta.distanceLabel} {t('search.distanceFromUser')}</span>
                  </div>
                </div>

                <div className="res-right">
                  <span className={`badge ${getStatusClass(r.statut)}`}>{translateData('status', r.statut)}</span>
                  <span className="res-link">{t('search.viewDetails')} <i className="fa-solid fa-angle-right" /></span>
                </div>
              </article>
            );
          })}
        </section>

        {totalPages > 1 && (
          <div className="pagination">
            <button className="btn pagination-btn" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              {t('common.previous')}
            </button>
            <span className="pagination-info">{t('common.page')} {page} / {totalPages}</span>
            <button className="btn pagination-btn" disabled={page === totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
              {t('common.next')}
            </button>
          </div>
        )}
      </div>
    </main>
  );
};

export default Search;
