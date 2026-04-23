import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../services/api';

const STORAGE_KEY = 'smartfind_chat_history';
const MAX_HISTORY = 20;

const WELCOME_MESSAGE = {
  role: 'assistant',
  content:
    "Bonjour, je suis l'assistant SmartFind. Pose-moi tes questions sur la navigation, les boutons ou l'usage des équipements (imprimante, scanner, projecteur, écran, visio).",
};

const ChatbotWidget = () => {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    } catch (_e) {
      /* ignore */
    }
    return [WELCOME_MESSAGE];
  });

  const listRef = useRef(null);
  const inputRef = useRef(null);

  const token = localStorage.getItem('access_token');
  const hiddenRoutes = ['/login', '/signup', '/verify-email', '/forgot-password'];
  const hidden = !token || hiddenRoutes.includes(location.pathname);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_HISTORY)));
    } catch (_e) {
      /* quota plein : on ignore */
    }
  }, [messages]);

  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [open, messages]);

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
  }, [open]);

  if (hidden) return null;

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || busy) return;

    const userMsg = { role: 'user', content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setBusy(true);

    try {
      const history = nextMessages
        .slice(0, -1)
        .filter((m) => m !== WELCOME_MESSAGE)
        .slice(-MAX_HISTORY);
      const res = await api.post('/chat', { message: text, history });
      const reply = res.data?.reply || "Je ne peux répondre qu'aux questions sur SmartFind.";
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch (err) {
      const msg =
        err?.response?.status === 429
          ? 'Trop de messages, patiente une minute avant de réessayer.'
          : "Impossible de contacter l'assistant pour le moment.";
      setMessages((prev) => [...prev, { role: 'assistant', content: msg }]);
    } finally {
      setBusy(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const resetConversation = () => {
    setMessages([WELCOME_MESSAGE]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (_e) {
      /* ignore */
    }
  };

  return (
    <div className="chatbot-root">
      {open && (
        <div className="chatbot-panel" role="dialog" aria-label="Assistant SmartFind">
          <div className="chatbot-header">
            <div className="chatbot-title">
              <span className="chatbot-dot" />
              <div>
                <div className="chatbot-title-main">Assistant SmartFind</div>
                <div className="chatbot-title-sub">Aide sur l'application et les équipements</div>
              </div>
            </div>
            <div className="chatbot-header-actions">
              <button
                type="button"
                className="chatbot-iconbtn"
                onClick={resetConversation}
                title="Effacer la conversation"
                aria-label="Effacer la conversation"
              >
                <i className="fa-solid fa-rotate-left" />
              </button>
              <button
                type="button"
                className="chatbot-iconbtn"
                onClick={() => setOpen(false)}
                title="Fermer"
                aria-label="Fermer"
              >
                <i className="fa-solid fa-xmark" />
              </button>
            </div>
          </div>

          <div className="chatbot-messages" ref={listRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chatbot-msg ${m.role === 'user' ? 'chatbot-msg-user' : 'chatbot-msg-bot'}`}>
                {m.content}
              </div>
            ))}
            {busy && (
              <div className="chatbot-msg chatbot-msg-bot chatbot-typing">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>

          <div className="chatbot-input">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Pose ta question sur SmartFind…"
              rows={1}
              maxLength={2000}
              disabled={busy}
            />
            <button
              type="button"
              className="chatbot-send"
              onClick={sendMessage}
              disabled={busy || !input.trim()}
              aria-label="Envoyer"
              title="Envoyer"
            >
              <i className="fa-solid fa-paper-plane" />
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className={`chatbot-fab ${open ? 'chatbot-fab-open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? 'Fermer le chatbot' : 'Ouvrir le chatbot'}
        title={open ? 'Fermer le chatbot' : 'Assistant SmartFind'}
      >
        <i className={`fa-solid ${open ? 'fa-xmark' : 'fa-robot'}`} />
      </button>
    </div>
  );
};

export default ChatbotWidget;
