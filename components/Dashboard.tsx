import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { HomePage } from './HomePage';
import { LiveInterface } from './LiveInterface';
import { InteractionMode, ChatSession, Message, User } from '../types';
import { Menu } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface DashboardProps {
    currentUser: User;
    onLogout: () => void;
    theme: 'light' | 'dark';
    toggleTheme: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ currentUser, onLogout, theme, toggleTheme }) => {
    
    // Dynamic Storage Key based on User ID
    const STORAGE_KEY = `zeno_chats_${currentUser.id}`;

    // --- STATE ---
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [interactionMode, setInteractionMode] = useState<InteractionMode>(InteractionMode.TEXT);
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    // --- LOAD CHATS (Scoped to User) ---
    useEffect(() => {
        // Reset state first to ensure no bleed-over if user switched quickly
        setSessions([]);
        setActiveSessionId(null);

        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                const restoredSessions = parsed.map((s: any) => ({
                    ...s,
                    date: new Date(s.date),
                    messages: s.messages.map((m: any) => ({...m, timestamp: new Date(m.timestamp)}))
                }));
                setSessions(restoredSessions);
            } catch (e) {
                console.error("Failed to parse sessions", e);
                setSessions([]);
            }
        } else {
            setSessions([]);
        }
    }, [currentUser.id]); // Re-run ONLY when user ID changes

    // --- SAVE CHATS (Scoped to User) ---
    useEffect(() => {
        // Only save if we have sessions loaded to avoid overwriting with empty array on initial mount race conditions
        if (currentUser.id) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
        }
    }, [sessions, currentUser.id]);

    // Active Session Helper
    const activeSession = sessions.find(s => s.id === activeSessionId);

    // --- ACTIONS ---

    const startSession = (mode: InteractionMode, initialText?: string) => {
        const initialMessages: Message[] = [];
        
        if (initialText) {
            initialMessages.push({
                id: Date.now().toString(),
                role: 'user',
                content: initialText,
                timestamp: new Date()
            });
        }

        const newSession: ChatSession = {
            id: Date.now().toString(),
            title: initialText ? (initialText.length > 20 ? initialText.slice(0, 20) + '...' : initialText) : 'New Conversation',
            date: new Date(),
            messages: initialMessages
        };

        setSessions(prev => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        setInteractionMode(mode);

        // If there was an initial text, trigger an AI response
        if (initialText) {
            setTimeout(() => {
                setSessions(prev => prev.map(session => {
                    if (session.id === newSession.id) {
                        return {
                            ...session,
                            messages: [...session.messages, {
                                id: Date.now().toString() + '_ai',
                                role: 'assistant',
                                content: "I'm listening. How is that making you feel?",
                                timestamp: new Date()
                            }]
                        };
                    }
                    return session;
                }));
            }, 1000);
        }
    };

    const handleStartVoice = () => startSession(InteractionMode.VOICE);
    const handleStartText = (text?: string) => startSession(InteractionMode.TEXT, text);

    // New Chat -> Go to Home Screen (Preserve current chat in history)
    const handleNewChat = () => {
        setActiveSessionId(null); 
        setIsSidebarOpen(false);
    };

    const handleSelectSession = (sessionId: string) => {
        setActiveSessionId(sessionId);
        setInteractionMode(InteractionMode.TEXT);
        setIsSidebarOpen(false);
    };

    const handleDeleteSession = (sessionId: string) => {
        setSessions(prev => prev.filter(s => s.id !== sessionId));
        if (activeSessionId === sessionId) {
            setActiveSessionId(null);
        }
    };

    const handleRenameSession = (sessionId: string, newTitle: string) => {
        setSessions(prev => prev.map(s => {
            if (s.id === sessionId) {
                return { ...s, title: newTitle };
            }
            return s;
        }));
    };

    const updateActiveSessionMessages = (newMessage: Message) => {
        if (!activeSessionId) return;
        
        setSessions(prev => prev.map(session => {
            if (session.id === activeSessionId) {
                let title = session.title;
                // Auto-title logic
                if ((title === 'New Conversation' || title === 'New Chat') && newMessage.role === 'user') {
                    title = newMessage.content.slice(0, 24) + (newMessage.content.length > 24 ? '...' : '');
                }
                return {
                    ...session,
                    title,
                    messages: [...session.messages, newMessage]
                };
            }
            return session;
        }));
    };

    const handleUserSendMessage = (text: string) => {
        // Add user message to UI immediately
        // If the message is a placeholder like "[Transcribing...]", replace the last user message if it's also a placeholder
        if (!activeSessionId) return;
        
        setSessions(prev => prev.map(session => {
            if (session.id === activeSessionId) {
                const messages = [...session.messages];
                const lastMessage = messages[messages.length - 1];
                
                // If last message is a placeholder and new message is also a placeholder or actual text, replace it
                if (lastMessage && 
                    lastMessage.role === 'user' && 
                    (lastMessage.content.startsWith('[') || text.startsWith('['))) {
                    // Replace the last message
                    messages[messages.length - 1] = {
                        id: lastMessage.id, // Keep same ID
                        role: 'user',
                        content: text,
                        timestamp: new Date()
                    };
                } else {
                    // Add new message
                    messages.push({
                        id: Date.now().toString(),
                        role: 'user',
                        content: text,
                        timestamp: new Date()
                    });
                }
                
                let title = session.title;
                // Auto-title logic
                if ((title === 'New Conversation' || title === 'New Chat') && !text.startsWith('[')) {
                    title = text.slice(0, 24) + (text.length > 24 ? '...' : '');
                }
                
                return {
                    ...session,
                    title,
                    messages
                };
            }
            return session;
        }));
    };

    const handleEndSession = () => {
        setActiveSessionId(null);
        setIsSidebarOpen(false);
    };

    return (
        <div className="drawer lg:drawer-open h-full font-sans text-base-content">
            <input 
                id="dashboard-drawer" 
                type="checkbox" 
                className="drawer-toggle" 
                checked={isSidebarOpen}
                onChange={(e) => setIsSidebarOpen(e.target.checked)}
            />
            
            <div className="drawer-content flex flex-col h-full bg-base-100 relative overflow-hidden">
                
                {/* Mobile Header */}
                <div className={`lg:hidden navbar absolute top-0 z-40 transition-opacity duration-300 ${activeSessionId && interactionMode === InteractionMode.VOICE ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
                    <div className="flex-none">
                        <label htmlFor="dashboard-drawer" className="btn btn-square btn-ghost">
                            <Menu size={24} className="text-base-content" />
                        </label>
                    </div>
                </div>

                {/* Main Content Area */}
                <div className="flex-1 relative w-full h-full">
                    <AnimatePresence mode="wait">
                        {!activeSessionId ? (
                            <motion.div 
                                key="home"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0, scale: 1.05 }}
                                transition={{ duration: 0.4 }}
                                className="w-full h-full"
                            >
                                <HomePage 
                                    userName={currentUser.name}
                                    onStartVoice={handleStartVoice}
                                    onStartText={handleStartText}
                                />
                            </motion.div>
                        ) : (
                            <motion.div 
                                key="session"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.4 }}
                                className="w-full h-full absolute inset-0 bg-base-100 z-50"
                            >
                                {activeSession && (
                                    <LiveInterface 
                                        mode={interactionMode}
                                        onModeChange={setInteractionMode}
                                        onEndSession={handleEndSession}
                                        messages={activeSession.messages}
                                        onSendMessage={handleUserSendMessage}
                                        onReceiveMessage={(text) => updateActiveSessionMessages({
                                            id: Date.now().toString() + '_ai',
                                            role: 'assistant',
                                            content: text,
                                            timestamp: new Date()
                                        })}
                                        userId={currentUser.id}
                                        userName={currentUser.name}
                                        conversationId={activeSession.id}
                                    />
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div> 
            
            {/* Sidebar Drawer */}
            <div className="drawer-side z-[60]">
                <label htmlFor="dashboard-drawer" aria-label="close sidebar" className="drawer-overlay"></label>
                <div className="w-80 min-h-full bg-base-100 border-r border-base-300 text-base-content p-0">
                    <Sidebar 
                        isOpen={true} 
                        onClose={() => setIsSidebarOpen(false)} 
                        sessions={sessions}
                        onNewChat={handleNewChat}
                        onLogout={onLogout}
                        activeSessionId={activeSessionId}
                        onSelectSession={handleSelectSession}
                        onDeleteSession={handleDeleteSession}
                        onRenameSession={handleRenameSession}
                        theme={theme}
                        toggleTheme={toggleTheme}
                    />
                </div>
            </div>
        </div>
    );
};