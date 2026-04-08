import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts';
import api from '../services/api';

export default function AdminDashboard({ onAddEquipementClick, onGoToAlerts }) {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [modal, setModal] = useState({ isOpen: false, title: '', data: [] });
    const [activeView, setActiveView] = useState('main'); // 'main' | 'analytics'
    const navigate = useNavigate();

    const openModal = (title, data) => setModal({ isOpen: true, title, data });
    const closeModal = () => setModal({ isOpen: false, title: '', data: [] });

    useEffect(() => {
        fetchStats();
    }, []);

    const fetchStats = async () => {
        setLoading(true);
        try {
            const res = await api.get('/admin/dashboard-stats');
            setStats(res.data);
        } catch (error) {
            console.error("Erreur de récupération des analytiques :", error);
        } finally {
            setLoading(false);
        }
    };

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload;
            return (
                <div style={{ background: 'white', border: '1px solid #e5e7eb', padding: '12px 16px', borderRadius: '12px', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}>
                    <p style={{ fontWeight: 'bold', color: '#1f2937', margin: '0 0 4px 0', fontSize: '15px' }}>{data.salle}</p>
                    {data.etage !== '-' && <p style={{ fontSize: '13px', color: '#6b7280', margin: '0 0 8px 0', fontWeight: '500' }}>Étage : {data.etage}</p>}
                    <p style={{ fontSize: '14px', fontWeight: 'bold', color: '#3b82f6', margin: 0 }}>
                        {payload[0].value} équipement{payload[0].value !== 1 ? 's' : ''}
                    </p>
                </div>
            );
        }
        return null;
    };

    if (loading) {
        return <div className="flex justify-center flex-col items-center h-64 text-gray-500 font-medium"><i className="fa-solid fa-spinner fa-spin text-3xl mb-4"></i> Chargement des données en direct...</div>;
    }

    if (!stats) {
        return <div className="flex justify-center items-center h-64 text-red-500 font-medium">Erreur lors du chargement des analytiques.</div>;
    }

    // =========================================================
    // VUE 1 : ANALYSE DES RÉSERVATIONS (DRILL-DOWN)
    // =========================================================
    if (activeView === 'analytics') {
        return (
            <div className="animate-fade-in fade-in" style={{ animation: 'fadeIn 0.3s ease-out' }}>
                {/* Header Back Button */}
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: '24px' }}>
                    <button onClick={() => setActiveView('main')} style={{ background: 'white', border: '1px solid #e5e7eb', padding: '10px 16px', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.05)', transition: 'all 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'} onMouseLeave={e => e.currentTarget.style.background = 'white'}>
                        <i className="fa-solid fa-arrow-left"></i> Dashboard
                    </button>
                    <h2 style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '0 0 0 20px' }}>Analyse des Réservations <span style={{ color: '#6b7280', fontWeight: 'normal', fontSize: '16px' }}>(30 derniers jours)</span></h2>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '24px' }}>
                    {/* Bar Chart Horizontal pour le Top 10 */}
                    <div style={{ background: 'white', padding: '24px', borderRadius: '16px', border: '1px solid #e5e7eb' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', marginBottom: '16px', margin: 0 }}><i className="fa-solid fa-ranking-star mr-2 text-yellow-500"></i> Classement Top 10</h3>
                        <div style={{ height: '400px' }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={stats.events.top_10_mensuel} layout="vertical" margin={{ top: 5, right: 30, left: 40, bottom: 5 }}>
                                    <XAxis type="number" hide />
                                    <YAxis type="category" dataKey="modele" tick={{ fontSize: 13, fontWeight: 'bold', fill: '#4b5563' }} axisLine={false} tickLine={false} />
                                    <Tooltip cursor={{ fill: '#f3f4f6' }} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }} />
                                    <Bar dataKey="reservations" fill="#a855f7" radius={[0, 6, 6, 0]} barSize={24}>
                                        {
                                            stats.events.top_10_mensuel.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={index === 0 ? '#ca8a04' : index === 1 ? '#9ca3af' : index === 2 ? '#b45309' : '#a855f7'} />
                                            ))
                                        }
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Line Chart Tendance */}
                    <div style={{ background: 'white', padding: '24px', borderRadius: '16px', border: '1px solid #e5e7eb' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', marginBottom: '16px', margin: 0 }}><i className="fa-solid fa-chart-line mr-2 text-blue-500"></i> Tendance temporelle</h3>
                        <div style={{ height: '400px', marginTop: '10px' }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={stats.charts.reservation_trend} margin={{ top: 5, right: 20, left: -20, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                                    <XAxis dataKey="date" tick={{ fontSize: 13, fill: '#6b7280' }} axisLine={false} tickLine={false} tickFormatter={(val) => new Date(val).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })} />
                                    <YAxis allowDecimals={false} tick={{ fontSize: 13, fill: '#6b7280', fontWeight: 'bold' }} axisLine={false} tickLine={false} />
                                    <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }} labelFormatter={(label) => new Date(label).toLocaleDateString()} />
                                    <Line type="monotone" dataKey="count" name="Réservations" stroke="#3b82f6" strokeWidth={3} dot={{ r: 4, strokeWidth: 2 }} activeDot={{ r: 6 }} />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // =========================================================
    // VUE 0 : MAIN DASHBOARD
    // =========================================================
    return (
        <div className="space-y-6 animate-fade-in fade-in" style={{ animation: 'fadeIn 0.4s ease-out' }}>
            {/* COUCHE 1 : CARTES KPI */}
            <div className="grid grid-cols-1 md:grid-cols-6 gap-4" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '16px' }}>
                <div onClick={() => openModal('Tous les Utilisateurs', stats.details.users)} style={{ cursor: 'pointer', background: 'white', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#6b7280', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Utilisateurs</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '4px 0 0 0' }}>{stats.kpi.total_users}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>
                        <i className="fa-solid fa-users"></i>
                    </div>
                </div>
                <div onClick={() => openModal('Tous les Équipements', stats.details.equipments)} style={{ cursor: 'pointer', background: 'white', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#6b7280', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Équipements</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '4px 0 0 0' }}>{stats.kpi.total_equipments}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#eef2ff', color: '#4f46e5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>
                        <i className="fa-solid fa-boxes-stacked"></i>
                    </div>
                </div>
                <div onClick={() => openModal('Équipements Disponibles', stats.details.equipments.filter(e => e.statut === 'Disponible'))} style={{ cursor: 'pointer', background: 'white', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', borderLeft: '4px solid #10b981', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#059669', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Disponibles</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '4px 0 0 0' }}>{stats.kpi.available_count}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#d1fae5', color: '#059669', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>
                        <i className="fa-solid fa-check"></i>
                    </div>
                </div>
                <div onClick={() => openModal('Équipements Occupés', stats.details.equipments.filter(e => e.statut.toLowerCase().includes('occup') || e.statut.toLowerCase().includes('reserv')))} style={{ cursor: 'pointer', background: 'white', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', borderLeft: '4px solid #f59e0b', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#d97706', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Occupés</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '4px 0 0 0' }}>{stats.kpi.occupied_count}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#fef3c7', color: '#d97706', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>
                        <i className="fa-solid fa-lock"></i>
                    </div>
                </div>
                <div onClick={() => openModal('Équipements en Panne', stats.details.equipments.filter(e => e.statut.toLowerCase().includes('panne')))} style={{ cursor: 'pointer', background: 'white', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', borderLeft: '4px solid #ef4444', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#dc2626', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>En Panne</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#1f2937', margin: '4px 0 0 0' }}>{stats.kpi.broken_count}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#fee2e2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px' }}>
                        <i className="fa-solid fa-triangle-exclamation"></i>
                    </div>
                </div>
                {/* 6ème Carte : Top Réservations (Couleur Violet/Gold) */}
                <div onClick={() => setActiveView('analytics')} style={{ cursor: 'pointer', background: 'linear-gradient(135deg, #fdf4ff 0%, #f3e8ff 100%)', padding: '20px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)', border: '1px solid #e9d5ff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', transition: 'transform 0.2s' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'} onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}>
                    <div>
                        <p style={{ fontSize: '11px', color: '#9333ea', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Top Réservations</p>
                        <p style={{ fontSize: '24px', fontWeight: '900', color: '#7e22ce', margin: '4px 0 0 0' }}>{stats.events.top_10_mensuel ? stats.events.top_10_mensuel.length : 0}</p>
                    </div>
                    <div style={{ width: '40px', height: '40px', borderRadius: '50%', background: '#ffffff', color: '#9333ea', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
                        <i className="fa-solid fa-trophy text-yellow-500"></i>
                    </div>
                </div>
            </div>

            {/* COUCHE 2 : GRAPHIQUES */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '24px', marginTop: '24px' }}>

                {/* Graphique Statuts (PieChart) */}
                <div style={{ background: 'white', padding: '24px', borderRadius: '16px', border: '1px solid #e5e7eb' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', marginBottom: '16px', margin: 0 }}>Répartition globale</h3>
                    <div style={{ height: '280px', display: 'flex', justifyContent: 'center' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={stats.charts.status_pie} cx="50%" cy="50%" innerRadius={70} outerRadius={95} paddingAngle={5} dataKey="value">
                                    {stats.charts.status_pie.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '16px', marginTop: '8px' }}>
                        {stats.charts.status_pie.map((s, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', fontSize: '14px', fontWeight: 'bold', color: '#4b5563' }}>
                                <span style={{ width: '12px', height: '12px', borderRadius: '50%', marginRight: '8px', backgroundColor: s.color }}></span>
                                {s.name} ({s.value})
                            </div>
                        ))}
                    </div>
                </div>

                {/* Graphique Salles (BarChart) */}
                <div style={{ background: 'white', padding: '24px', borderRadius: '16px', border: '1px solid #e5e7eb', gridColumn: 'span 2' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', marginBottom: '16px', margin: 0 }}>Équipements par salle</h3>
                    <div style={{ height: '320px', marginTop: '20px' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stats.charts.room_bars} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                <XAxis dataKey="salle" tick={false} axisLine={false} tickLine={false} />
                                <YAxis allowDecimals={false} tick={{ fontSize: 13, fill: '#6b7280', fontWeight: 'bold' }} axisLine={false} tickLine={false} />
                                <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f3f4f6' }} />
                                <Bar dataKey="count" fill="#3b82f6" radius={[6, 6, 0, 0]} barSize={45} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* COUCHE 3 : ÉVÉNEMENTS EN DIRECT (LISTES RÉDUITES SANS TOP 10) */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '24px', marginTop: '24px' }}>

                {/* Liste : Alertes Actives */}
                <div style={{ background: 'white', borderRadius: '16px', border: '1px solid #fecaca', overflow: 'hidden' }}>
                    <div style={{ background: '#fef2f2', padding: '16px 24px', borderBottom: '1px solid #fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: '900', color: '#991b1b', margin: 0 }}><i className="fa-solid fa-triangle-exclamation mr-2"></i> Alertes à traiter</h3>
                        <span style={{ background: '#dc2626', color: 'white', fontSize: '12px', fontWeight: 'bold', padding: '4px 12px', borderRadius: '999px' }}>{stats.events.active_alerts.length}</span>
                    </div>
                    <div>
                        {stats.events.active_alerts.length > 0 ? (
                            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                                {stats.events.active_alerts.map((alert, i) => (
                                    <li key={i} style={{ padding: '20px 24px', display: 'flex', alignItems: 'flex-start', gap: '16px', borderBottom: '1px solid #f3f4f6' }}>
                                        <div style={{ width: '10px', height: '10px', marginTop: '6px', borderRadius: '50%', background: '#ef4444' }}></div>
                                        <div>
                                            <p style={{ fontSize: '15px', fontWeight: 'bold', color: '#111827', margin: 0 }}>{alert.message}</p>
                                            <p style={{ fontSize: '13px', fontWeight: '500', color: '#6b7280', margin: '4px 0 0 0' }}>{new Date(alert.date).toLocaleString()} • Gravité : <span style={{ color: '#dc2626' }}>{alert.niveau}</span></p>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <div style={{ padding: '40px', textAlign: 'center' }}>
                                <i className="fa-solid fa-check-circle" style={{ fontSize: '36px', color: '#4ade80', marginBottom: '12px' }}></i>
                                <p style={{ fontSize: '15px', fontWeight: 'bold', color: '#6b7280', margin: 0 }}>Aucune alerte en cours</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Liste : Dernières Réservations */}
                <div style={{ background: 'white', borderRadius: '16px', border: '1px solid #e5e7eb', overflow: 'hidden' }}>
                    <div style={{ background: '#f9fafb', padding: '16px 24px', borderBottom: '1px solid #f3f4f6' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: '900', color: '#1f2937', margin: 0 }}><i className="fa-regular fa-calendar-check mr-2"></i> Dernières Transactions</h3>
                    </div>
                    <div>
                        {stats.events.recent_reservations.length > 0 ? (
                            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                                {stats.events.recent_reservations.map((res, i) => (
                                    <li key={i} style={{ padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #f3f4f6' }}>
                                        <div>
                                            <p style={{ fontSize: '15px', fontWeight: 'bold', color: '#111827', margin: 0 }}>{res.user}</p>
                                            <p style={{ fontSize: '13px', fontWeight: '500', color: '#6b7280', margin: '4px 0 0 0' }}>Cible : <span style={{ fontWeight: 'bold', color: '#374151' }}>{res.object_model}</span></p>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <span style={{ fontSize: '11px', background: '#e0e7ff', color: '#3730a3', padding: '4px 10px', borderRadius: '6px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{res.status}</span>
                                            <p style={{ fontSize: '12px', fontWeight: '500', color: '#9ca3af', margin: '8px 0 0 0' }}>{new Date(res.date).toLocaleDateString()}</p>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p style={{ padding: '40px', fontSize: '15px', fontWeight: 'bold', color: '#6b7280', textAlign: 'center', margin: 0 }}>Aucune réservation récente.</p>
                        )}
                    </div>
                </div>

            </div>

            {/* MODAL POUR AFFICHER LES DÉTAILS BDD */}
            {modal.isOpen && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '20px', backdropFilter: 'blur(3px)' }} onClick={closeModal}>
                    <div style={{ background: 'white', borderRadius: '16px', padding: '0', width: '100%', maxWidth: '900px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)' }} onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px 24px', borderBottom: '1px solid #e5e7eb', background: '#f8fafc', borderTopLeftRadius: '16px', borderTopRightRadius: '16px' }}>
                            <h2 style={{ fontSize: '20px', fontWeight: '900', color: '#1f2937', margin: 0 }}>{modal.title} ({modal.data.length})</h2>
                            <button onClick={closeModal} style={{ background: '#e2e8f0', border: 'none', width: '32px', height: '32px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '20px', cursor: 'pointer', color: '#475569', transition: 'all 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = '#cbd5e1'} onMouseLeave={e => e.currentTarget.style.background = '#e2e8f0'}>&times;</button>
                        </div>

                        <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
                            {modal.data.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '60px 0' }}>
                                    <i className="fa-solid fa-folder-open" style={{ fontSize: '48px', color: '#cbd5e1', margin: '0 0 16px 0' }}></i>
                                    <p style={{ color: '#64748b', fontSize: '16px', fontWeight: 'bold', margin: 0 }}>Aucune donnée disponible.</p>
                                </div>
                            ) : (
                                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                                    <thead>
                                        {modal.title.includes('Utilisateurs') ? (
                                            <tr style={{ color: '#64748b', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '2px solid #e2e8f0' }}>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Nom Complet</th>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Email</th>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Rôle</th>
                                            </tr>
                                        ) : (
                                            <tr style={{ color: '#64748b', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '2px solid #e2e8f0' }}>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Marque & Modèle</th>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Adresses Réseau</th>
                                                <th style={{ padding: '0 12px 12px 12px' }}>Statut</th>
                                            </tr>
                                        )}
                                    </thead>
                                    <tbody>
                                        {modal.data.map((item, i) => (
                                            modal.title.includes('Utilisateurs') ? (
                                                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.2s' }} onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                                                    <td style={{ padding: '16px 12px', fontWeight: 'bold', color: '#0f172a' }}>{item.nom} {item.prenom}</td>
                                                    <td style={{ padding: '16px 12px', color: '#475569' }}>{item.email}</td>
                                                    <td style={{ padding: '16px 12px' }}><span style={{ padding: '4px 10px', background: '#f1f5f9', color: '#334155', borderRadius: '6px', fontSize: '12px', fontWeight: 'bold' }}>{item.role}</span></td>
                                                </tr>
                                            ) : (
                                                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.2s', cursor: 'pointer' }} onClick={() => navigate(`/equipment/${item.id}`)} onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'} onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                                                    <td style={{ padding: '16px 12px', fontWeight: 'bold', color: '#0f172a' }}>{item.marque} <span style={{ color: '#64748b', fontWeight: 'normal' }}>{item.modele}</span></td>
                                                    <td style={{ padding: '16px 12px', color: '#475569', fontSize: '13px', fontFamily: 'monospace' }}>
                                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                            <span><i className="fa-solid fa-microchip" style={{ width: '16px', color: '#94a3b8' }}></i> {item.mac || 'N/A'}</span>
                                                            {item.ip && <span><i className="fa-solid fa-network-wired" style={{ width: '16px', color: '#94a3b8' }}></i> {item.ip}</span>}
                                                        </div>
                                                    </td>
                                                    <td style={{ padding: '16px 12px' }}>
                                                        <span style={{
                                                            padding: '6px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 'bold', display: 'inline-flex', alignItems: 'center', gap: '6px',
                                                            background: item.statut.toLowerCase().includes('dispo') ? '#dcfce7' : item.statut.toLowerCase().includes('occup') ? '#fef3c7' : '#fee2e2',
                                                            color: item.statut.toLowerCase().includes('dispo') ? '#166534' : item.statut.toLowerCase().includes('occup') ? '#92400e' : '#991b1b'
                                                        }}>
                                                            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: item.statut.toLowerCase().includes('dispo') ? '#22c55e' : item.statut.toLowerCase().includes('occup') ? '#f59e0b' : '#ef4444' }}></div>
                                                            {item.statut}
                                                        </span>
                                                    </td>
                                                </tr>
                                            )
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
