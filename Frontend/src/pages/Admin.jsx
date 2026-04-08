import { useState, useEffect } from 'react';
import api from '../services/api';
import { useI18n } from '../i18n';
import AdminDashboard from './AdminDashboard';

const Admin = () => {
  const { t, locale } = useI18n();
  const [view, setView] = useState('dashboard'); // 'dashboard', 'alerts', 'add'

  // Alerts State
  const [alertes, setAlertes] = useState([]);
  const [error, setError] = useState('');

  // Add Object State
  const [salles, setSalles] = useState([]);
  const [types, setTypes] = useState([]);
  const [fonctionnalitesDispo, setFonctionnalitesDispo] = useState([]);
  const [formData, setFormData] = useState({
    nom_marque: '', nom_model: '', type_objet: '', description: '', mac_adresse: '', ip_adress: '', id_salle: '', pos_x: null, pos_y: null, photo: null, fonctionnalites: ''
  });

  useEffect(() => {
    if (view === 'alerts' && alertes.length === 0) {
      api.get('/admin/alertes').then(res => setAlertes(res.data))
        .catch(err => setError(err.response?.status === 403 ? t('admin.forbidden') : t('admin.error')));
    }
    if (view === 'add') {
      if (salles.length === 0) api.get('/salles').then(res => setSalles(res.data)).catch(() => { });
      if (types.length === 0) api.get('/types').then(res => setTypes(res.data)).catch(() => { });
      if (fonctionnalitesDispo.length === 0) api.get('/fonctionnalites').then(res => setFonctionnalitesDispo(res.data)).catch(() => { });
    }
  }, [view, t, alertes.length, salles.length, types.length, fonctionnalitesDispo.length]);

  const resolveAlerte = async (id) => {
    if (!window.confirm(t('admin.resolveConfirm'))) return;
    try {
      await api.put(`/admin/alertes/${id}/resolve`, { nouveau_statut_objet: "Disponible" });
      setAlertes(alertes.filter(a => a.id_alerte !== id));
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
              style={{ display: 'flex', alignItems: 'center', padding: '10px 20px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'dashboard' ? '#2563eb' : 'transparent', color: view === 'dashboard' ? 'white' : '#4b5563' }}
              onClick={() => setView('dashboard')}
            >
              <i className="fa-solid fa-chart-pie" style={{ marginRight: '8px' }}></i> Dashboard
            </button>
            <button
              style={{ display: 'flex', alignItems: 'center', padding: '10px 20px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'alerts' ? '#2563eb' : 'transparent', color: view === 'alerts' ? 'white' : '#4b5563' }}
              onClick={() => setView('alerts')}
            >
              <i className="fa-solid fa-bell" style={{ marginRight: '8px' }}></i> Alertes
            </button>
          </div>

          <button
            onClick={() => setView('add')}
            style={{ display: 'flex', alignItems: 'center', padding: '11px 22px', borderRadius: '12px', fontWeight: 'bold', border: 'none', cursor: 'pointer', transition: 'all 0.2s', background: view === 'add' ? '#14532d' : '#16a34a', color: 'white', boxShadow: '0 4px 10px rgba(22, 163, 74, 0.2)' }}
          >
            <i className="fa-solid fa-plus" style={{ marginRight: '8px' }}></i> Ajouter un équipement
          </button>
        </div>

        {/* === CONTENU VIEWS === */}
        {view === 'dashboard' && <AdminDashboard onAddEquipementClick={() => setView('add')} onGoToAlerts={() => setView('alerts')} />}

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
              {alertes.length === 0 && !error && <div className="chip chip-done">{t('admin.noAlerts')}</div>}

              {alertes.map(a => (
                <div key={a.id_alerte} className="row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className="row-left" style={{ width: '100%' }}>
                    <div className="ico" style={{ background: '#fef3f2', color: 'var(--danger)' }}><i className="fa-solid fa-triangle-exclamation"></i></div>
                    <div>
                      <div className="title">{a.message}</div>
                      <div className="sub">{a.nom_objet} • {new Intl.DateTimeFormat(locale).format(new Date(a.date_alerte))}</div>
                    </div>
                  </div>
                  <button className="btn btn-primary" style={{ padding: '8px 16px' }} onClick={() => resolveAlerte(a.id_alerte)}>
                    Résoudre
                  </button>
                </div>
              ))}
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
                <input required type="text" placeholder="Marque (ex: HP, Cisco)" className="input" value={formData.nom_marque} onChange={e => setFormData({ ...formData, nom_marque: e.target.value })} />
                <input required type="text" placeholder="Modèle (ex: LaserJet 1020)" className="input" value={formData.nom_model} onChange={e => setFormData({ ...formData, nom_model: e.target.value })} />
                <div>
                  <input required list="types-list" placeholder="Type (ex: Imprimante, Routeur)" className="input" style={{ width: '100%' }} value={formData.type_objet} onChange={e => setFormData({ ...formData, type_objet: e.target.value })} />
                  <datalist id="types-list">
                    {types.map((t, idx) => <option key={idx} value={t} />)}
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
