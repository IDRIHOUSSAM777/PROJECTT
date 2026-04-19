import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

const defaultFilters = {
  type: '',
  fonction: '',
  marque: '',
  statut: '',
  etage: '',
  salle: '',
};

const Home = () => {
  const { t, translateData } = useI18n();
  const [query, setQuery] = useState('');
  const [categories, setCategories] = useState([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState(defaultFilters);
  const [filterOptions, setFilterOptions] = useState({
    types: [],
    fonctionnalites: [],
    marques: [],
    statuts: [],
    etages: [],
    salles: [],
  });

  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);

  const filterWrapRef = useRef(null);
  const searchWrapRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/categories')
      .then((res) => setCategories(Array.isArray(res.data) ? res.data : []))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    api.get('/search/filters')
      .then((res) => {
        const data = res.data || {};
        setFilterOptions({
          types: Array.isArray(data.types) ? data.types : [],
          fonctionnalites: Array.isArray(data.fonctionnalites) ? data.fonctionnalites : [],
          marques: Array.isArray(data.marques) ? data.marques : [],
          statuts: Array.isArray(data.statuts) ? data.statuts : [],
          etages: Array.isArray(data.etages) ? data.etages : [],
          salles: Array.isArray(data.salles) ? data.salles : [],
        });
      })
      .catch(() => {
        setFilterOptions({
          types: [],
          fonctionnalites: [],
          marques: [],
          statuts: ['Disponible', 'Occupé'],
          etages: [],
          salles: [],
        });
      });
  }, []);

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (filtersOpen && filterWrapRef.current && !filterWrapRef.current.contains(event.target)) {
        setFiltersOpen(false);
      }

      if (suggestionsOpen && searchWrapRef.current && !searchWrapRef.current.contains(event.target)) {
        setSuggestionsOpen(false);
        setActiveSuggestionIndex(-1);
      }
    };

    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => document.removeEventListener('mousedown', closeOnOutsideClick);
  }, [filtersOpen, suggestionsOpen]);

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

  const availableSalles = useMemo(() => {
    if (!filters.etage) return filterOptions.salles;
    return filterOptions.salles.filter((s) => String(s.num_etage) === String(filters.etage));
  }, [filterOptions.salles, filters.etage]);

  const statusOptions = useMemo(() => {
    if (filterOptions.statuts.length > 0) return filterOptions.statuts;
    return ['Disponible', 'Occupé'];
  }, [filterOptions.statuts]);

  const hasActiveFilters = useMemo(() => {
    return Boolean(
      filters.type ||
      filters.fonction ||
      filters.marque ||
      filters.statut ||
      filters.etage ||
      filters.salle
    );
  }, [filters]);

  const activeFilterCount = useMemo(() => {
    return [
      filters.type,
      filters.fonction,
      filters.marque,
      filters.statut,
      filters.etage,
      filters.salle,
    ].filter(Boolean).length;
  }, [filters]);

  const updateFilter = (name, value) => {
    setFilters((prev) => {
      const next = { ...prev, [name]: value };

      if (name === 'etage' && prev.salle) {
        const selectedSalle = filterOptions.salles.find((s) => String(s.id_salle) === String(prev.salle));
        if (selectedSalle && String(selectedSalle.num_etage) !== String(value)) {
          next.salle = '';
        }
      }

      return next;
    });
  };

  const buildSearchUrl = (saveHistory = false, forcedQuery = query) => {
    const params = new URLSearchParams();
    const text = (forcedQuery || '').trim();

    if (text) params.set('q', text);
    if (filters.type) params.set('type', filters.type);
    if (filters.fonction) params.set('fonction', filters.fonction);
    if (filters.marque) params.set('marque', filters.marque);
    if (filters.statut) params.set('statut', filters.statut);
    if (filters.etage) params.set('etage', filters.etage);
    if (filters.salle) params.set('salle', filters.salle);
    // Tri par distance activé par défaut (backend trie sur étage → distance → pertinence).
    params.set('distance', '1');
    if (saveHistory && text) params.set('save', '1');

    return params.toString() ? `/search?${params.toString()}` : '/search';
  };

  const handleSearch = (forcedQuery = query) => {
    const text = (forcedQuery || '').trim();
    if (!text && !hasActiveFilters) return;

    setSuggestionsOpen(false);
    setActiveSuggestionIndex(-1);

    if (text !== query) {
      setQuery(text);
    }

    navigate(buildSearchUrl(true, text));
  };

  const chooseSuggestion = (value) => {
    handleSearch(value);
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
        handleSearch(query);
      }
    }
  };

  const applyFilters = () => {
    setFiltersOpen(false);
    navigate(buildSearchUrl(Boolean(query.trim()), query));
  };

  const resetFilters = () => {
    setFilters(defaultFilters);
  };

  const getIcon = (name) => {
    const n = name.toLowerCase();
    if (n.includes('imprim')) return 'fa-print';
    if (n.includes('proj')) return 'fa-video';
    if (n.includes('scan')) return 'fa-qrcode';
    if (n.includes('ecran') || n.includes('screen')) return 'fa-display';
    if (n.includes('reseau') || n.includes('network') || n.includes('wifi')) return 'fa-wifi';
    if (n.includes('acces') || n.includes('access') || n.includes('controle')) return 'fa-door-open';
    return 'fa-cube';
  };

  const quickCategories = categories.slice(0, 4);

  return (
    <main className="page-pad">
      <div className="container">
        <section className="hero">
          <h1 className="hero-title">{t('home.heroTitle')}</h1>
          <p className="hero-sub">{t('home.heroSub')}</p>

          <div className="hero-search card" ref={searchWrapRef}>
            <i className="fa-solid fa-magnifying-glass" />
            <input
              className="input"
              placeholder={t('home.searchPlaceholder')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleInputKeyDown}
              onFocus={() => {
                if (suggestions.length > 0) setSuggestionsOpen(true);
              }}
            />

            {suggestionsOpen && suggestions.length > 0 && (
              <div className="hero-suggest card">
                {suggestions.map((item, idx) => (
                  <button
                    key={`${item}-${idx}`}
                    type="button"
                    className={`hero-suggest-item ${idx === activeSuggestionIndex ? 'active' : ''}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => chooseSuggestion(item)}
                  >
                    <i className="fa-solid fa-magnifying-glass" />
                    <span>{item}</span>
                  </button>
                ))}
              </div>
            )}

            <div className="hero-filter-wrap" ref={filterWrapRef}>
              <button
                className={`btn hero-filter-btn ${filtersOpen ? 'active' : ''}`}
                onClick={() => setFiltersOpen((v) => !v)}
                type="button"
                aria-label={t('common.filter')}
                title={t('common.filter')}
              >
                <i className="fa-solid fa-filter" />
                {activeFilterCount > 0 && <span className="hero-filter-badge">{activeFilterCount}</span>}
              </button>

              {filtersOpen && (
                <div className="hero-filter-popover card">
                  <div className="hero-filter-head">
                    <h3><i className="fa-solid fa-sliders" /> {t('common.filter')}</h3>
                  </div>

                  <div className="hero-filter-grid">
                    <label className="hero-filter-field">
                      <span>{t('common.type')}</span>
                      <select className="select" value={filters.type} onChange={(e) => updateFilter('type', e.target.value)}>
                        <option value="">{t('common.all')}</option>
                        {filterOptions.types.map((type) => (
                          <option key={type} value={type}>{translateData('type', type)}</option>
                        ))}
                      </select>
                    </label>

                    <label className="hero-filter-field">
                      <span>{t('search.fonction')}</span>
                      <select className="select" value={filters.fonction} onChange={(e) => updateFilter('fonction', e.target.value)}>
                        <option value="">{t('common.allF')}</option>
                        {filterOptions.fonctionnalites.map((fonction) => (
                          <option key={fonction} value={fonction}>{fonction}</option>
                        ))}
                      </select>
                    </label>

                    <label className="hero-filter-field">
                      <span>{t('common.brand')}</span>
                      <select className="select" value={filters.marque} onChange={(e) => updateFilter('marque', e.target.value)}>
                        <option value="">{t('common.allF')}</option>
                        {filterOptions.marques.map((marque) => (
                          <option key={marque} value={marque}>{marque}</option>
                        ))}
                      </select>
                    </label>

                    <label className="hero-filter-field">
                      <span>{t('common.status')}</span>
                      <select className="select" value={filters.statut} onChange={(e) => updateFilter('statut', e.target.value)}>
                        <option value="">{t('common.all')}</option>
                        {statusOptions.map((statut) => (
                          <option key={statut} value={statut}>{translateData('status', statut)}</option>
                        ))}
                      </select>
                    </label>

                    <label className="hero-filter-field">
                      <span>{t('common.floor')}</span>
                      <select className="select" value={filters.etage} onChange={(e) => updateFilter('etage', e.target.value)}>
                        <option value="">{t('common.all')}</option>
                        {filterOptions.etages.map((etage) => (
                          <option key={etage} value={etage}>{t('search.floorPrefix')} {etage}</option>
                        ))}
                      </select>
                    </label>

                    <label className="hero-filter-field">
                      <span>{t('common.room')}</span>
                      <select className="select" value={filters.salle} onChange={(e) => updateFilter('salle', e.target.value)}>
                        <option value="">{t('common.allF')}</option>
                        {availableSalles.map((salle) => (
                          <option key={salle.id_salle} value={salle.id_salle}>
                            {salle.nom_salle}
                          </option>
                        ))}
                      </select>
                    </label>

                  </div>

                  <div className="hero-filter-foot">
                    <button type="button" className="btn" onClick={resetFilters}>{t('common.reset')}</button>
                    <button type="button" className="btn btn-primary" onClick={applyFilters}>{t('common.apply')}</button>
                  </div>
                </div>
              )}
            </div>

            <button className="btn btn-primary" onClick={() => handleSearch(query)}>{t('common.search')}</button>
          </div>

        </section>

        <section className="quick">
          <div className="quick-head">
            <h2 className="section-title">{t('home.quickAccess')}</h2>
            <Link className="quick-link" to="/categories">{t('home.seeAll')}</Link>
          </div>

          {quickCategories.length === 0 ? (
            <div className="card" style={{ padding: '18px', color: 'var(--muted)' }}>
              {t('home.noCategories')}
            </div>
          ) : (
            <div className="quick-grid">
              {quickCategories.map((cat, i) => (
                <button
                  key={`${cat.nom}-${i}`}
                  className="quick-card card"
                  onClick={() => navigate(`/search?type=${encodeURIComponent(cat.nom)}`)}
                >
                  <div className="quick-ico"><i className={`fa-solid ${getIcon(cat.nom)}`} /></div>
                  <div className="quick-title">{translateData('type', cat.nom)}</div>
                  <div className="quick-sub">{cat.count ?? 0} {t('categories.devices')}</div>
                </button>
              ))}
            </div>
          )}
        </section>

        <footer className="footer">
          <div>{t('home.footerProject')}</div>
          <div>© 2026</div>
        </footer>
      </div>
    </main>
  );
};

export default Home;
