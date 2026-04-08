import React, { useState } from 'react';
import '@chatscope/chat-ui-kit-styles/dist/default/styles.min.css';
import {
    MainContainer,
    ChatContainer,
    MessageList,
    Message,
    MessageInput,
    TypingIndicator
} from '@chatscope/chat-ui-kit-react';
import api from '../services/api';

const Chatbot = () => {
    const [messages, setMessages] = useState([
        { message: "Bonjour! Je suis l'assistant IA du bâtiment. Je peux consulter la disponibilité des équipements et signaler les pannes en lisant la base de données. Comment puis-je vous aider ?", sender: "bot", direction: "incoming" }
    ]);
    const [isTyping, setIsTyping] = useState(false);
    const [isOpen, setIsOpen] = useState(false);

    const handleSend = async (messageText) => {
        const newMessage = { message: messageText, sender: 'user', direction: 'outgoing' };
        setMessages((prev) => [...prev, newMessage]);
        setIsTyping(true);

        try {
            const response = await api.post('/chat', { message: messageText });
            setMessages((prev) => [
                ...prev,
                { message: response.data.reply, sender: 'bot', direction: 'incoming' }
            ]);
        } catch (error) {
            setMessages((prev) => [
                ...prev,
                { message: "Désolé, une erreur technique empêche la connexion à l'IA.", sender: 'bot', direction: 'incoming' }
            ]);
        } finally {
            setIsTyping(false);
        }
    };

    return (
        <div style={{ position: "fixed", bottom: "30px", right: "30px", zIndex: 9999 }}>
            {isOpen ? (
                <div style={{ width: "350px", height: "500px", boxShadow: "0 4px 15px rgba(0,0,0,0.2)", borderRadius: "10px", overflow: "hidden", display: "flex", flexDirection: "column" }}>
                    <div
                        style={{ background: "#2563eb", color: "white", padding: "12px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                        onClick={() => setIsOpen(false)}
                    >
                        <strong>Assistant IA</strong>
                        <span style={{ fontWeight: "bold" }}>✖</span>
                    </div>
                    <div style={{ flex: 1, position: 'relative' }}>
                        <MainContainer style={{ border: "none" }}>
                            <ChatContainer>
                                <MessageList typingIndicator={isTyping ? <TypingIndicator content="L'IA analyse la base de données..." /> : null}>
                                    {messages.map((msg, i) => (
                                        <Message key={i} model={{ message: msg.message, sender: msg.sender, direction: msg.direction }} />
                                    ))}
                                </MessageList>
                                <MessageInput placeholder="Pose-moi une question sur le bâtiment..." onSend={handleSend} attachButton={false} />
                            </ChatContainer>
                        </MainContainer>
                    </div>
                </div>
            ) : (
                <button
                    onClick={() => setIsOpen(true)}
                    style={{ width: "60px", height: "60px", borderRadius: "50%", background: "#2563eb", color: "white", border: "none", fontSize: "28px", cursor: "pointer", boxShadow: "0 4px 10px rgba(0,0,0,0.3)", display: "flex", justifyContent: "center", alignItems: "center" }}
                >
                    💬
                </button>
            )}
        </div>
    );
};

export default Chatbot;
