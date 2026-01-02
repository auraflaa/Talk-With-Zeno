import React from 'react';
import { motion } from 'framer-motion';
import { Mic, MessageSquare } from 'lucide-react';

interface HomePageProps {
    onStartVoice: () => void;
    onStartText: (text?: string) => void;
    userName?: string;
}

export const HomePage: React.FC<HomePageProps> = ({ onStartVoice, onStartText, userName = "there" }) => {
    const suggestions = [
        "I just want to talk",
        "I feel overwhelmed",
        "Help me think clearly",
        "I don’t know what to say"
    ];

    return (
        <div className="relative w-full h-full flex flex-col items-center justify-center overflow-hidden transition-colors duration-300 bg-[linear-gradient(to_bottom,#FFFFFF,rgba(31,122,110,0.04))] dark:bg-[linear-gradient(to_bottom,#0F1720,rgba(31,122,110,0.06))]">
            
            {/* Main Content */}
            <div className="relative z-10 flex flex-col items-center max-w-lg w-full px-6">
                
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    className="text-center mb-6"
                >
                    <h1 className="text-4xl md:text-5xl font-bold mb-3 font-display tracking-tight text-base-content dark:text-[#F5F7FA]">
                        Hey {userName}.
                    </h1>
                    <p className="text-xl font-light text-base-content/90 dark:text-[rgba(245,247,250,0.8)]">
                        How can I help?
                    </p>
                </motion.div>

                {/* Soft Prompt Chips */}
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.3, duration: 0.8 }}
                    className="flex flex-wrap justify-center gap-2.5 mb-10 w-full max-w-[420px]"
                >
                    {suggestions.map((text, idx) => (
                        <button
                            key={idx}
                            onClick={() => onStartText(text)}
                            className="rounded-full border px-4 py-2 text-sm font-medium transition-colors duration-200 outline-none
                            border-[rgba(31,122,110,0.4)] text-[rgb(31,122,110)] hover:bg-[rgba(31,122,110,0.08)]
                            dark:border-[rgba(255,255,255,0.22)] dark:text-[#E6E6E6] 
                            dark:hover:bg-[rgba(31,122,110,0.18)] dark:hover:border-[rgb(31,122,110)]
                            bg-transparent"
                        >
                            {text}
                        </button>
                    ))}
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2, duration: 0.5 }}
                    className="flex flex-col gap-4 w-full items-center"
                >
                    {/* Primary Voice Action */}
                    <button 
                        onClick={onStartVoice}
                        className="group relative w-24 h-24 rounded-full bg-base-100 shadow-[0_10px_40px_rgba(0,0,0,0.08)] flex items-center justify-center transition-all duration-300 hover:scale-105 hover:shadow-xl border border-base-200 
                        dark:bg-[#111827] dark:border-none dark:shadow-[0_8px_20px_rgba(0,0,0,0.35)]"
                    >
                        <div className="absolute inset-0 bg-primary/10 rounded-full scale-0 group-hover:scale-100 transition-transform duration-500" />
                        <Mic size={32} className="text-primary" />
                    </button>
                    <span className="text-sm font-medium text-base-content/50 dark:text-[rgba(245,247,250,0.5)] mt-1">Start talking</span>

                    {/* Type Instead Button */}
                    <button 
                        onClick={() => onStartText()}
                        className="mt-6 flex items-center gap-2 px-6 py-3 rounded-full text-sm font-medium transition-colors duration-200 outline-none
                        bg-transparent border border-[rgba(31,122,110,0.35)] text-[rgb(31,122,110)]
                        hover:bg-[rgba(31,122,110,0.08)] hover:border-[rgb(31,122,110)]
                        
                        dark:bg-[rgba(255,255,255,0.04)] 
                        dark:border-[rgba(255,255,255,0.14)] 
                        dark:text-[#E6E6E6]
                        dark:hover:bg-[rgba(31,122,110,0.18)] 
                        dark:hover:border-[rgb(31,122,110)]"
                    >
                        <MessageSquare size={16} />
                        <span>Type instead</span>
                    </button>
                </motion.div>

            </div>
        </div>
    );
};