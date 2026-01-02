import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ControlPanel } from './ControlPanel';
import { TextChat } from './TextChat';
import { InteractionMode, Message, LiveConnectionState } from '../types';
import { apiService } from '../services/apiService';
import { audioService } from '../services/audioService';
import { motion, AnimatePresence } from 'framer-motion';

interface LiveInterfaceProps {
    mode: InteractionMode;
    onModeChange: (mode: InteractionMode) => void;
    onEndSession: () => void;
    messages: Message[];
    onSendMessage: (text: string) => void;
    onReceiveMessage: (text: string) => void;
    userId?: string;
    conversationId?: string;
}

export const LiveInterface: React.FC<LiveInterfaceProps> = ({ 
    mode,
    onModeChange,
    onEndSession, 
    messages,
    onSendMessage,
    onReceiveMessage,
    userId = 'user_main',
    conversationId
}) => {
    const [connectionState, setConnectionState] = useState<LiveConnectionState>(LiveConnectionState.DISCONNECTED);
    const [isMicActive, setIsMicActive] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [audioLevel, setAudioLevel] = useState(0);
    const conversationIdRef = useRef<string | null>(conversationId || null);
    const userIdRef = useRef<string>(userId);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    
    useEffect(() => {
        userIdRef.current = userId;
    }, [userId]);
    
    useEffect(() => {
        if (conversationId) {
            conversationIdRef.current = conversationId;
        }
    }, [conversationId]);

    // Initialize connection
    useEffect(() => {
        const checkHealth = async () => {
            const isHealthy = await apiService.healthCheck();
            setConnectionState(isHealthy ? LiveConnectionState.CONNECTED : LiveConnectionState.ERROR);
        };
        checkHealth();
    }, []);

    // Send initial greeting when voice mode starts (only once per conversation)
    const hasGreetedRef = useRef<string | null>(null);
    const greetingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // Reset greeting ref when conversation changes
    useEffect(() => {
        if (conversationId && hasGreetedRef.current !== conversationId) {
            hasGreetedRef.current = null; // Reset for new conversation
            if (greetingTimeoutRef.current) {
                clearTimeout(greetingTimeoutRef.current);
                greetingTimeoutRef.current = null;
            }
        }
    }, [conversationId]);
    
    useEffect(() => {
        // Clear any existing timeout
        if (greetingTimeoutRef.current) {
            clearTimeout(greetingTimeoutRef.current);
            greetingTimeoutRef.current = null;
        }
        
        // Check if we should send greeting: voice mode, no messages, connected, and haven't greeted for this conversation
        const currentConvId = conversationIdRef.current || conversationId || 'new';
        const shouldGreet = mode === InteractionMode.VOICE && 
                           messages.length === 0 && 
                           connectionState === LiveConnectionState.CONNECTED && 
                           hasGreetedRef.current !== currentConvId;
        
        if (shouldGreet) {
            console.log('Greeting check: Will send greeting', { 
                mode, 
                messageCount: messages.length, 
                connectionState, 
                currentConvId
            });
            const sendInitialGreeting = async () => {
                try {
                    hasGreetedRef.current = currentConvId; // Mark as greeted for this conversation
                    console.log('Sending initial greeting for voice mode...');
                    const greetingText = "Hey there! How are you doing today?";
                    
                    // Add greeting message to chat
                    onReceiveMessage(greetingText);
                    
                    // Generate and play audio greeting via text processing (with audio)
                    const response = await apiService.processText(
                        greetingText,
                        userIdRef.current,
                        currentConvId !== 'new' ? currentConvId : undefined,
                        true  // Generate audio for the greeting
                    );
                    
                    // Update conversation ID if returned
                    if (response.conversation_id) {
                        conversationIdRef.current = response.conversation_id;
                        hasGreetedRef.current = response.conversation_id; // Update ref with actual ID
                    }
                    
                    // Play audio greeting
                    if (response.audio_base64) {
                        try {
                            const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                            const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                            await audioService.playAudio(audioBlob);
                            console.log('Initial greeting audio played');
                        } catch (error) {
                            console.error('Error playing greeting audio:', error);
                        }
                    } else if (response.audio_url) {
                        try {
                            const audioBlob = await apiService.getAudio(response.audio_url);
                            await audioService.playAudio(audioBlob);
                            console.log('Initial greeting audio played from URL');
                        } catch (error) {
                            console.error('Error playing greeting audio from URL:', error);
                        }
                    } else {
                        console.warn('No audio in greeting response');
                    }
                } catch (error) {
                    console.error('Error sending initial greeting:', error);
                    // Reset on error to allow retry
                    hasGreetedRef.current = null;
                }
            };
            
            // Delay to ensure everything is initialized
            greetingTimeoutRef.current = setTimeout(sendInitialGreeting, 1200);
        }
        
        return () => {
            if (greetingTimeoutRef.current) {
                clearTimeout(greetingTimeoutRef.current);
                greetingTimeoutRef.current = null;
            }
        };
    }, [mode, messages.length, connectionState, onReceiveMessage, conversationId]);

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isProcessing]);

    // Audio level simulation during recording
    useEffect(() => {
        if (!isMicActive || !audioService.isRecording()) {
            setAudioLevel(0);
            return;
        }

        const interval = setInterval(() => {
            setAudioLevel(0.3 + Math.random() * 0.5);
        }, 100);

        return () => clearInterval(interval);
    }, [isMicActive]);

    const handleMicToggle = useCallback(async () => {
        // Prevent multiple clicks during processing
        if (isProcessing) {
            console.log('Already processing, ignoring click');
            return;
        }

        if (isMicActive) {
            // Stop recording and process
            try {
                // Immediately set states to prevent double-click issues
                setIsMicActive(false);
                setIsProcessing(true);
                
                const audioBlob = await audioService.stopRecording();
                
                // Check if audio is too short (likely accidental click)
                // Reduced threshold to 500 bytes for faster response
                if (audioBlob.size < 500) {
                    console.warn('Audio too short, ignoring');
                    setIsProcessing(false);
                    return;
                }
                
                console.log(`Processing audio: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                
                // Check backend connection first (with timeout)
                let isBackendHealthy = false;
                try {
                    const healthCheckPromise = apiService.healthCheck();
                    const timeoutPromise = new Promise<boolean>((resolve) => 
                        setTimeout(() => resolve(false), 3000)
                    );
                    isBackendHealthy = await Promise.race([healthCheckPromise, timeoutPromise]) as boolean;
                } catch (error) {
                    console.warn('Health check failed:', error);
                    isBackendHealthy = false;
                }
                
                if (!isBackendHealthy) {
                    const errorMsg = 'Backend server is not running. Please start it with: python backend/run.py';
                    console.error(errorMsg);
                    onReceiveMessage(`⚠️ ${errorMsg}`);
                    setIsProcessing(false);
                    return;
                }
                
                console.log('Calling processVoice API...');
                const response = await apiService.processVoice(
                    audioBlob,
                    userIdRef.current,
                    conversationIdRef.current || undefined
                );

                console.log('Voice response received:', {
                    hasConversationId: !!response.conversation_id,
                    hasUserText: !!response.user_text,
                    hasTextResponse: !!response.text_response,
                    hasAudioBase64: !!response.audio_base64,
                    hasAudioUrl: !!response.audio_url,
                    responseKeys: Object.keys(response)
                });

                if (!response) {
                    throw new Error('No response received from backend');
                }

                if (response.conversation_id) {
                    conversationIdRef.current = response.conversation_id;
                }
                
                // Add user message (transcribed text)
                if (response.user_text) {
                    console.log('Adding user message:', response.user_text);
                    onSendMessage(response.user_text);
                } else {
                    console.warn('No user_text in response');
                }
                
                // Add assistant message
                if (response.text_response) {
                    console.log('Adding assistant message:', response.text_response);
                    onReceiveMessage(response.text_response);
                } else {
                    console.warn('No text_response in response');
                    onReceiveMessage('I received your message, but I couldn\'t generate a response. Please try again.');
                }
                
                // Play audio response
                if (response.audio_base64) {
                    console.log('Playing audio from base64 response (length:', response.audio_base64.length, 'chars)');
                    try {
                        // Convert base64 to blob
                        // Groq Orpheus returns WAV format, not MP3
                        const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                        const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                        console.log(`Audio blob created: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                        await audioService.playAudio(audioBlob);
                        console.log('Audio playback started');
                    } catch (error) {
                        console.error('Error playing audio from base64:', error);
                        // Don't fail the whole request if audio playback fails
                    }
                } else if (response.audio_url) {
                    console.log('Fetching audio from URL:', response.audio_url);
                    try {
                        const audioBlob = await apiService.getAudio(response.audio_url);
                        await audioService.playAudio(audioBlob);
                        console.log('Audio playback started from URL');
                    } catch (error) {
                        console.error('Error playing audio from URL:', error);
                        // Don't fail the whole request if audio playback fails
                    }
                } else {
                    console.warn('No audio response available in response. Response keys:', Object.keys(response));
                    // This is not necessarily an error - text mode might not have audio
                }
            } catch (error) {
                console.error('Error processing voice:', error);
                const errorMessage = error instanceof Error ? error.message : 'Failed to process voice. Please try again.';
                console.error('Full error details:', {
                    message: errorMessage,
                    error: error,
                    stack: error instanceof Error ? error.stack : undefined
                });
                // Show error in chat instead of alert
                onReceiveMessage(`I'm sorry, I'm having trouble processing your voice. ${errorMessage}`);
                // Don't show alert - error is already in chat
            } finally {
                setIsProcessing(false);
            }
        } else {
            // Start recording
            try {
                console.log('Starting audio recording...');
                // Set mic active immediately for visual feedback
                setIsMicActive(true);
                await audioService.startRecording();
                setConnectionState(LiveConnectionState.CONNECTED);
                console.log('Recording started successfully');
            } catch (error) {
                console.error('Error starting recording:', error);
                const errorMessage = error instanceof Error ? error.message : 'Failed to start recording. Please check microphone permissions.';
                // Show error in chat
                onReceiveMessage(`⚠️ I couldn't start recording. ${errorMessage}`);
                setIsMicActive(false);
                setConnectionState(LiveConnectionState.DISCONNECTED);
            }
        }
    }, [isMicActive, isProcessing, onSendMessage, onReceiveMessage, messages.length]);

    const handleTextSubmit = useCallback(async (text: string) => {
        if (!text.trim() || isProcessing) return;
        
        try {
            setIsProcessing(true);
            
            // Check backend connection first
            const isBackendHealthy = await apiService.healthCheck();
            if (!isBackendHealthy) {
                throw new Error('Backend server is not running. Please start the backend server on http://localhost:5000');
            }
            
            // Add user message to UI (this is handled by parent, but we call it for consistency)
            onSendMessage(text);
            
            // Text mode: Direct LLM only, no TTS
            console.log(`Processing text: "${text}", user: ${userIdRef.current}, conversation: ${conversationIdRef.current || 'new'}`);
            const startTime = Date.now();
            const response = await apiService.processText(
                text,
                userIdRef.current,
                conversationIdRef.current || undefined,
                false  // Don't generate audio for text mode
            );

            const duration = Date.now() - startTime;
            console.log(`Text processing completed in ${duration}ms`);
            console.log('Text response received:', {
                hasConversationId: !!response.conversation_id,
                hasTextResponse: !!response.text_response,
                textResponseLength: response.text_response?.length || 0
            });

            if (!response) {
                throw new Error('No response received from backend');
            }

            if (response.conversation_id) {
                conversationIdRef.current = response.conversation_id;
            }
            
            // Add assistant message
            if (response.text_response) {
                console.log('Adding assistant message:', response.text_response.substring(0, 100) + '...');
                onReceiveMessage(response.text_response);
            } else {
                console.warn('No text_response in response');
                onReceiveMessage('I received your message, but I couldn\'t generate a response. Please try again.');
            }
            
            // Text mode doesn't need audio, but if provided, play it
            if (response.audio_base64) {
                console.log('Playing audio from base64 response');
                try {
                    // Convert base64 to blob
                    // Groq Orpheus returns WAV format, not MP3
                    const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                    console.log(`Audio blob created: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                    await audioService.playAudio(audioBlob);
                    console.log('Audio playback started');
                } catch (error) {
                    console.error('Error playing audio from base64:', error);
                }
            } else if (response.audio_url) {
                console.log('Fetching audio from URL:', response.audio_url);
                try {
                    const audioBlob = await apiService.getAudio(response.audio_url);
                    await audioService.playAudio(audioBlob);
                    console.log('Audio playback started from URL');
                } catch (error) {
                    console.error('Error fetching/playing audio from URL:', error);
                }
            }
        } catch (error) {
            console.error('Error processing text:', error);
            const errorMessage = error instanceof Error ? error.message : 'Failed to process text. Please try again.';
            console.error('Full error details:', {
                message: errorMessage,
                error: error,
                stack: error instanceof Error ? error.stack : undefined
            });
            onReceiveMessage(`I'm sorry, I'm having trouble processing your message. ${errorMessage}`);
            // Show alert for critical errors
            if (errorMessage.includes('Backend server is not running') || errorMessage.includes('Cannot connect to backend') || errorMessage.includes('taking too long')) {
                alert(`Text processing error: ${errorMessage}\n\nPlease check:\n1. Backend server is running on http://localhost:5000\n2. Check browser console for details`);
            }
        } finally {
            setIsProcessing(false);
        }
    }, [isProcessing, onSendMessage, onReceiveMessage]);

    return (
        <div className="relative w-full h-full flex flex-col bg-base-100 overflow-hidden transition-colors duration-300">
            
            {/* --- VOICE MODE VIEW --- */}
            {mode === InteractionMode.VOICE && (
                <div className="absolute inset-0 z-10 flex flex-col">
                    
                    {/* Messages Display Area */}
                    <div className="flex-1 overflow-y-auto overflow-x-hidden pb-32 px-4">
                        <div className="py-6 space-y-6 max-w-3xl mx-auto">
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
                                <div className="chat chat-start">
                                    <div className="chat-bubble bg-base-200 text-base-content border border-base-200">
                                        <span className="inline-flex items-center gap-2">
                                            <span className="loading loading-dots loading-sm"></span>
                                            Processing...
                                        </span>
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    </div>

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
                            isListening={isMicActive || isProcessing}
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