import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import api from '../services/api';

const EditEquipment = () => {
    const { id } = useParams();
    const navigate = useNavigate();

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [salles, setSalles] = useState([]);
    const [types, setTypes] = useState([]);
    const [fonctionnalitesDispo, setFonctionnalitesDispo] = useState([]);
    const [formData, setFormData] = useState({
        nom_marque: '', nom_model: '', type_objet: '', description: '', mac_adresse: '', ip_adress: '', id_salle: '', pos_x: null, pos_y: null, photo: null, fonctionnalites: '', statut: ''
    });

    useEffect(() => {
        const fetchSelects = async () => {
            try {
                const [sRes, tRes, fRes] = await Promise.all([
                    api.get('/salles'),
                    api.get('/types'),
                    api.get('/fonctionnalites')
                ]);
                setSalles(sRes.data);
                setTypes(tRes.data);
                setFonctionnalitesDispo(fRes.data);
            } catch (err) {
                console.error(err);
            }
        };

        const fetchEquipment = async () => {
            try {
                const res = await api.get(`/objets/${id}`);
                const eq = res.data;
                setFormData({
                    nom_marque: eq.nom_marque || '',
                    nom_model: eq.nom_model || '',
                    type_objet: eq.type_objet || '',
                    description: eq.description || '',
                    mac_adresse: eq.mac_adresse || '',
                    ip_adress: eq.ip_adress || '',
                    id_salle: eq.id_salle || '',
                    pos_x: eq.pos_x,
                    pos_y: eq.pos_y,
                    photo: null,
                    statut: eq.statut || '',
                    fonctionnalites: eq.fonctionnalites ? eq.fonctionnalites.map(f => f.nom).join(', ') : ''
                });
                setLoading(false);
            } catch (err) {
                setError('Erreur lors du chargement de l\'équipement');
                setLoading(false);
            }
        };

        fetchSelects().then(fetchEquipment);
    }, [id]);

    const handleMapClick = (e) => {
        const rect = e.target.getBoundingClientRect();
        const x = ((e.clientX - rect.left) / rect.width) * 100;
        const y = ((e.clientY - rect.top) / rect.height) * 100;
        setFormData({ ...formData, pos_x: x, pos_y: y });
    };

    const handleUpdateSubmit = async (e) => {
        e.preventDefault();
        try {
            const fonctionnalitesList = formData.fonctionnalites
                ? formData.fonctionnalites.split(',').map(f => f.trim()).filter(f => f)
                : [];

            const payload = {
                nom_marque: formData.nom_marque,
                nom_model: formData.nom_model,
                type_objet: formData.type_objet,
                description: formData.description,
                mac_adresse: formData.mac_adresse,
                ip_adress: formData.ip_adress,
                id_salle: parseInt(formData.id_salle),
                pos_x: formData.pos_x,
                pos_y: formData.pos_y,
                statut: formData.statut,
                fonctionnalites: fonctionnalitesList
            };

            await api.put(`/objets/${id}`, payload);

            if (formData.photo) {
                const photoData = new FormData();
                photoData.append('file', formData.photo);
                await api.post(`/objets/${id}/upload-photo`, photoData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                });
            }

            alert("Équipement modifié avec succès !");
            navigate(`/equipment/${id}`);
        } catch (err) {
            alert("Erreur lors de la modification. Vérifiez l'adresse MAC (unique) ou les champs obligatoires.");
        }
    };

    if (loading) return <div className="page-pad container text-center">Chargement...</div>;
    if (error) return <div className="page-pad container text-center text-red-500">{error}</div>;

    return (
        <main className="page-pad">
            <div className="container">
                <section className="card admin">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '30px' }}>
                        <button className="icon-btn" onClick={() => navigate(-1)} style={{ background: '#f1f5f9' }}>
                            <i className="fa-solid fa-arrow-left" />
                        </button>
                        <div>
                            <h1 className="section-title" style={{ margin: 0 }}>Modifier un équipement</h1>
                            <p className="subtitle" style={{ margin: 0 }}>Mettez à jour les détails ou l'emplacement de l'objet.</p>
                        </div>
                    </div>

                    <form onSubmit={handleUpdateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '15px' }}>
                            <input required type="text" placeholder="Marque (ex: HP, Cisco)" className="input" value={formData.nom_marque} onChange={e => setFormData({ ...formData, nom_marque: e.target.value })} />
                            <input required type="text" placeholder="Modèle (ex: LaserJet 1020)" className="input" value={formData.nom_model} onChange={e => setFormData({ ...formData, nom_model: e.target.value })} />
                            <div>
                                <input required list="types-list" placeholder="Type (ex: Imprimante, Routeur)" className="input" style={{ width: '100%' }} value={formData.type_objet} onChange={e => setFormData({ ...formData, type_objet: e.target.value })} />
                                <datalist id="types-list">
                                    {types.map((t, idx) => <option key={idx} value={t} />)}
                                </datalist>
                            </div>

                            <select required className="input" value={formData.statut} onChange={e => setFormData({ ...formData, statut: e.target.value })}>
                                <option value="">-- Statut de l'appareil --</option>
                                <option value="Disponible">🟢 Disponible</option>
                                <option value="Occupé">🟠 Occupé</option>
                                <option value="Panne">🔴 En Panne</option>
                                <option value="Réservé">🔵 Réservé</option>
                            </select>

                            <input required type="text" placeholder="Adresse MAC (Obligatoire)" className="input" value={formData.mac_adresse} onChange={e => setFormData({ ...formData, mac_adresse: e.target.value })} />
                            <input type="text" placeholder="Adresse IP" className="input" value={formData.ip_adress} onChange={e => setFormData({ ...formData, ip_adress: e.target.value })} />
                            <div>
                                <input list="fonc-list" placeholder="Fonctionnalités (séparées par des virgules)" className="input" style={{ width: '100%' }} value={formData.fonctionnalites} onChange={e => setFormData({ ...formData, fonctionnalites: e.target.value })} />
                                <datalist id="fonc-list">
                                    {fonctionnalitesDispo.map((f, idx) => <option key={idx} value={f} />)}
                                </datalist>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                <label style={{ fontSize: '0.85rem', color: '#6b7280', fontWeight: 'bold', marginLeft: '4px' }}>Nouvelle photo (laisse vide pour conserver l'actuelle)</label>
                                <input type="file" accept="image/*" className="input" style={{ padding: '8px' }} onChange={e => setFormData({ ...formData, photo: e.target.files[0] })} />
                            </div>
                        </div>

                        <textarea placeholder="Description optionnelle..." className="input" style={{ width: '100%', minHeight: '80px' }} value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} />

                        <div>
                            <h3 style={{ fontSize: '1.1rem', color: '#4b5563', marginBottom: '10px', borderBottom: '1px solid #e5e7eb', paddingBottom: '5px' }}>Localisation & Placement Interactif</h3>
                            <select required className="input" style={{ width: '100%', marginBottom: '15px' }} value={formData.id_salle} onChange={e => setFormData({ ...formData, id_salle: e.target.value })}>
                                <option value="">-- Sélectionnez une salle cible --</option>
                                {salles.map(s => <option key={s.id_salle} value={s.id_salle}>{s.nom_salle} (Étage {s.num_etage})</option>)}
                            </select>

                            {formData.id_salle && (
                                <div style={{ textAlign: 'center' }}>
                                    <p style={{ fontSize: '0.95rem', color: '#6b7280', marginBottom: '12px' }}>Cliquez sur le plan 2D pour marquer le nouvel emplacement :</p>
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

                                        {typeof formData.pos_x === 'number' && typeof formData.pos_y === 'number' && (
                                            <div style={{
                                                position: 'absolute', top: `${formData.pos_y}%`, left: `${formData.pos_x}%`,
                                                transform: 'translate(-50%, -100%)', pointerEvents: 'none'
                                            }}>
                                                <i className="fa-solid fa-location-dot" style={{ color: '#ef4444', fontSize: '3rem', filter: 'drop-shadow(0px 8px 12px rgba(0,0,0,0.5))' }}></i>
                                            </div>
                                        )}
                                    </div>

                                    {typeof formData.pos_x === 'number' && typeof formData.pos_y === 'number' && (
                                        <div style={{ marginTop: '15px', fontSize: '0.95rem', color: '#059669', fontWeight: 'bold', background: '#d1fae5', padding: '12px', borderRadius: '8px', display: 'inline-block' }}>
                                            📍 Position capturée : X = {formData.pos_x.toFixed(2)}%, Y = {formData.pos_y.toFixed(2)}%
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '15px', marginTop: '20px', borderTop: '1px solid #e5e7eb', paddingTop: '20px' }}>
                            <button type="submit" className="btn btn-primary" style={{ background: 'var(--primary)', color: 'white', padding: '15px 35px', fontSize: '1.1rem' }} disabled={!formData.id_salle || formData.pos_x === null}>
                                Mettre à jour l'équipement <i className="fa-solid fa-check" style={{ marginLeft: '8px' }}></i>
                            </button>
                        </div>
                    </form>
                </section>
            </div>
        </main>
    );
};
export default EditEquipment;
