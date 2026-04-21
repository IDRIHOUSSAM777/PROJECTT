import { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useI18n } from '../i18n';

// ========================================================
//  PREMIUM CAD FLOOR PLAN — SmartFind Enterprise Map
// ========================================================

const Carte = () => {
    const { t, translateData } = useI18n();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const paramEtage = searchParams.get('etage');
    const paramObjet = searchParams.get('objet');

    const [etages, setEtages] = useState([]);
    const [salles, setSalles] = useState([]);
    const [selectedEtage, setSelectedEtage] = useState(null);
    const [objets, setObjets] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selectedObjet, setSelectedObjet] = useState(null);
    const [selectedRoom, setSelectedRoom] = useState(null);
    const [hoveredPin, setHoveredPin] = useState(null);

    const [userLocation, setUserLocation] = useState(() => {
        try {
            const saved = localStorage.getItem('smartfind_user_pos');
            return saved ? JSON.parse(saved) : null;
        } catch { return null; }
    });
    const [isSettingLocation, setIsSettingLocation] = useState(false);
    const [tempUserLocation, setTempUserLocation] = useState(null);

    const confirmUserLocation = () => {
        if (!tempUserLocation) return;
        setUserLocation(tempUserLocation);
        localStorage.setItem('smartfind_user_pos', JSON.stringify(tempUserLocation));
        setIsSettingLocation(false);
    };

    const handleSVGClick = (e) => {
        if (!isSettingLocation) return;
        // SVG coordinate mapping
        const svg = e.currentTarget.closest('svg');
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        const svgP = pt.matrixTransform(svg.getScreenCTM().inverse());
        setTempUserLocation({ x: svgP.x, y: svgP.y, etage: selectedEtage });
    };

    // ── DATA FROM BACKEND API ──────────────────────
    useEffect(() => {
        api.get('/search/filters')
            .then((res) => {
                const floorList = res.data?.etages || [];
                setEtages(floorList);
                setSalles(res.data?.salles || []);
                // Pré-sélectionne l'étage depuis l'URL (?etage=…) si disponible, sinon le 1er
                const wantedEtage = paramEtage != null ? parseInt(paramEtage, 10) : null;
                const initialEtage = (wantedEtage != null && floorList.includes(wantedEtage))
                    ? wantedEtage
                    : (floorList.length > 0 ? floorList[0] : null);
                if (initialEtage !== null) setSelectedEtage(initialEtage);
            })
            .catch((err) => console.error("Error loading map filters:", err));
    }, [paramEtage]);

    useEffect(() => {
        if (selectedEtage === null) return;
        setLoading(true);
        setSelectedObjet(null);
        setSelectedRoom(null);
        api.get(`/search?etage=${selectedEtage}`)
            .then((res) => {
                const list = Array.isArray(res.data) ? res.data : [];
                setObjets(list);
                // Auto-sélectionne l'objet ciblé via ?objet=…
                if (paramObjet) {
                    const target = list.find(o => String(o.id_objet) === String(paramObjet));
                    if (target) setSelectedObjet(target);
                }
            })
            .catch((err) => console.error("Error fetching map objects:", err))
            .finally(() => setLoading(false));
    }, [selectedEtage, paramObjet]);

    // ── COMPUTED ────────────────────────────────────
    const sallesActuelles = useMemo(() => salles.filter(s => s.num_etage === selectedEtage), [salles, selectedEtage]);

    const { mainRooms, corridorRooms } = useMemo(() => {
        const main = [], corridors = [];
        sallesActuelles.forEach(s => {
            const n = (s.nom_salle || "").toLowerCase();
            (n.includes("couloir") || n.includes("hall") || n.includes("corridor")) ? corridors.push(s) : main.push(s);
        });
        return { mainRooms: main, corridorRooms: corridors };
    }, [sallesActuelles]);

    const objectsByRoom = useMemo(() => {
        const map = {};
        objets.forEach(obj => { if (!map[obj.id_salle]) map[obj.id_salle] = []; map[obj.id_salle].push(obj); });
        return map;
    }, [objets]);

    // ── VISUAL LAYOUT ──────────────────────────────
    // 6 room slots + corridor — positions in viewBox 0 0 140 85
    const layoutSlots = [
        { x: 5, y: 5, w: 40, h: 33, doorWall: 'right', doorPos: 0.7 },
        { x: 49, y: 5, w: 30, h: 29, doorWall: 'bottom', doorPos: 0.5 },
        { x: 83, y: 5, w: 30, h: 29, doorWall: 'left', doorPos: 0.7 },
        { x: 5, y: 50, w: 26, h: 24, doorWall: 'top', doorPos: 0.5 },
        { x: 35, y: 50, w: 30, h: 24, doorWall: 'top', doorPos: 0.5 },
        { x: 83, y: 50, w: 30, h: 24, doorWall: 'left', doorPos: 0.5 },
    ];
    const corridorArea = { x: 45, y: 34, w: 34, h: 16 };

    const roomsToRender = useMemo(() => {
        return mainRooms.slice(0, 6).map((room, idx) => {
            const slot = layoutSlots[idx];
            return slot ? { ...room, ...slot } : null;
        }).filter(Boolean);
    }, [mainRooms]);

    const roomSlotMap = useMemo(() => {
        const map = {};
        mainRooms.slice(0, 6).forEach((r, idx) => { if (layoutSlots[idx]) map[r.id_salle] = layoutSlots[idx]; });
        return map;
    }, [mainRooms]);

    // ── HELPERS ────────────────────────────────────
    const handleEtageChange = (e) => setSelectedEtage(Number(e.target.value));

    const getStatusColor = (status) => {
        const s = String(status).toLowerCase();
        if (s.includes('panne') || s.includes('error') || s.includes('signalé')) return '#e74c3c';
        if (s.includes('occup') || s.includes('reserv')) return '#f39c12';
        return '#27ae60';
    };

    const isFaultStatus = (status) => {
        const s = String(status).toLowerCase();
        return s.includes('panne') || s.includes('error') || s.includes('signalé');
    };

    const getRoomStatus = (roomId) => {
        const ro = objectsByRoom[roomId] || [];
        if (ro.length === 0) return { label: 'Vide', color: '#94a3b8' };
        if (ro.some(o => isFaultStatus(o.statut))) return { label: 'Panne détectée', color: '#e74c3c' };
        if (ro.some(o => { const s = String(o.statut).toLowerCase(); return s.includes('occup') || s.includes('reserv'); }))
            return { label: 'OCCUPÉ', color: '#f39c12' };
        return { label: 'DISPONIBLE', color: '#27ae60' };
    };

    const stats = useMemo(() => {
        const total = objets.length;
        const online = objets.filter(o => !isFaultStatus(o.statut)).length;
        const faults = objets.filter(o => isFaultStatus(o.statut)).length;
        return { total, online, faults };
    }, [objets]);

    const selectedRoomObjects = useMemo(() => {
        if (!selectedRoom) return [];
        return objectsByRoom[selectedRoom.id_salle] || [];
    }, [selectedRoom, objectsByRoom]);

    // ── DOOR ARC GENERATOR (CAD-precise) ───────────
    const renderDoor = (room) => {
        const r = 4; // door swing radius
        const gap = r; // wall gap for door opening
        let gapLine, arc, doorLine;
        const { x, y, w, h, doorWall, doorPos } = room;

        if (doorWall === 'right') {
            const dy = y + h * doorPos;
            gapLine = <line x1={x + w} y1={dy - gap / 2} x2={x + w} y2={dy + gap / 2} stroke="#f8f9fb" strokeWidth="1.2" />;
            doorLine = <line x1={x + w} y1={dy - gap / 2} x2={x + w - r} y2={dy - gap / 2} stroke="#4a5568" strokeWidth="0.35" />;
            arc = <path d={`M ${x + w - r},${dy - gap / 2} A ${r},${r} 0 0,1 ${x + w},${dy + gap / 2}`} fill="none" stroke="#4a5568" strokeWidth="0.3" strokeDasharray="0.8,0.5" />;
        } else if (doorWall === 'left') {
            const dy = y + h * doorPos;
            gapLine = <line x1={x} y1={dy - gap / 2} x2={x} y2={dy + gap / 2} stroke="#f8f9fb" strokeWidth="1.2" />;
            doorLine = <line x1={x} y1={dy - gap / 2} x2={x + r} y2={dy - gap / 2} stroke="#4a5568" strokeWidth="0.35" />;
            arc = <path d={`M ${x + r},${dy - gap / 2} A ${r},${r} 0 0,0 ${x},${dy + gap / 2}`} fill="none" stroke="#4a5568" strokeWidth="0.3" strokeDasharray="0.8,0.5" />;
        } else if (doorWall === 'bottom') {
            const dx = x + w * doorPos;
            gapLine = <line x1={dx - gap / 2} y1={y + h} x2={dx + gap / 2} y2={y + h} stroke="#f8f9fb" strokeWidth="1.2" />;
            doorLine = <line x1={dx - gap / 2} y1={y + h} x2={dx - gap / 2} y2={y + h - r} stroke="#4a5568" strokeWidth="0.35" />;
            arc = <path d={`M ${dx - gap / 2},${y + h - r} A ${r},${r} 0 0,0 ${dx + gap / 2},${y + h}`} fill="none" stroke="#4a5568" strokeWidth="0.3" strokeDasharray="0.8,0.5" />;
        } else if (doorWall === 'top') {
            const dx = x + w * doorPos;
            gapLine = <line x1={dx - gap / 2} y1={y} x2={dx + gap / 2} y2={y} stroke="#f8f9fb" strokeWidth="1.2" />;
            doorLine = <line x1={dx - gap / 2} y1={y} x2={dx - gap / 2} y2={y + r} stroke="#4a5568" strokeWidth="0.35" />;
            arc = <path d={`M ${dx - gap / 2},${y + r} A ${r},${r} 0 0,1 ${dx + gap / 2},${y}`} fill="none" stroke="#4a5568" strokeWidth="0.3" strokeDasharray="0.8,0.5" />;
        }

        return <g>{gapLine}{doorLine}{arc}</g>;
    };

    // ── PREMIUM PIN (Google Maps–style) ────────────
    const renderPin = (point, fx, fy) => {
        const color = getStatusColor(point.statut);
        const fault = isFaultStatus(point.statut);
        const selected = selectedObjet?.id_objet === point.id_objet;
        const hovered = hoveredPin === point.id_objet;

        // Pin dimensions
        const pw = 2.0;  // half-width at widest
        const ph = 7.5;  // total height
        const cr = 1.8;  // circle head radius

        const tipY = fy;
        const headY = fy - ph + cr + 0.5;

        return (
            <g key={point.id_objet}
                className={`cad-pin ${fault ? 'cad-pin-fault' : ''} ${hovered ? 'cad-pin-hover' : ''}`}
                style={{ cursor: 'pointer' }}
                onClick={(e) => { e.stopPropagation(); setSelectedObjet(point); setSelectedRoom(null); }}
                onMouseEnter={() => setHoveredPin(point.id_objet)}
                onMouseLeave={() => setHoveredPin(null)}>

                {/* Fault pulse rings (outside the visual group to avoid jitter) */}
                {fault && (
                    <g style={{ pointerEvents: 'none' }}>
                        <circle cx={fx} cy={headY} r="3.5" fill="none" stroke="#e74c3c"
                            strokeWidth="0.3" className="cad-pulse-1" opacity="0.6" />
                        <circle cx={fx} cy={headY} r="5" fill="none" stroke="#e74c3c"
                            strokeWidth="0.2" className="cad-pulse-2" opacity="0.3" />
                    </g>
                )}

                {/* Pin Visual Group (Scales on hover) */}
                <g className="cad-pin-main">
                    {/* Ground shadow (ellipse) */}
                    <ellipse cx={fx} cy={tipY + 0.3} rx={hovered ? 2 : 1.4} ry={hovered ? 0.7 : 0.45}
                        fill="rgba(0,0,0,0.18)" className="cad-pin-shadow">
                        <animate attributeName="rx" values={fault ? "1.4;2;1.4" : "1.4"} dur="1.8s" repeatCount={fault ? "indefinite" : "0"} />
                    </ellipse>

                    {/* Pin body — premium teardrop */}
                    <path d={`
                        M ${fx} ${tipY}
                        C ${fx + pw * 0.6} ${tipY - ph * 0.25} ${fx + pw} ${tipY - ph * 0.45} ${fx + pw} ${tipY - ph * 0.58}
                        C ${fx + pw} ${tipY - ph * 0.78} ${fx + cr} ${tipY - ph + 0.2} ${fx + cr} ${headY}
                        A ${cr} ${cr} 0 1 0 ${fx - cr} ${headY}
                        C ${fx - cr} ${tipY - ph + 0.2} ${fx - pw} ${tipY - ph * 0.78} ${fx - pw} ${tipY - ph * 0.58}
                        C ${fx - pw} ${tipY - ph * 0.45} ${fx - pw * 0.6} ${tipY - ph * 0.25} ${fx} ${tipY} Z
                    `}
                        fill={color}
                        stroke="rgba(255,255,255,0.9)"
                        strokeWidth="0.4"
                        filter="url(#pin-shadow)"
                    />

                    {/* Glossy highlight on pin head */}
                    <ellipse cx={fx - 0.4} cy={headY - 0.5} rx="0.8" ry="0.5"
                        fill="rgba(255,255,255,0.45)" transform={`rotate(-25 ${fx - 0.4} ${headY - 0.5})`} />

                    {/* Inner white circle */}
                    <circle cx={fx} cy={headY} r="1.0" fill="white" opacity="0.92" />
                </g>

                {/* Selection ring */}
                {selected && (
                    <circle cx={fx} cy={headY} r="3.8" fill="none" stroke={color}
                        strokeWidth="0.45" strokeDasharray="1.4,0.8"
                        className="carte-selection-ring" style={{ pointerEvents: 'none' }} />
                )}

                {/* Hover tooltip */}
                {hovered && !selected && (
                    <g className="cad-tooltip" style={{ pointerEvents: 'none' }}>
                        <rect x={fx - 10} y={headY - 7} width="20" height="4.5"
                            rx="1" fill="rgba(15,23,42,0.88)"
                            filter="url(#tooltip-shadow)" />
                        <text x={fx} y={headY - 4.2} textAnchor="middle" dominantBaseline="middle"
                            fill="white" fontSize="1.6" fontFamily="'Inter', sans-serif" fontWeight="600">
                            {point.nom_model}
                        </text>
                    </g>
                )}
            </g>
        );
    };

    // ========================================
    //  RENDER SVG FLOOR PLAN
    // ========================================
    const renderFloorPlan = () => (
        <svg className={`cad-floor-svg ${isSettingLocation ? 'setting-location' : ''}`} width="100%" height="100%"
            viewBox="0 0 140 85" preserveAspectRatio="xMidYMid meet"
            onClick={handleSVGClick}
            style={{ cursor: isSettingLocation ? 'crosshair' : 'default' }}>
            <defs>
                {/* Subtle dot grid */}
                <pattern id="dot-grid" width="3" height="3" patternUnits="userSpaceOnUse">
                    <circle cx="1.5" cy="1.5" r="0.15" fill="#b0bac9" opacity="0.5" />
                </pattern>
                {/* Pin drop-shadow filter */}
                <filter id="pin-shadow" x="-40%" y="-20%" width="180%" height="160%">
                    <feDropShadow dx="0.3" dy="0.6" stdDeviation="0.5" floodColor="rgba(0,0,0,0.35)" />
                </filter>
                {/* Tooltip shadow */}
                <filter id="tooltip-shadow" x="-10%" y="-20%" width="120%" height="150%">
                    <feDropShadow dx="0" dy="0.5" stdDeviation="0.8" floodColor="rgba(0,0,0,0.3)" />
                </filter>
            </defs>

            {/* ── BACKGROUND ── */}
            <rect width="140" height="85" fill="#f8f9fb" />
            <rect width="140" height="85" fill="url(#dot-grid)" />

            {/* ── BUILDING SHELL (double line) ── */}
            <rect x="3" y="3" width="114" height="76" rx="0.8"
                fill="none" stroke="#334155" strokeWidth="1.6" />
            <rect x="4" y="4" width="112" height="74" rx="0.4"
                fill="none" stroke="#334155" strokeWidth="0.3" opacity="0.25" />

            {/* ── ROOMS (from DB) ── */}
            {roomsToRender.map((room) => (
                <g key={room.id_salle} style={{ cursor: 'pointer' }}
                    onClick={() => { setSelectedRoom(room); setSelectedObjet(null); }}>

                    {/* Room fill — very subtle tint */}
                    <rect x={room.x} y={room.y} width={room.w} height={room.h}
                        fill="rgba(100, 130, 180, 0.025)"
                        stroke="#334155" strokeWidth="0.8" />

                    {/* CAD door */}
                    {renderDoor(room)}

                    {/* Room name (centered, CAD-style) */}
                    <text x={room.x + room.w / 2} y={room.y + room.h / 2 + 0.5}
                        textAnchor="middle" dominantBaseline="middle"
                        fill="#334155" fontSize="2.2"
                        fontFamily="'Inter', 'Roboto', sans-serif" fontWeight="600"
                        letterSpacing="0.3"
                        style={{ pointerEvents: 'none', userSelect: 'none' }}>
                        {room.nom_salle}
                    </text>

                    {/* Object count badge */}
                    {(objectsByRoom[room.id_salle] || []).length > 0 && (
                        <g>
                            <rect x={room.x + room.w - 5} y={room.y + 1.5} width="4" height="2.5"
                                rx="1.2" fill="#334155" opacity="0.7" />
                            <text x={room.x + room.w - 3} y={room.y + 3}
                                textAnchor="middle" dominantBaseline="middle"
                                fill="white" fontSize="1.3" fontWeight="700"
                                fontFamily="'Inter', sans-serif"
                                style={{ pointerEvents: 'none' }}>
                                {(objectsByRoom[room.id_salle] || []).length}
                            </text>
                        </g>
                    )}
                </g>
            ))}

            {/* ── CORRIDOR ── */}
            <rect x={corridorArea.x} y={corridorArea.y}
                width={corridorArea.w} height={corridorArea.h}
                fill="rgba(100, 130, 180, 0.035)" stroke="#334155" strokeWidth="0.5" />
            <text x={corridorArea.x + corridorArea.w / 2} y={corridorArea.y + corridorArea.h / 2 + 0.5}
                textAnchor="middle" dominantBaseline="middle"
                fill="#64748b" fontSize="1.8" fontFamily="'Inter', sans-serif" fontWeight="500"
                letterSpacing="1"
                style={{ pointerEvents: 'none', userSelect: 'none' }}>
                {corridorRooms.length > 0 ? corridorRooms[0].nom_salle : 'Couloir'}
            </text>

            {/* ── INTERNAL WALLS (crisp CAD lines) ── */}
            {/* Top-row vertical separators */}
            <line x1="49" y1="5" x2="49" y2="34" stroke="#334155" strokeWidth="0.8" />
            <line x1="83" y1="5" x2="83" y2="34" stroke="#334155" strokeWidth="0.8" />
            {/* Horizontal between top rooms & corridor */}
            <line x1="5" y1="38" x2="45" y2="38" stroke="#334155" strokeWidth="0.8" />
            <line x1="79" y1="34" x2="117" y2="34" stroke="#334155" strokeWidth="0.8" />
            {/* Bottom-row separators */}
            <line x1="5" y1="50" x2="35" y2="50" stroke="#334155" strokeWidth="0.8" />
            <line x1="35" y1="50" x2="35" y2="74" stroke="#334155" strokeWidth="0.8" />
            <line x1="65" y1="50" x2="83" y2="50" stroke="#334155" strokeWidth="0.8" />
            <line x1="83" y1="50" x2="83" y2="74" stroke="#334155" strokeWidth="0.8" />

            {/* ── IOT PINS (from DB) ── */}
            {!isSettingLocation && objets.map((point) => {
                const slot = roomSlotMap[point.id_salle];
                if (!slot) return null;

                let fx, fy;
                if (point.pos_x != null && point.pos_y != null) {
                    // Position réelle capturée à l'ajout (pos_x / pos_y = % 0-100 dans la salle)
                    fx = slot.x + (point.pos_x / 100) * slot.w;
                    fy = slot.y + (point.pos_y / 100) * slot.h;
                } else {
                    // Fallback: objets legacy sans position — dispersion déterministe dans la salle
                    const h1 = (point.id_objet * 17) % 100;
                    const h2 = (point.id_objet * 31) % 100;
                    const cx = slot.x + slot.w / 2;
                    const cy = slot.y + slot.h / 2 - 1;
                    fx = cx + (h1 / 100) * slot.w * 0.4 - slot.w * 0.2;
                    fy = cy + (h2 / 100) * slot.h * 0.25 - slot.h * 0.125;
                }

                return renderPin(point, fx, fy);
            })}

            {/* ── USER PIN ── */}
            {(() => {
                const loc = tempUserLocation || userLocation;
                if (!loc || loc.etage !== selectedEtage) return null;
                const { x, y } = loc;
                return (
                    <g transform={`translate(${x}, ${y})`} style={{ pointerEvents: 'none' }}>
                        {/* Pulse Ring */}
                        <circle cx="0" cy="0" r="3.5" fill="none" stroke="#2563eb" strokeWidth="0.4" className="cad-pulse-1" />
                        <circle cx="0" cy="0" r="1.8" fill="#3b82f6" opacity="0.3" />

                        {/* Precise dot */}
                        <circle cx="0" cy="0" r="0.6" fill="#1e3a8a" />

                        {/* High-tech arrow body directly pointing to the dot */}
                        <path d="M 0 -0.8 L 1.2 -4 L 0 -3.2 L -1.2 -4 Z" fill="#2563eb" stroke="white" strokeWidth="0.2" />

                        {/* Tooltip Box */}
                        <rect x="-10" y="-8.5" width="20" height="3.8" rx="1" fill="rgba(30,58,138,0.9)" />
                        <text x="0" y="-6.4" textAnchor="middle" dominantBaseline="middle" fill="white" fontSize="1.4" fontWeight="600" fontFamily="'Inter',sans-serif">Vous êtes ici</text>
                    </g>
                );
            })()}

            {/* ── LEGEND ── */}
            <g transform="translate(5, 80)">
                <circle cx="1.5" cy="0" r="0.7" fill="#27ae60" />
                <text x="3.5" y="0.4" fontSize="1.35" fill="#475569" fontFamily="'Inter',sans-serif" fontWeight="500">Disponible</text>
                <circle cx="18" cy="0" r="0.7" fill="#f39c12" />
                <text x="20" y="0.4" fontSize="1.35" fill="#475569" fontFamily="'Inter',sans-serif" fontWeight="500">Occupé</text>
                <circle cx="32" cy="0" r="0.7" fill="#e74c3c" />
                <text x="34" y="0.4" fontSize="1.35" fill="#475569" fontFamily="'Inter',sans-serif" fontWeight="500">Panne / Erreur</text>
                <text x="110" y="0.4" fontSize="1.2" fill="#94a3b8" textAnchor="end"
                    fontFamily="'Inter',sans-serif" fontWeight="500">
                    {stats.online}/{stats.total} Online  ·  {stats.faults} Faults
                </text>
            </g>
        </svg>
    );

    // ========================================
    //  RENDER JSX
    // ========================================
    return (
        <main className="page-pad carte-page">
            <div className="container">
                <header className="carte-head">
                    <h1 className="carte-title">{t('map.title')}</h1>
                    <p className="carte-subtitle">{t('map.subtitle')}</p>
                </header>

                <div className="carte-controls">
                    <label htmlFor="floor-select"><strong>{t('map.selectFloor')}</strong></label>
                    <select id="floor-select" className="input-field" value={selectedEtage || ''} onChange={handleEtageChange} disabled={isSettingLocation}>
                        {etages.map((et) => (
                            <option key={et} value={et}>{t('map.floor')} {et}</option>
                        ))}
                    </select>

                    <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
                        {!isSettingLocation ? (
                            <button className="btn btn-primary" onClick={() => setIsSettingLocation(true)}>
                                <i className="fa-solid fa-location-crosshairs" style={{ marginRight: '6px' }} />
                                {userLocation ? 'Modifier ma position' : 'Définir ma position'}
                            </button>
                        ) : (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', background: 'var(--surface-50)', padding: '4px 12px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                                <span style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '14px' }}>
                                    <i className="fa-solid fa-mouse-pointer" style={{ marginRight: '6px' }} />
                                    Cliquez sur le plan pour définir votre emplacement
                                </span>
                                <button className="btn" onClick={() => { setIsSettingLocation(false); setTempUserLocation(null); }}>Annuler</button>
                                <button className="btn btn-primary" disabled={!tempUserLocation} onClick={confirmUserLocation}>Confirmer</button>
                            </div>
                        )}
                    </div>
                </div>

                <div className="carte-layout">
                    {/* Map */}
                    <div className="carte-map-container card cad-map-glass">
                        {loading ? (
                            <div className="carte-loading">{t('common.loading')}</div>
                        ) : (
                            <div className="carte-map-wrapper">
                                {renderFloorPlan()}
                            </div>
                        )}
                    </div>

                    {/* Sidebar (Glassmorphism) */}
                    <div className={`carte-sidebar cad-sidebar-glass ${(selectedObjet || selectedRoom) ? 'open' : ''}`}>
                        {selectedObjet ? (
                            <div className="carte-sidebar-content">
                                <div className="carte-sidebar-cover" style={{ backgroundColor: getStatusColor(selectedObjet.statut) + '10' }}>
                                    <div className="cad-sidebar-header">
                                        <div className="cad-header-top">
                                            <h3>{selectedObjet.nom_model}</h3>
                                            <span className="cad-status-pill" style={{
                                                background: getStatusColor(selectedObjet.statut) + '18',
                                                color: getStatusColor(selectedObjet.statut),
                                                borderColor: getStatusColor(selectedObjet.statut) + '40'
                                            }}>
                                                {translateData('status', selectedObjet.statut)}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="carte-sidebar-body">
                                    <div className="cad-detail-card">
                                        <div className="carte-detail-row">
                                            <div className="cad-detail-icon"><i className="fa-solid fa-microchip" /></div>
                                            <div className="cad-detail-info">
                                                <span className="carte-detail-label">Type</span>
                                                <span className="carte-detail-value">{translateData('type', selectedObjet.type_objet)}</span>
                                            </div>
                                        </div>
                                        <div className="carte-detail-row">
                                            <div className="cad-detail-icon"><i className="fa-solid fa-copyright" /></div>
                                            <div className="cad-detail-info">
                                                <span className="carte-detail-label">Marque</span>
                                                <span className="carte-detail-value">{selectedObjet.nom_marque || 'N/A'}</span>
                                            </div>
                                        </div>
                                        <div className="carte-detail-row">
                                            <div className="cad-detail-icon"><i className="fa-solid fa-location-dot" /></div>
                                            <div className="cad-detail-info">
                                                <span className="carte-detail-label">Salle</span>
                                                <span className="carte-detail-value">{salles.find(s => s.id_salle === selectedObjet.id_salle)?.nom_salle || 'N/A'}</span>
                                            </div>
                                        </div>
                                        <div className="carte-detail-row">
                                            <div className="cad-detail-icon"><i className="fa-solid fa-circle-info" /></div>
                                            <div className="cad-detail-info">
                                                <span className="carte-detail-label">État</span>
                                                <span className="carte-detail-value" style={{ color: getStatusColor(selectedObjet.statut), fontWeight: 700 }}>{selectedObjet.statut}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div className="carte-sidebar-footer">
                                    <button className="btn btn-primary" onClick={() => navigate(`/equipment/${selectedObjet.id_objet}`)}>
                                        <i className="fa-solid fa-eye" style={{ marginRight: 6 }} />Voir détails
                                    </button>
                                    <button className="btn btn-secondary" onClick={() => setSelectedObjet(null)}>Fermer</button>
                                </div>
                            </div>
                        ) : selectedRoom ? (
                            <div className="carte-sidebar-content">
                                <div className="carte-sidebar-header">
                                    <h3>Détails Salle</h3>
                                </div>
                                <div className="carte-sidebar-body">
                                    <div className="carte-detail-row"><span className="carte-detail-label">Salle</span><span className="carte-detail-value" style={{ fontWeight: 700 }}>{selectedRoom.nom_salle}</span></div>
                                    <div className="carte-detail-row"><span className="carte-detail-label">Équipements</span><span className="carte-detail-value">{selectedRoomObjects.length} objet(s)</span></div>
                                    {selectedRoomObjects.length > 0 && (
                                        <div className="carte-room-equip-list">
                                            {selectedRoomObjects.map(obj => (
                                                <div key={obj.id_objet} className="carte-room-equip-item"
                                                    onClick={() => { setSelectedObjet(obj); setSelectedRoom(null); }}>
                                                    <div className="carte-room-equip-dot" style={{ backgroundColor: getStatusColor(obj.statut) }} />
                                                    <div className="carte-room-equip-info">
                                                        <span className="carte-room-equip-name">{obj.nom_model}</span>
                                                        <span className="carte-room-equip-type">{obj.type_objet}</span>
                                                    </div>
                                                    <span className="carte-room-equip-status" style={{ color: getStatusColor(obj.statut) }}>{obj.statut}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <div className="carte-sidebar-footer">
                                    {getRoomStatus(selectedRoom.id_salle).label === 'OCCUPÉ' && (
                                        <>
                                            <button className="btn btn-primary" onClick={() => { }}>
                                                <i className="fa-solid fa-power-off" style={{ marginRight: 6 }} />Allumer Datashow
                                            </button>
                                            <button className="btn btn-warning-outline" onClick={() => { }}>
                                                <i className="fa-solid fa-door-open" style={{ marginRight: 6 }} />Terminer Réunion
                                            </button>
                                        </>
                                    )}
                                    <button className="btn btn-secondary" onClick={() => setSelectedRoom(null)}>Fermer</button>
                                </div>
                            </div>
                        ) : (
                            <div className="carte-sidebar-empty">
                                <div className="cad-empty-icon">
                                    <i className="fa-solid fa-map-location-dot" />
                                </div>
                                <h4>Plan Interactif</h4>
                                <p>Sélectionnez une salle ou un équipement sur le plan pour afficher ses détails.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </main>
    );
};

export default Carte;
