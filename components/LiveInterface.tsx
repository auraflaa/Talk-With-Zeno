import React, { useState, useEffect, useCallback } from 'react';
import { ControlPanel } from './ControlPanel';
import { TextChat } from './TextChat';
import { InteractionMode, Message, LiveConnectionState } from '../types';
import { MockLiveService } from '../services/mockLiveService';
import { motion, AnimatePresence } from 'framer-motion';

interface LiveInterfaceProps {
    mode: InteractionMode;
    onModeChange: (mode: InteractionMode) => void;
    onEndSession: () => void;
    messages: Message[];
    onSendMessage: (text: string) => void;
    onReceiveMessage: (text: string) => void;
}

export const LiveInterface: React.FC<LiveInterfaceProps> = ({ 
    mode,
    onModeChange,
    onEndSession, 
    messages,
    onSendMessage,
    onReceiveMessage
}) => {
    // Live Service State
    const [connectionState, setConnectionState] = useState<LiveConnectionState>(LiveConnectionState.DISCONNECTED);
    const [liveService, setLiveService] = useState<MockLiveService | null>(null);
    const [isMicActive, setIsMicActive] = useState(mode === InteractionMode.VOICE);
    
    // Wave Animation State
    const [audioLevel, setAudioLevel] = useState(0);

    // Initialize Service
    useEffect(() => {
        const service = new MockLiveService(
            (state) => setConnectionState(state),
            (audio) => {
                 // Audio received logic
            },
            (text, isFinal) => {
                if (isFinal) {
                    onReceiveMessage(text);
                }
            }
        );
        setLiveService(service);
        service.connect({ model: 'gemini-mock' });
        
        return () => {
            service.disconnect();
        };
    }, []);

    // Sync mic state with mode changes
    useEffect(() => {
        if (mode === InteractionMode.VOICE) {
            setIsMicActive(true);
        } else {
            setIsMicActive(false);
        }
    }, [mode]);

    // Simulate Audio Levels for Wave Animation
    useEffect(() => {
        if (!isMicActive) {
            setAudioLevel(0);
            return;
        }

        const interval = setInterval(() => {
            setAudioLevel(0.2 + Math.random() * 0.6);
        }, 100);

        return () => clearInterval(interval);
    }, [isMicActive]);

    const handleMicToggle = useCallback(() => {
        setIsMicActive(prev => !prev);
    }, []);

    const handleTextSubmit = (text: string) => {
        if (!liveService) return;
        onSendMessage(text);
        liveService.sendText(text);
    };

    return (
        <div className="relative w-full h-full flex flex-col bg-base-100 overflow-hidden transition-colors duration-300">
            
            {/* --- VOICE MODE VIEW --- */}
            {mode === InteractionMode.VOICE && (
                <div className="absolute inset-0 z-10 flex flex-col">
                    
                    {/* Empty Center - STRICT: No Gray Circle */}
                    <div className="flex-1"></div>

                    {/* Dynamic Green Wave Visual - Anchored Bottom */}
                    <AnimatePresence>
                        {isMicActive && (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.5 }}
                                className="absolute bottom-0 left-0 right-0 z-0 pointer-events-none overflow-hidden flex items-end justify-center h-[40%]"
                            >
                                {/* Core Glow - Primary */}
                                <motion.div 
                                    className="w-full bg-gradient-to-t from-primary/40 via-primary/20 to-transparent blur-3xl"
                                    animate={{ 
                                        height: `${audioLevel * 100}%`,
                                    }}
                                    transition={{ type: "spring", stiffness: 300, damping: 20 }}
                                />
                                
                                {/* Wave Line Representation */}
                                <motion.div 
                                    className="absolute bottom-0 w-[120%] h-32 bg-primary/10 blur-xl rounded-[50%]"
                                    animate={{ 
                                        scaleY: [1, 1.5, 1],
                                        opacity: [0.3, 0.6, 0.3]
                                    }}
                                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                                />
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* LIVE Indicator - Only if needed, strictly minimal */}
                    {connectionState === LiveConnectionState.CONNECTED && (
                        <div className="absolute top-6 left-0 w-full flex justify-center z-20 pointer-events-none">
                            <div className="bg-primary/10 backdrop-blur-md px-3 py-1 rounded-full flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                                <span className="text-xs font-bold text-primary uppercase tracking-widest">Live</span>
                            </div>
                        </div>
                    )}

                    {/* Bottom Controls */}
                    <div className="relative z-20 w-full mb-12">
                        <ControlPanel 
                            isListening={isMicActive}
                            onMicToggle={handleMicToggle}
                            onEndSession={onEndSession}
                            onSwitchToText={() => onModeChange(InteractionMode.TEXT)}
                        />
                    </div>
                </div>
            )}

            {/* --- TEXT MODE VIEW --- */}
            {mode === InteractionMode.TEXT && (
                <div className="absolute inset-0 z-10 flex flex-col bg-base-100">
                    <TextChat 
                        messages={messages} 
                        onSendMessage={handleTextSubmit} 
                        onSwitchToVoice={() => onModeChange(InteractionMode.VOICE)}
                        onEndSession={onEndSession}
                    />
                </div>
            )}
        </div>
    );
};