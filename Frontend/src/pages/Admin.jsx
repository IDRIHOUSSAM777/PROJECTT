import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';
import AdminDashboard from './AdminDashboard';

const Admin = () => {
  const { t, locale } = useI18n();
  const navigate = useNavigate();
  const [view, setView] = useState('alerts'); // 'alerts' par défaut, 'dashboard', 'add'

  // Alerts State
  const [alertes, setAlertes] = useState([]);
  const [error, setError] = useState('');
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const [hasNewAlerts, setHasNewAlerts] = useState(false);

  // Add Object State
  const [salles, setSalles] = useState([]);
  const [types, setTypes] = useState([]);
  const [marques, setMarques] = useState([]);
  const [fonctionnalitesDispo, setFonctionnalitesDispo] = useState([]);

  // Types toujours proposés dans le dropdown, même si la BDD est vide.
  // Types et Marques par défaut (proposés même si la BDD est vide)
  const TYPES_PAR_DEFAUT = ['Ordinateur', 'Imprimante', 'Scanner', 'Projecteur', 'Réseau', 'Contrôle accès', 'Écran', 'Serveur', 'Capteur'];
  const MARQUES_PAR_DEFAUT = ['HP', 'Canon', 'Dell', 'Cisco', 'Epson', 'Lenovo', 'Logitech', 'SAMSUNG', 'ViewSonic'];
  const [formData, setFormData] = useState({
    nom_marque: '', nom_model: '', type_objet: '', description: '', mac_adresse: '', ip_adress: '', id_salle: '', pos_x: null, pos_y: null, photo: null, fonctionnalites: ''
  });

  const fetchAlertes = () => {
    api.get('/admin/alertes').then(res => setAlertes(res.data))
      .catch(err => setError(err.response?.status === 403 ? t('admin.forbidden') : t('admin.error')));
  };

  useEffect(() => {
    if (view === 'alerts') {
      fetchAlertes();
    }
    if (view === 'add') {
      if (salles.length === 0) api.get('/salles').then(res => setSalles(res.data)).catch(() => { });
      if (types.length === 0) api.get('/types').then(res => setTypes(res.data)).catch(() => { });
      if (marques.length === 0) api.get('/marques').then(res => setMarques(res.data)).catch(() => { });
      if (fonctionnalitesDispo.length === 0) api.get('/fonctionnalites').then(res => setFonctionnalitesDispo(res.data)).catch(() => { });
    }
  }, [view, t, salles.length, types.length, marques.length, fonctionnalitesDispo.length]);

  // WebSocket temps réel : rafraîchit la liste d'alertes dès qu'un objet change de statut
  useEffect(() => {
    const apiBase = api.defaults.baseURL || 'http://127.0.0.1:8000';
    const wsUrl = apiBase.replace(/^http/, 'ws') + '/ws/statuts';
    let ws;
    let retryTimer;

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => setWsConnected(true);
        ws.onclose = () => {
          setWsConnected(false);
          retryTimer = setTimeout(connect, 3000);
        };
        ws.onerror = () => {
          try { ws.close(); } catch { /* noop */ }
        };
        ws.onmessage = (evt) => {
          try {
            const data = JSON.parse(evt.data);
            if (data.event === 'subscribed') return;
            setLastEvent(data);
            if (view === 'alerts') fetchAlertes();
            else setHasNewAlerts(true);
          } catch { /* ignore non-JSON */ }
        };
      } catch {
        retryTimer = setTimeout(connect, 3000);
      }
    };

    connect();
    return () => {
      clearTimeout(retryTimer);
      if (ws) {
        ws.onclose = null;
        try { ws.close(); } catch { /* noop */ }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const deleteAlerte = async (id, e) => {
    e?.stopPropagation();
    try {
      await api.delete(`/admin/alertes/${id}`);
      setAlertes(prev => prev.filter(a => a.id_alerte !== id));
      setSelectedAlertId(null);
    } catch {
      setError(t('admin.error'));
    }
  };

  const handleMapClick = (e) => {
    const rect = e.target.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    setFormData({ ...formData, pos_x: x, pos_y: y });
  };

  const handleAddSubmit = async (e) => {
    e.preventDefault();
    try {
      const fonctionnalitesList = formData.fonctionnalites
        ? formData.fonctionnalites.split(',').map(f => f.trim()).filter(f => f)
        : [];

      const payload = {
        nom_marque: formData.nom_marque, nom_model: formData.nom_model, type_objet: formData.type_objet,
        description: formData.description, mac_adresse: formData.mac_adresse, ip_adress: formData.ip_adress,
        id_salle: parseInt(formData.id_salle), pos_x: formData.pos_x, pos_y: formData.pos_y, fonctionnalites: fonctionnalitesList
      };

      const res = await api.post('/objets', payload);
      const newObj = res.data;

      if (formData.photo) {
        const photoData = new FormData();
        photoData.append('file', formData.photo);
        await api.post(`/objets/${newObj.id_objet}/upload-photo`, photoData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }

      alert("Équipement ajouté avec succès !");
      setFormData({ nom_marque: '', nom_model: '', type_objet: '', description: '', mac_adresse: '', ip_adress: '', id_salle: '', pos_x: null, pos_y: null, photo: null, fonctionnalites: '' });
      setView('dashboard');
    } catch (err) {
      alert("Erreur lors de l'ajout. Vérifiez l'adresse MAC (unique) ou les champs obligatoires.");
    }
  };

  // --- RENDUS ---
  return (
    <main className="page-pad">
      <div className="container">

        {/* === NAVIGATION BAR === */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'white', padding: '16px 20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', border: '1px solid #e5e7eb', marginBottom: '24px', flexWrap: 'wrap', gap: '15px' }}>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              style={{ display: 'flex', alignItems: 'center', padding: '10px 20px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'alerts' ? '#2563eb' : 'transparent', color: view === 'alerts' ? 'white' : '#4b5563', position: 'relative' }}
              onClick={() => { setView('alerts'); setHasNewAlerts(false); }}
            >
              <i className="fa-solid fa-bell" style={{ marginRight: '8px' }}></i> Alertes
              {hasNewAlerts && (
                <span style={{ position: 'absolute', top: '8px', right: '12px', width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444', border: '2px solid white' }}></span>
              )}
            </button>
            <button
              style={{ display: 'flex', alignItems: 'center', padding: '10px 20px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'dashboard' ? '#2563eb' : 'transparent', color: view === 'dashboard' ? 'white' : '#4b5563' }}
              onClick={() => setView('dashboard')}
            >
              <i className="fa-solid fa-chart-pie" style={{ marginRight: '8px' }}></i> Dashboard
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              title={wsConnected ? `Temps réel actif${lastEvent ? ` — dernier: objet #${lastEvent.id_objet} → ${lastEvent.statut}` : ''}` : 'Temps réel déconnecté'}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '6px 10px', borderRadius: '999px',
                background: wsConnected ? '#dcfce7' : '#fee2e2',
                color: wsConnected ? '#166534' : '#991b1b',
                fontSize: '12px', fontWeight: 'bold',
              }}
            >
              <span style={{
                width: '8px', height: '8px', borderRadius: '50%',
                background: wsConnected ? '#16a34a' : '#dc2626',
                boxShadow: wsConnected ? '0 0 0 3px rgba(22,163,74,0.25)' : 'none',
              }} />
              {wsConnected ? 'LIVE' : 'OFFLINE'}
            </span>
            <button
              onClick={() => setView('add')}
              style={{ display: 'flex', alignItems: 'center', padding: '11px 22px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'add' ? '#14532d' : '#16a34a', color: 'white', boxShadow: '0 4px 10px rgba(22, 163, 74, 0.2)' }}
            >
              <i className="fa-solid fa-plus" style={{ marginRight: '8px' }}></i> Ajouter un équipement
            </button>
          </div>
        </div>

        {/* === CONTENU VIEWS === */}
        {view === 'dashboard' && <AdminDashboard onAddEquipementClick={() => setView('add')} />}

        {view === 'alerts' && (
          <section className="card admin">
            <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px' }}>
              <div>
                <h1 className="section-title" style={{ margin: 0 }}>Gestion des Alertes</h1>
                <p className="subtitle" style={{ margin: 0 }}>Suivi des pannes IoT et signalements utilisateur.</p>
              </div>
            </div>

            <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {error && <div className="chip chip-busy">{error}</div>}
              {alertes.length === 0 && !error && (
                <div style={{ padding: '40px', textAlign: 'center', background: '#f0fdf4', borderRadius: '12px', border: '1px solid #bbf7d0' }}>
                  <i className="fa-solid fa-check-circle" style={{ fontSize: '36px', color: '#16a34a', marginBottom: '12px' }}></i>
                  <p style={{ fontSize: '15px', fontWeight: 'bold', color: '#166534', margin: 0 }}>Aucune alerte active</p>
                </div>
              )}

              {alertes.map(a => {
                const isSelected = selectedAlertId === a.id_alerte;
                const dateStr = new Intl.DateTimeFormat(locale, {
                  dateStyle: 'short', timeStyle: 'short'
                }).format(new Date(a.date_alerte));
                return (
                  <div
                    key={a.id_alerte}
                    onClick={() => {
                      if (a.id_objet) navigate(`/equipment/${a.id_objet}`);
                      else setSelectedAlertId(isSelected ? null : a.id_alerte);
                    }}
                    title={a.id_objet ? "Consulter l'équipement" : ''}
                    style={{
                      position: 'relative',
                      padding: '16px 20px',
                      background: isSelected ? '#fef2f2' : 'white',
                      border: `1px solid ${isSelected ? '#fca5a5' : '#fee2e2'}`,
                      borderRadius: '12px',
                      cursor: a.id_objet ? 'pointer' : 'default',
                      transition: 'all 0.2s',
                      boxShadow: isSelected ? '0 4px 12px rgba(239, 68, 68, 0.15)' : '0 1px 2px rgba(0,0,0,0.04)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '16px',
                    }}
                  >
                    <div style={{
                      width: '44px', height: '44px', borderRadius: '50%',
                      background: '#fee2e2', color: '#dc2626',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <i className="fa-solid fa-triangle-exclamation" style={{ fontSize: '18px' }}></i>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, color: '#111827', fontSize: '15px' }}>{a.nom_objet}</span>
                        <span style={{
                          fontSize: '11px', fontWeight: 'bold', padding: '2px 10px',
                          borderRadius: '999px', textTransform: 'uppercase', letterSpacing: '0.04em',
                          background: a.niveau === 'Critical' ? '#fee2e2' : a.niveau === 'Warning' ? '#fef3c7' : '#dbeafe',
                          color: a.niveau === 'Critical' ? '#991b1b' : a.niveau === 'Warning' ? '#92400e' : '#1e40af',
                        }}>{a.niveau}</span>
                      </div>
                      <div style={{ fontSize: '14px', color: '#4b5563', marginBottom: '2px' }}>
                        {a.message}
                      </div>
                      <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                        <i className="fa-regular fa-clock" style={{ marginRight: '4px' }}></i>{dateStr} • {a.source}
                      </div>
                    </div>
                    <button
                      onClick={(e) => deleteAlerte(a.id_alerte, e)}
                      title="Supprimer l'alerte"
                      style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        background: '#dc2626',
                        color: 'white',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '13px',
                        flexShrink: 0,
                      }}
                    >
                      <i className="fa-solid fa-xmark"></i>
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {view === 'add' && (
          <section className="card admin">
            <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '30px' }}>
              <div>
                <h1 className="section-title" style={{ margin: 0 }}>Ajouter un équipement</h1>
                <p className="subtitle" style={{ margin: 0 }}>Renseignez les détails et placez l'objet sur le plan interactif.</p>
              </div>
            </div>

            <form onSubmit={handleAddSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '15px' }}>
                <div>
                  <input required list="marques-list" placeholder="Marque (ex: HP, Cisco)" className="input" style={{ width: '100%' }} value={formData.nom_marque} onChange={e => setFormData({ ...formData, nom_marque: e.target.value })} />
                  <datalist id="marques-list">
                    {Array.from(new Set([...MARQUES_PAR_DEFAUT, ...marques])).map((m, idx) => <option key={idx} value={m} />)}
                  </datalist>
                </div>
                <input required type="text" placeholder="Modèle (ex: LaserJet 1020)" className="input" value={formData.nom_model} onChange={e => setFormData({ ...formData, nom_model: e.target.value })} />
                <div>
                  <input required list="types-list" placeholder="Type (ex: Imprimante, Routeur)" className="input" style={{ width: '100%' }} value={formData.type_objet} onChange={e => setFormData({ ...formData, type_objet: e.target.value })} />
                  <datalist id="types-list">
                    {Array.from(new Set([...TYPES_PAR_DEFAUT, ...types])).map((t, idx) => <option key={idx} value={t} />)}
                  </datalist>
                </div>
                <input required type="text" placeholder="Adresse MAC (Obligatoire)" className="input" value={formData.mac_adresse} onChange={e => setFormData({ ...formData, mac_adresse: e.target.value })} />
                <input type="text" placeholder="Adresse IP" className="input" value={formData.ip_adress} onChange={e => setFormData({ ...formData, ip_adress: e.target.value })} />
                <div>
                  <input list="fonc-list" placeholder="Fonctionnalités (séparées par des virgules)" className="input" style={{ width: '100%' }} value={formData.fonctionnalites} onChange={e => setFormData({ ...formData, fonctionnalites: e.target.value })} />
                  <datalist id="fonc-list">
                    {fonctionnalitesDispo.map((f, idx) => <option key={idx} value={f} />)}
                  </datalist>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: 'bold', marginLeft: '4px' }}>Photo de l'objet (Optionnelle)</label>
                  <input type="file" accept="image/*" className="input" style={{ padding: '8px' }} onChange={e => setFormData({ ...formData, photo: e.target.files[0] })} />
                </div>
              </div>

              <textarea placeholder="Description optionnelle..." className="input" style={{ width: '100%', minHeight: '80px' }} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} />

              <div>
                <h3 style={{ fontSize: '1.1rem', color: '#4b5563', marginBottom: '10px', borderBottom: '1px solid #e5e7eb', paddingBottom: '5px' }}>Localisation & Placement Interactif</h3>
                <select required className="input" style={{ width: '100%', marginBottom: '15px' }} value={formData.id_salle} onChange={e => setFormData({ ...formData, id_salle: e.target.value })}>
                  <option value="">-- Sélectionnez une salle cible --</option>
                  {salles.length > 0 ? (
                    salles.map(s => <option key={s.id_salle} value={s.id_salle}>{s.nom_salle} (Étage {s.num_etage})</option>)
                  ) : (
                    <>
                      <option value="1">Salle de Réunion A</option>
                      <option value="2">Open Space IT</option>
                      <option value="3">Salle Serveurs</option>
                      <option value="4">Couloir Principal</option>
                    </>
                  )}
                </select>

                {formData.id_salle && (
                  <div style={{ textAlign: 'center' }}>
                    <p style={{ fontSize: '0.95rem', color: '#6b7280', marginBottom: '12px' }}>Cliquez sur le plan 2D pour marquer l'emplacement exact de l'appareil :</p>
                    <div
                      onClick={handleMapClick}
                      style={{
                        position: 'relative', width: '100%', height: '350px',
                        backgroundColor: '#f8fafc', border: '2px dashed #cbd5e1',
                        borderRadius: '12px', cursor: 'crosshair', overflow: 'hidden',
                        backgroundImage: 'url("https://www.transparenttextures.com/patterns/cubes.png")'
                      }}
                    >
                      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#94a3b8', pointerEvents: 'none' }}>
                        <i className="fa-solid fa-search-location" style={{ fontSize: '4rem', opacity: 0.3 }}></i>
                        <div style={{ marginTop: '15px', fontSize: '1.1rem', fontWeight: 'bold', opacity: 0.5 }}>ZONE INTERACTIVE (SALLE {formData.id_salle})</div>
                      </div>

                      {formData.pos_x !== null && formData.pos_y !== null && (
                        <div style={{
                          position: 'absolute', top: `${formData.pos_y}%`, left: `${formData.pos_x}%`,
                          transform: 'translate(-50%, -100%)', pointerEvents: 'none'
                        }}>
                          <i className="fa-solid fa-location-dot" style={{ color: '#ef4444', fontSize: '3rem', filter: 'drop-shadow(0px 8px 12px rgba(0,0,0,0.5))' }}></i>
                        </div>
                      )}
                    </div>

                    {formData.pos_x !== null && (
                      <div style={{ marginTop: '15px', fontSize: '0.95rem', color: '#059669', fontWeight: 'bold', background: '#d1fae5', padding: '12px', borderRadius: '8px', display: 'inline-block' }}>
                        📍 Position capturée : X = {formData.pos_x.toFixed(2)}%, Y = {formData.pos_y.toFixed(2)}%
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '15px', marginTop: '20px', borderTop: '1px solid #e5e7eb', paddingTop: '20px' }}>
                <button type="submit" className="btn" style={{ background: 'var(--primary)', color: 'white', padding: '15px 35px', fontSize: '1.1rem' }} disabled={!formData.id_salle || formData.pos_x === null}>
                  Enregistrer l'équipement final <i className="fa-solid fa-check" style={{ marginLeft: '8px' }}></i>
                </button>
              </div>
            </form>
          </section>
        )}

      </div>
    </main>
  );
};
export default Admin;
