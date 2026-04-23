import { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const TERMINAL_STATUSES = new Set(['success', 'failed', 'timeout']);

const statusColor = (status) => {
  switch (status) {
    case 'success': return { bg: '#dcfce7', fg: '#166534', border: '#86efac' };
    case 'failed':
    case 'timeout': return { bg: '#fee2e2', fg: '#991b1b', border: '#fecaca' };
    case 'running':
    case 'dispatched': return { bg: '#dbeafe', fg: '#1e40af', border: '#93c5fd' };
    default: return { bg: '#f1f5f9', fg: '#475569', border: '#cbd5e1' };
  }
};

const labelFromStatus = (status) => {
  switch (status) {
    case 'pending': return 'Préparation…';
    case 'dispatched': return 'Envoyé à l\'équipement';
    case 'running': return 'Exécution en cours…';
    case 'success': return 'Terminé avec succès';
    case 'failed': return 'Échec';
    case 'timeout': return 'Timeout (équipement injoignable)';
    default: return status;
  }
};

const ActionModal = ({ objet, open, onClose }) => {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [file, setFile] = useState(null);
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [task, setTask] = useState(null);
  const [error, setError] = useState('');

  const reset = () => {
    setSelected(null);
    setFile(null);
    setText('');
    setUrl('');
    setTask(null);
    setError('');
  };

  useEffect(() => {
    if (!open || !objet?.id) return;
    setLoading(true);
    setError('');
    reset();
    api.get(`/objets/${objet.id}/actions`)
      .then((res) => setActions(Array.isArray(res.data) ? res.data : []))
      .catch(() => setError('Impossible de charger les actions disponibles.'))
      .finally(() => setLoading(false));
  }, [open, objet?.id]);

  useEffect(() => {
    if (!task || TERMINAL_STATUSES.has(task.status)) return;
    const pollId = setInterval(() => {
      api.get(`/tasks/${task.task_id || task.id_task}`)
        .then((res) => {
          const data = res.data || {};
          setTask((prev) => ({
            ...prev,
            status: data.status,
            result_url: data.result_url || prev.result_url,
            error: data.error || prev.error,
          }));
          if (TERMINAL_STATUSES.has(data.status)) clearInterval(pollId);
        })
        .catch(() => {});
    }, 2000);
    return () => clearInterval(pollId);
  }, [task?.task_id, task?.id_task, task?.status]);

  const currentSpec = useMemo(
    () => actions.find((a) => a.key === selected) || null,
    [actions, selected]
  );

  const canSubmit = useMemo(() => {
    if (!currentSpec || submitting) return false;
    const kind = currentSpec.input_kind;
    if (kind === 'file') return !!file;
    if (kind === 'url') return !!url.trim();
    if (kind === 'text') return currentSpec.optional || !!text.trim();
    return true;
  }, [currentSpec, file, url, text, submitting]);

  const submit = async () => {
    if (!currentSpec) return;
    setSubmitting(true);
    setError('');
    try {
      const form = new FormData();
      form.append('action', currentSpec.key);
      if (currentSpec.input_kind === 'file' && file) form.append('file', file);
      if (currentSpec.input_kind === 'url') form.append('payload_url', url.trim());
      if (currentSpec.input_kind === 'text') form.append('payload_text', text.trim());
      const res = await api.post(`/objets/${objet.id}/action`, form);
      setTask({
        task_id: res.data.task_id,
        status: res.data.status,
        message: res.data.message,
        result_url: res.data.result_url,
      });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Échec de l\'action');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  const colors = task ? statusColor(task.status) : null;

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 16,
      }}
    >
      <div
        className="card"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--surface, #fff)', borderRadius: 14, width: 560,
          maxWidth: '100%', padding: 24, boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: 0 }}>Action sur {objet?.name || objet?.nom_model || 'l\'équipement'}</h3>
            <p style={{ margin: '4px 0 0', color: 'var(--muted)', fontSize: '0.9rem' }}>
              {objet?.type || objet?.type_objet}
            </p>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Fermer"
            style={{ background: 'transparent', border: 'none', fontSize: 22, cursor: 'pointer', color: '#64748b' }}
          >
            <i className="fa-solid fa-xmark" />
          </button>
        </div>

        {loading && <p>Chargement des actions…</p>}

        {!loading && actions.length === 0 && (
          <p style={{ color: '#64748b' }}>
            Aucune action disponible pour cet équipement.
          </p>
        )}

        {!loading && actions.length > 0 && !task && (
          <>
            <div style={{ display: 'grid', gap: 10, marginBottom: 16 }}>
              {actions.map((a) => (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => { setSelected(a.key); setFile(null); setText(''); setUrl(''); setError(''); }}
                  style={{
                    padding: '12px 14px', borderRadius: 10,
                    border: `1px solid ${selected === a.key ? '#2563eb' : '#e2e8f0'}`,
                    background: selected === a.key ? '#eff6ff' : '#f8fafc',
                    display: 'flex', alignItems: 'center', gap: 10,
                    cursor: 'pointer', textAlign: 'left',
                  }}
                >
                  <i className="fa-solid fa-bolt" style={{ color: '#f59e0b' }} />
                  <span style={{ fontWeight: 600 }}>{a.label_fr}</span>
                </button>
              ))}
            </div>

            {currentSpec && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
                {currentSpec.input_kind === 'file' && (
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Fichier</span>
                    <input
                      type="file"
                      accept={currentSpec.accept || undefined}
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                    {currentSpec.max_size && (
                      <small style={{ color: '#64748b' }}>
                        Max {(currentSpec.max_size / (1024 * 1024)).toFixed(0)} Mo
                      </small>
                    )}
                  </label>
                )}
                {currentSpec.input_kind === 'url' && (
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>URL</span>
                    <input
                      type="url"
                      className="input"
                      placeholder={currentSpec.placeholder || 'https://…'}
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                    />
                  </label>
                )}
                {currentSpec.input_kind === 'text' && (
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                      Texte {currentSpec.optional ? '(optionnel)' : ''}
                    </span>
                    <textarea
                      className="input"
                      rows={3}
                      placeholder={currentSpec.placeholder}
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                    />
                  </label>
                )}
                {currentSpec.input_kind === 'none' && (
                  <p style={{ color: '#475569' }}>
                    Cette action ne nécessite aucun paramètre.
                  </p>
                )}
              </div>
            )}

            {error && (
              <div style={{ padding: 10, borderRadius: 8, background: '#fee2e2', color: '#991b1b', marginBottom: 12 }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" onClick={onClose} className="btn">Annuler</button>
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                style={{
                  background: canSubmit ? '#2563eb' : '#94a3b8',
                  color: 'white', border: 'none', padding: '10px 16px',
                  borderRadius: 8, cursor: canSubmit ? 'pointer' : 'not-allowed',
                  fontWeight: 600,
                }}
              >
                <i className={`fa-solid ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} style={{ marginRight: 6 }} />
                {submitting ? 'Envoi…' : 'Exécuter'}
              </button>
            </div>
          </>
        )}

        {task && (
          <div>
            <div style={{
              padding: 14, borderRadius: 10,
              background: colors.bg, color: colors.fg,
              border: `1px solid ${colors.border}`, marginBottom: 14,
            }}>
              <strong>{labelFromStatus(task.status)}</strong>
              {task.error && <div style={{ marginTop: 6, fontSize: '0.9rem' }}>{task.error}</div>}
              {task.result_url && (
                <div style={{ marginTop: 10 }}>
                  <a
                    href={task.result_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: colors.fg, fontWeight: 600, textDecoration: 'underline' }}
                  >
                    Ouvrir le résultat ↗
                  </a>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <button type="button" onClick={reset} className="btn">
                Nouvelle action
              </button>
              <button type="button" onClick={onClose} className="btn btn-primary"
                style={{ background: '#2563eb', color: 'white', border: 'none', padding: '10px 16px', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
                Fermer
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ActionModal;
