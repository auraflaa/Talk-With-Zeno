import React from 'react';
import { motion } from 'framer-motion';
import { Mic, MicOff, MessageSquare, X } from 'lucide-react';

interface ControlPanelProps {
  isListening: boolean;
  onMicToggle: () => void;
  onEndSession: () => void;
  onSwitchToText: () => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({ 
    isListening, 
    onMicToggle, 
    onEndSession,
    onSwitchToText
}) => {
  return (
    <motion.div 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="w-full max-w-lg mx-auto pb-8 px-6"
    >
      <div className="bg-base-100/90 backdrop-blur-2xl border border-base-200 rounded-3xl p-3 pr-4 shadow-2xl flex items-center justify-between relative z-50">
        
        {/* Switch to Text */}
        <div className="relative group">
            <button 
                onClick={onSwitchToText}
                aria-label="Switch to text mode"
                className="p-3 text-base-content/60 hover:text-base-content/90 transition-colors duration-200 flex items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-full"
            >
                <MessageSquare size={20} />
            </button>
            
            {/* Custom Tooltip */}
            <div className="absolute left-full top-1/2 -translate-y-1/2 ml-3 px-3 py-1.5 bg-gray-800 text-gray-200 text-xs font-medium rounded-lg opacity-0 scale-95 group-hover:opacity-100 group-hover:scale-100 transition-all duration-200 pointer-events-none whitespace-nowrap shadow-sm z-50">
                Switch to text mode
            </div>
        </div>

        {/* Center Mic */}
        <div className="absolute left-1/2 -translate-x-1/2 -translate-y-12">
            <button 
                onClick={onMicToggle}
                className={`btn btn-circle btn-lg shadow-xl border-4 border-base-100 transition-all duration-300 ${
                    isListening 
                    ? 'bg-primary hover:bg-primary-hover text-white shadow-xl scale-110' 
                    : 'bg-neutral text-white hover:bg-neutral-focus'
                }`}
                title={isListening ? "Mute Microphone" : "Unmute Microphone"}
            >
                {isListening ? <Mic size={32} /> : <MicOff size={32} />}
            </button>
        </div>

        {/* End Session - Red Text + Icon */}
        <button 
            onClick={onEndSession}
            className="flex items-center gap-1.5 px-3 py-2 rounded-full text-[#E5533D] hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors"
            title="End Conversation"
        >
            <span className="text-sm font-medium">End</span>
            <X size={20} />
        </button>
      </div>
    </motion.div>
  );
};