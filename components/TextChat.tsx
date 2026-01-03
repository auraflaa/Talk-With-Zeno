import React, { useRef, useEffect, useState } from 'react';
import { Send, Mic, X } from 'lucide-react';
import { Message } from '../types';

interface TextChatProps {
    messages: Message[];
    onSendMessage: (text: string) => void;
    onSwitchToVoice: () => void;
    onEndSession: () => void;
    isProcessing?: boolean;
}

export const TextChat: React.FC<TextChatProps> = ({ messages, onSendMessage, onSwitchToVoice, onEndSession, isProcessing = false }) => {
    const [input, setInput] = useState("");
    const endRef = useRef<HTMLDivElement>(null);
    const messagesContainerRef = useRef<HTMLDivElement>(null);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if(!input.trim()) return;
        onSendMessage(input);
        setInput("");
    };

    // Scroll to bottom when messages change or when processing starts/stops
    useEffect(() => {
        // Use setTimeout to ensure DOM is updated
        setTimeout(() => {
            if (endRef.current) {
                endRef.current.scrollIntoView({ behavior: 'smooth' });
            } else if (messagesContainerRef.current) {
                // Fallback: scroll container to bottom
                messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
            }
        }, 100);
    }, [messages, isProcessing]);
    
    // Initial scroll to bottom on mount
    useEffect(() => {
        if (messagesContainerRef.current) {
            messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
        }
    }, []);

    const isInputEmpty = !input.trim();

    return (
        <div className="flex flex-col h-full w-full max-w-3xl mx-auto relative px-4 transition-colors duration-300">
            
            {/* 
              Messages Area 
              Strict overflow control: auto vertical, hidden horizontal.
              Scrollbars are hidden via global CSS in index.html.
            */}
            <div ref={messagesContainerRef} className="flex-1 overflow-y-auto overflow-x-hidden pb-32">
                <div className="py-6 space-y-6 min-h-full">
                    {messages.length === 0 && !isProcessing && (
                        <div className="flex items-center justify-center h-full">
                            <p className="text-base-content/50 text-sm">Start a conversation by typing a message below</p>
                        </div>
                    )}
                    {messages.map((msg) => (
                        <div key={msg.id} className={`chat ${msg.role === 'user' ? 'chat-end' : 'chat-start'}`}>
                            <div 
                                className={`chat-bubble shadow-sm ${
                                    msg.role === 'user' 
                                    ? 'bg-primary text-white' 
                                    : 'bg-base-200 text-base-content border border-base-200'
                                }`}
                            >
                                {msg.content}
                            </div>
                        </div>
                    ))}
                    {isProcessing && (
                        <div className="chat chat-start animate-in fade-in duration-300">
                            <div className="chat-bubble bg-base-200 text-base-content border border-base-200">
                                <span className="inline-flex items-center gap-2">
                                    <span className="loading loading-dots loading-sm text-primary"></span>
                                    <span className="text-sm opacity-70">Thinking...</span>
                                </span>
                            </div>
                        </div>
                    )}
                    <div ref={endRef} />
                </div>
            </div>

            {/* Input Area + End Conversation */}
            <div className="absolute bottom-6 left-4 right-4 z-50">
                 <form 
                    onSubmit={handleSubmit} 
                    className="flex gap-2 p-1.5 pl-5 rounded-3xl w-full items-center transition-all duration-300 bg-white dark:bg-[#12161C] shadow-lg focus-within:shadow-[inset_0_0_0_1px_rgb(31,122,110),0_0_15px_rgba(31,122,110,0.15)]"
                 >
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Type a message..."
                        className="flex-1 bg-transparent border-none outline-none text-base-content placeholder:text-base-content/40 h-10 min-w-0"
                    />
                    
                    <div className="flex items-center gap-1 pr-1">
                        {/* Switch to Voice - Tooltip Only */}
                        <div className="relative group">
                            <button 
                                type="button"
                                onClick={onSwitchToVoice}
                                aria-label="Switch to voice mode"
                                className="p-2 rounded-full text-primary hover:opacity-80 transition-opacity focus:outline-none"
                            >
                                <Mic size={20} />
                            </button>
                             {/* Tooltip */}
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 px-3 py-1.5 bg-gray-900 dark:bg-gray-800 text-white text-xs font-medium rounded-lg opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 transition-all duration-200 pointer-events-none whitespace-nowrap shadow-sm z-50">
                                Switch to voice mode
                            </div>
                        </div>
                        
                        {/* Send Button */}
                        <button 
                            type="submit"
                            disabled={isInputEmpty}
                            className={`p-2 rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none ${
                                isInputEmpty
                                ? 'text-gray-400 cursor-not-allowed'
                                : 'text-primary scale-100 active:scale-95'
                            }`}
                            aria-label="Send message"
                        >
                            <Send size={20} className={!isInputEmpty ? "ml-0.5" : ""} />
                        </button>

                        {/* Divider */}
                        <div className="h-5 w-px bg-base-300 mx-1.5 opacity-50"></div>

                        {/* End Conversation Button - Red, Icon+Text, Right Aligned */}
                        <button 
                            type="button"
                            onClick={onEndSession}
                            className="flex items-center gap-1.5 px-3 py-2 rounded-full text-[#E5533D] hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors mr-1"
                            aria-label="End conversation"
                        >
                            <span className="text-sm font-medium whitespace-nowrap">End</span>
                            <X size={18} />
                        </button>
                    </div>
                 </form>
            </div>
        </div>
    );
};