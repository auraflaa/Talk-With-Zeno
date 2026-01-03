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
    userName?: string;
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
    userName,
    conversationId
}) => {
    const [connectionState, setConnectionState] = useState<LiveConnectionState>(LiveConnectionState.DISCONNECTED);
    const [isMicActive, setIsMicActive] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [audioLevel, setAudioLevel] = useState(0);
    const conversationIdRef = useRef<string | null>(conversationId || null);
    const userIdRef = useRef<string>(userId);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const recordingStartTimeRef = useRef<number | null>(null);
    
    useEffect(() => {
        userIdRef.current = userId;
    }, [userId]);
    
    useEffect(() => {
        if (conversationId) {
            conversationIdRef.current = conversationId;
        }
    }, [conversationId]);

    // Initialize connection and check backend health periodically
    useEffect(() => {
        const checkHealth = async () => {
            try {
                const isHealthy = await apiService.healthCheck();
                if (isHealthy) {
                    setConnectionState(LiveConnectionState.CONNECTED);
                } else {
                    setConnectionState(LiveConnectionState.DISCONNECTED);
                    // Show warning in chat if backend is down and we're in voice mode
                    if (mode === InteractionMode.VOICE && messages.length === 0) {
                        onReceiveMessage('⚠️ Backend server is not running. Please start it with: python backend/run.py');
                    }
                }
            } catch (error) {
                console.error('Health check failed:', error);
                setConnectionState(LiveConnectionState.DISCONNECTED);
                // Show warning in chat if backend is down and we're in voice mode
                if (mode === InteractionMode.VOICE && messages.length === 0) {
                    onReceiveMessage('⚠️ Backend server is not running. Please start it with: python backend/run.py');
                }
            }
        };
        
        checkHealth();
        // Check more frequently (every 5 seconds) to catch backend issues faster
        const interval = setInterval(checkHealth, 5000);
        return () => clearInterval(interval);
    }, [mode, messages.length, onReceiveMessage]);

    // Send initial greeting when voice mode starts (only once per conversation)
    const hasGreetedRef = useRef<string | null>(null);
    const greetingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const hasAutoStartedRef = useRef<boolean>(false);
    
    // Reset greeting ref when conversation changes
    useEffect(() => {
        if (conversationId && hasGreetedRef.current !== conversationId) {
            hasGreetedRef.current = null; // Reset for new conversation
            hasAutoStartedRef.current = false; // Reset auto-start flag
            if (greetingTimeoutRef.current) {
                clearTimeout(greetingTimeoutRef.current);
                greetingTimeoutRef.current = null;
            }
        }
    }, [conversationId]);
    
    // Reset auto-start flag when mode changes or when user manually stops recording
    useEffect(() => {
        if (mode !== InteractionMode.VOICE) {
            hasAutoStartedRef.current = false;
        }
    }, [mode]);
    
    // Reset auto-start flag when mic is manually stopped (so it can auto-start again)
    useEffect(() => {
        if (!isMicActive && !isProcessing && mode === InteractionMode.VOICE) {
            // Only reset if we're in voice mode and not processing
            // This allows auto-restart after processing completes
            const resetTimeout = setTimeout(() => {
                if (!isMicActive && !isProcessing) {
                    hasAutoStartedRef.current = false;
                }
            }, 1000);
            return () => clearTimeout(resetTimeout);
        }
    }, [isMicActive, isProcessing, mode]);
    
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
                    
                    // Send a special greeting request to backend
                    // Use a simple greeting prompt that will generate a natural greeting
                    const greetingPrompt = "Start the conversation with a friendly greeting.";
                    
                    // Generate and play audio greeting via text processing (with audio)
                    const response = await apiService.processText(
                        greetingPrompt,
                        userIdRef.current,
                        currentConvId !== 'new' ? currentConvId : undefined,
                        true,  // Generate audio for the greeting
                        userName
                    );
                    
                    // Update conversation ID if returned
                    if (response.conversation_id) {
                        conversationIdRef.current = response.conversation_id;
                        hasGreetedRef.current = response.conversation_id; // Update ref with actual ID
                    }
                    
                    // Only add the assistant's response to chat (not the user prompt)
                    if (response.text_response) {
                        console.log('Adding greeting response to chat:', response.text_response);
                        onReceiveMessage(response.text_response);
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
                    
                    // Mark greeting as done - auto-start will happen via the useEffect hook
                    // This ensures consistent auto-start behavior
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
    }, [mode, messages.length, connectionState, onReceiveMessage, conversationId, isMicActive, isProcessing]);

    // Auto-scroll to bottom when messages change
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isProcessing]);

    // Auto-start microphone when voice mode is activated
    useEffect(() => {
        // Auto-start if:
        // 1. Voice mode is active
        // 2. Backend is connected
        // 3. Mic is not already active
        // 4. Not currently processing
        // 5. Haven't auto-started yet
        const shouldAutoStart = mode === InteractionMode.VOICE && 
            connectionState === LiveConnectionState.CONNECTED && 
            !isMicActive && 
            !isProcessing &&
            !hasAutoStartedRef.current;
        
        if (shouldAutoStart) {
            // For new conversations, wait a bit for greeting; for existing, start immediately
            // But don't wait too long - start within 1 second if no greeting is coming
            const delay = messages.length === 0 && hasGreetedRef.current === null ? 1500 : 300;
            
            const autoStartTimeout = setTimeout(async () => {
                try {
                    // Double-check conditions before starting
                    // Don't auto-start if audio is playing (prevents feedback loop)
                    if (mode === InteractionMode.VOICE && 
                        connectionState === LiveConnectionState.CONNECTED && 
                        !isMicActive && 
                        !isProcessing &&
                        !audioService.isPlaying()) { // Don't start while AI is speaking
                        console.log('Auto-starting microphone in voice mode...');
                        setIsMicActive(true);
                        await audioService.startRecording();
                        hasAutoStartedRef.current = true;
                        console.log('Microphone auto-started successfully');
                    } else if (audioService.isPlaying()) {
                        // Audio is playing - don't auto-start to prevent feedback
                        // User can manually start mic if they want to interrupt
                        console.log('Audio is playing, skipping auto-start to prevent feedback loop');
                    }
                } catch (error) {
                    console.error('Error auto-starting microphone:', error);
                    setIsMicActive(false);
                }
            }, delay);
            
            return () => clearTimeout(autoStartTimeout);
        }
    }, [mode, connectionState, isMicActive, isProcessing, messages.length]);

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
    
    // Auto-stop recording after maximum duration (prevent huge files)
    const maxRecordingDurationRef = useRef<NodeJS.Timeout | null>(null);
    useEffect(() => {
        // Clear any existing timeout
        if (maxRecordingDurationRef.current) {
            clearTimeout(maxRecordingDurationRef.current);
            maxRecordingDurationRef.current = null;
        }
        
        if (!isMicActive || !audioService.isRecording()) {
            return;
        }
        
        // Set timeout to auto-stop after 60 seconds
        maxRecordingDurationRef.current = setTimeout(() => {
            console.warn('Maximum recording duration reached (60s), auto-stopping...');
            if (isMicActive && !isProcessing && audioService.isRecording()) {
                // Force stop the recording
                audioService.forceStop();
                setIsMicActive(false);
                onReceiveMessage('⚠️ Recording stopped automatically after 60 seconds. Please try a shorter recording.');
            }
        }, 60000); // 60 seconds max
        
        return () => {
            if (maxRecordingDurationRef.current) {
                clearTimeout(maxRecordingDurationRef.current);
                maxRecordingDurationRef.current = null;
            }
        };
    }, [isMicActive, isProcessing]);

    const handleMicToggle = useCallback(async () => {
        // Prevent multiple clicks during processing
        if (isProcessing) {
            console.log('Already processing, ignoring click');
            return;
        }

        if (isMicActive) {
            // Stop recording and process
            try {
                // Check if recording is actually active before trying to stop
                if (!audioService.isRecording()) {
                    console.warn('No active recording to stop');
                    setIsMicActive(false);
                    setIsProcessing(false);
                    return;
                }
                
                // Don't process if AI is currently speaking (prevents feedback loop)
                if (audioService.isPlaying()) {
                    console.log('AI is speaking, stopping audio and restarting recording instead of processing');
                    audioService.stopAudio();
                    // Restart recording instead of processing
                    try {
                        await audioService.startRecording();
                        console.log('Recording restarted after stopping AI audio');
                    } catch (error) {
                        console.error('Error restarting recording:', error);
                        setIsMicActive(false);
                    }
                    return;
                }
                
                // Check minimum recording duration (at least 500ms to ensure chunks are collected)
                const minRecordingDuration = 500; // Minimum 500ms recording
                const elapsed = recordingStartTimeRef.current 
                    ? Date.now() - recordingStartTimeRef.current 
                    : 0;
                
                if (elapsed < minRecordingDuration) {
                    // Wait a bit more to ensure we have audio chunks
                    const waitTime = minRecordingDuration - elapsed;
                    console.log(`Recording duration: ${elapsed}ms. Waiting ${waitTime}ms more to ensure audio chunks are collected...`);
                    await new Promise(resolve => setTimeout(resolve, waitTime));
                } else {
                    console.log(`Recording duration: ${elapsed}ms (meets minimum of ${minRecordingDuration}ms)`);
                }
                
                recordingStartTimeRef.current = null; // Reset after use
                
                // Immediately set states to prevent double-click issues
                setIsMicActive(false);
                setIsProcessing(true);
                
                // Add a temporary "transcribing..." message so user knows their voice is being processed
                const tempTranscribingId = Date.now().toString() + '_transcribing';
                onSendMessage('[Transcribing your voice...]');
                
                const audioBlob = await audioService.stopRecording();
                
                // Check if audio is too short (likely accidental click or silence)
                // Reasonable threshold to filter out very short clips while allowing normal speech
                const minAudioSize = 1000; // 1KB minimum - filters out silence but allows normal speech
                if (audioBlob.size < minAudioSize) {
                    console.warn(`Audio too short (${audioBlob.size} bytes), ignoring. Minimum: ${minAudioSize} bytes`);
                    console.warn('This might be due to: 1) Recording stopped too quickly, 2) No speech detected, 3) Microphone issue');
                    setIsProcessing(false);
                    // Don't auto-restart - let user manually start again
                    // This prevents infinite loops
                    return;
                }
                
                console.log(`Processing audio: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
                
                // Backend was already checked before recording started, but double-check quickly
                // (in case backend went down during recording)
                let isBackendHealthy = false;
                try {
                    const healthCheckPromise = apiService.healthCheck();
                    const timeoutPromise = new Promise<boolean>((resolve) => 
                        setTimeout(() => resolve(false), 2000) // Faster check
                    );
                    isBackendHealthy = await Promise.race([healthCheckPromise, timeoutPromise]) as boolean;
                } catch (error) {
                    console.warn('Health check failed:', error);
                    isBackendHealthy = false;
                }
                
                if (!isBackendHealthy) {
                    const errorMsg = 'Backend server stopped during recording. Please restart it with: python backend/run.py';
                    console.error(errorMsg);
                    onReceiveMessage(`⚠️ ${errorMsg}`);
                    setIsProcessing(false);
                    return;
                }
                
                console.log('Calling processVoice API...');
                const response = await apiService.processVoice(
                    audioBlob,
                    userIdRef.current,
                    conversationIdRef.current || undefined,
                    'en-US',
                    userName
                );

                console.log('Voice response received:', {
                    hasConversationId: !!response.conversation_id,
                    hasUserText: !!response.user_text,
                    userTextValue: response.user_text || 'MISSING',
                    hasTextResponse: !!response.text_response,
                    textResponseValue: response.text_response ? response.text_response.substring(0, 50) + '...' : 'MISSING',
                    hasAudioBase64: !!response.audio_base64,
                    hasAudioUrl: !!response.audio_url,
                    responseKeys: Object.keys(response),
                    fullResponse: response
                });

                if (!response) {
                    throw new Error('No response received from backend');
                }

                if (response.conversation_id) {
                    conversationIdRef.current = response.conversation_id;
                }
                
                // Add user message (transcribed text) FIRST - this is what the user said
                // Replace the "[Transcribing...]" message with the actual transcription
                if (response.user_text && response.user_text.trim()) {
                    console.log('Adding user message (transcribed text):', response.user_text);
                    // The previous "[Transcribing...]" message will be replaced by this
                    // We need to update the last user message instead of adding a new one
                    // For now, just add it - the Dashboard will handle duplicates
                    onSendMessage(response.user_text.trim());
                } else {
                    console.error('CRITICAL: No user_text in response or user_text is empty');
                    console.error('Response keys:', Object.keys(response));
                    console.error('Full response:', JSON.stringify(response, null, 2));
                    // Replace transcribing message with error
                    onSendMessage('[Transcription failed - your voice was recorded but could not be converted to text]');
                }
                
                // Add assistant message AFTER user message
                if (response.text_response && response.text_response.trim()) {
                    console.log('Adding assistant message:', response.text_response);
                    onReceiveMessage(response.text_response.trim());
                } else {
                    console.warn('No text_response in response or text_response is empty');
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
                
                // Check backend BEFORE starting recording (so user knows immediately if it's down)
                let isBackendHealthy = false;
                try {
                    const healthCheckPromise = apiService.healthCheck();
                    const timeoutPromise = new Promise<boolean>((resolve) => 
                        setTimeout(() => resolve(false), 2000) // Faster check (2 seconds)
                    );
                    isBackendHealthy = await Promise.race([healthCheckPromise, timeoutPromise]) as boolean;
                } catch (error) {
                    console.warn('Health check failed before recording:', error);
                    isBackendHealthy = false;
                }
                
                if (!isBackendHealthy) {
                    const errorMsg = 'Backend server is not running. Please start it with: python backend/run.py';
                    console.error(errorMsg);
                    onReceiveMessage(`⚠️ ${errorMsg}`);
                    setConnectionState(LiveConnectionState.DISCONNECTED);
                    return; // Don't start recording if backend is down
                }
                
                // CRITICAL: Force stop any existing recording first
                if (audioService.isRecording()) {
                    console.warn('WARNING: Recording already active, forcing stop before starting new one');
                    try {
                        audioService.forceStop();
                        // Wait a moment for cleanup
                        await new Promise(resolve => setTimeout(resolve, 200));
                    } catch (e) {
                        console.warn('Error force stopping:', e);
                    }
                }
                
                // Stop any currently playing audio when user starts speaking
                if (audioService.isPlaying()) {
                    console.log('Stopping AI audio playback - user is speaking');
                    audioService.stopAudio();
                }
                
                // Set mic active immediately for visual feedback
                setIsMicActive(true);
                recordingStartTimeRef.current = Date.now(); // Track when recording starts
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
                false,  // Don't generate audio for text mode
                userName
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
                    <div className="flex-1 overflow-y-auto overflow-x-hidden pb-32 px-4 pt-20">
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

                    {/* Dynamic Wave Visual - Anchored Bottom */}
                    <AnimatePresence>
                        {(isMicActive || isProcessing) && (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.3 }}
                                className="absolute bottom-0 left-0 right-0 z-0 pointer-events-none overflow-hidden h-[50%]"
                            >
                                {/* Multiple Wave Layers for Richer Effect */}
                                
                                {/* Layer 1: Core Glow - Primary Color */}
                                <motion.div 
                                    className="absolute bottom-0 w-full bg-gradient-to-t from-primary/50 via-primary/30 to-transparent blur-3xl"
                                    animate={{ 
                                        height: `${Math.max(30, audioLevel * 100)}%`,
                                    }}
                                    transition={{ type: "spring", stiffness: 200, damping: 25 }}
                                />
                                
                                {/* Layer 2: Secondary Wave */}
                                <motion.div 
                                    className="absolute bottom-0 w-[110%] -left-[5%] h-40 bg-primary/20 blur-2xl rounded-[50%]"
                                    animate={{ 
                                        scaleY: [1, 1.4, 1],
                                        scaleX: [1, 1.1, 1],
                                        opacity: [0.4, 0.7, 0.4]
                                    }}
                                    transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
                                />
                                
                                {/* Layer 3: Tertiary Wave - Slower */}
                                <motion.div 
                                    className="absolute bottom-0 w-[130%] -left-[15%] h-48 bg-primary/15 blur-xl rounded-[50%]"
                                    animate={{ 
                                        scaleY: [1, 1.6, 1],
                                        scaleX: [1, 1.2, 1],
                                        opacity: [0.3, 0.6, 0.3]
                                    }}
                                    transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
                                />
                                
                                {/* Layer 4: Base Wave - Largest */}
                                <motion.div 
                                    className="absolute bottom-0 w-[150%] -left-[25%] h-56 bg-primary/10 blur-2xl rounded-[50%]"
                                    animate={{ 
                                        scaleY: [1, 1.8, 1],
                                        scaleX: [1, 1.3, 1],
                                        opacity: [0.2, 0.5, 0.2]
                                    }}
                                    transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
                                />
                                
                                {/* Animated Ripple Effect */}
                                {[0, 1, 2].map((i) => (
                                    <motion.div
                                        key={i}
                                        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-64 h-64 bg-primary/5 rounded-full blur-2xl"
                                        animate={{
                                            scale: [0.8, 1.5, 0.8],
                                            opacity: [0.3, 0, 0.3],
                                        }}
                                        transition={{
                                            duration: 3,
                                            repeat: Infinity,
                                            delay: i * 1,
                                            ease: "easeOut"
                                        }}
                                    />
                                ))}
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* LIVE Indicator - Fixed position to avoid overlap */}
                    {connectionState === LiveConnectionState.CONNECTED && (
                        <div className="absolute top-4 left-0 w-full flex justify-center z-30 pointer-events-none">
                            <div className="bg-primary/10 backdrop-blur-md px-3 py-1 rounded-full flex items-center gap-2 border border-primary/20">
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
                        isProcessing={isProcessing}
                    />
                </div>
            )}
        </div>
    );
};