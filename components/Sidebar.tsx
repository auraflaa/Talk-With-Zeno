import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, Plus, Sun, Moon, LogOut, MoreHorizontal, Pencil, Trash2, Share2, Check, X, Settings } from 'lucide-react';
import { ChatSession } from '../types';
import { motion, AnimatePresence } from 'framer-motion';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  sessions: ChatSession[];
  onNewChat: () => void;
  onLogout: () => void;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, newTitle: string) => void;
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  onOpenSettings?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ 
    sessions, 
    onNewChat, 
    onLogout, 
    activeSessionId, 
    onSelectSession,
    onDeleteSession,
    onRenameSession,
    theme,
    toggleTheme,
    onOpenSettings,
}) => {
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
    
    // Rename State
    const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
    const [editTitle, setEditTitle] = useState("");
    const inputRef = useRef<HTMLInputElement>(null);

    // Focus input when editing starts
    useEffect(() => {
        if (editingSessionId && inputRef.current) {
            inputRef.current.focus();
        }
    }, [editingSessionId]);

    const startEditing = (id: string, currentTitle: string) => {
        setEditingSessionId(id);
        setEditTitle(currentTitle);
    };

    const saveEditing = (id: string) => {
        if (editTitle.trim()) {
            onRenameSession(id, editTitle.trim());
        }
        setEditingSessionId(null);
    };

    const cancelEditing = () => {
        setEditingSessionId(null);
        setEditTitle("");
    };

    const handleShare = (id: string) => {
        // Mock share functionality
        alert("Link copied to clipboard!");
    };

  return (
    <>
    <div className="flex flex-col h-full p-4 bg-base-100 text-base-content transition-colors duration-300">
        {/* Brand - Desktop Only */}
        <div className="hidden lg:block pb-6 pl-2">
            <h2 className="text-2xl font-extrabold text-base-content tracking-tight font-display">Talk with Zeno</h2>
        </div>

        {/* New Chat Button - Semantic Primary */}
        <button 
            onClick={onNewChat}
            className="btn bg-primary hover:bg-primary-hover btn-block justify-start gap-3 no-animation font-normal text-white border-none shadow-sm"
        >
            <Plus size={18} />
            New chat
        </button>

        <div className="flex-1 overflow-y-auto py-6 space-y-1">
            <div className="text-xs font-semibold tracking-wide text-base-content/80 uppercase px-2 mb-2">Recent</div>
            <ul className="menu w-full p-0 gap-1 rounded-box">
                {sessions.map((session) => (
                    <li key={session.id} className="relative group">
                        {editingSessionId === session.id ? (
                            // Edit Mode
                            <div className="flex items-center gap-2 py-3 px-3 rounded-lg bg-base-200">
                                <input 
                                    ref={inputRef}
                                    type="text" 
                                    value={editTitle}
                                    onChange={(e) => setEditTitle(e.target.value)}
                                    className="flex-1 bg-transparent border-none outline-none text-sm min-w-0"
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') saveEditing(session.id);
                                        if (e.key === 'Escape') cancelEditing();
                                    }}
                                    onBlur={() => saveEditing(session.id)}
                                />
                                <button onMouseDown={(e) => e.preventDefault()} onClick={() => saveEditing(session.id)} className="text-primary hover:bg-primary/10 rounded p-1"><Check size={14}/></button>
                                <button onMouseDown={(e) => e.preventDefault()} onClick={cancelEditing} className="text-base-content/50 hover:bg-base-300 rounded p-1"><X size={14}/></button>
                            </div>
                        ) : (
                            // View Mode
                            <div className={`flex items-center justify-between py-2 px-3 rounded-lg transition-colors w-full
                                ${activeSessionId === session.id 
                                    ? 'bg-primary/10 text-primary font-medium' 
                                    : 'text-base-content/70 hover:bg-base-200 hover:text-primary'
                                }`}
                            >
                                <button 
                                    onClick={() => onSelectSession(session.id)}
                                    className={`flex items-center gap-3 flex-1 min-w-0 text-left py-1
                                        ${activeSessionId === session.id ? 'text-primary' : 'text-base-content/70'}
                                    `}
                                >
                                    <MessageSquare size={16} className={`flex-shrink-0 ${activeSessionId === session.id ? 'text-primary' : 'text-base-content/40'}`} />
                                    <span className="truncate block text-sm font-medium text-base-content">
                                        {session.title}
                                    </span>
                                </button>

                                {/* Three Dots Menu */}
                                <div className="dropdown dropdown-bottom dropdown-end" onClick={(e) => e.stopPropagation()}>
                                    <div 
                                        tabIndex={0} 
                                        role="button" 
                                        className={`btn btn-ghost btn-xs btn-circle ${activeSessionId === session.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 transition-opacity'}`}
                                    >
                                        <MoreHorizontal size={16} />
                                    </div>
                                    <ul tabIndex={0} className="dropdown-content z-[50] menu p-2 shadow-lg bg-base-100 rounded-box w-40 border border-base-200">
                                        <li>
                                            <button onClick={() => startEditing(session.id, session.title)} className="flex gap-2">
                                                <Pencil size={14} /> Rename
                                            </button>
                                        </li>
                                        <li>
                                            <button onClick={() => handleShare(session.id)} className="flex gap-2">
                                                <Share2 size={14} /> Share
                                            </button>
                                        </li>
                                        <li>
                                            <button onClick={() => onDeleteSession(session.id)} className="flex gap-2 text-error hover:bg-error/10 hover:text-error">
                                                <Trash2 size={14} /> Delete
                                            </button>
                                        </li>
                                    </ul>
                                </div>
                            </div>
                        )}
                    </li>
                ))}
            </ul>
        </div>

        {/* Bottom actions pinned to bottom of sidebar */}
        <div className="mt-auto pt-4 pb-2 border-t border-base-200 space-y-1">
            {/* Settings */}
            <button
                onClick={onOpenSettings}
                className="btn btn-ghost btn-block justify-start gap-3 font-normal text-base-content hover:bg-base-200"
            >
                <Settings size={18} />
                Settings
            </button>

            {/* Theme Toggle */}
            <button 
                onClick={toggleTheme}
                className="btn btn-ghost btn-block justify-start gap-3 font-normal text-base-content hover:bg-base-200"
            >
                {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
                <span>{theme === 'light' ? 'Dark Mode' : 'Light Mode'}</span>
            </button>
            
            {/* Logout Trigger */}
            <button 
                onClick={() => setShowLogoutConfirm(true)} 
                className="btn btn-ghost btn-block justify-start gap-3 font-normal text-error hover:bg-error/10 text-left"
            >
                <LogOut size={18} />
                <span>Sign out</span>
            </button>
        </div>
    </div>

    {/* Logout Confirmation Modal */}
    <AnimatePresence>
        {showLogoutConfirm && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setShowLogoutConfirm(false)}
                    className="absolute inset-0 bg-black/40 backdrop-blur-sm"
                />
                <motion.div 
                    initial={{ scale: 0.95, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.95, opacity: 0 }}
                    className="bg-base-100 rounded-2xl shadow-xl p-6 w-full max-w-sm relative z-10 border border-base-200"
                >
                    <h3 className="text-lg font-bold text-base-content mb-2">Sign out?</h3>
                    <p className="text-base-content/70 mb-6">Are you sure you want to log out of your account?</p>
                    <div className="flex gap-3">
                        <button 
                            onClick={() => setShowLogoutConfirm(false)}
                            className="btn btn-ghost flex-1"
                        >
                            Cancel
                        </button>
                        <button 
                            onClick={onLogout}
                            className="btn btn-error text-white flex-1"
                        >
                            Log out
                        </button>
                    </div>
                </motion.div>
            </div>
        )}
    </AnimatePresence>
    </>
  );
};