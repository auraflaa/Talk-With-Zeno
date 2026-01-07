import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ControlPanel } from './ControlPanel';
import { TextChat } from './TextChat';
import { InteractionMode, Message, LiveConnectionState } from '../types';
import { apiService, VoiceResponse } from '../services/apiService';
import { audioService } from '../services/audioService';
import { greetingService } from '../services/greetingService';
import { motion, AnimatePresence } from 'framer-motion';
import { MarkdownMessage } from './MarkdownMessage';
import { logWithTimestamp, warnWithTimestamp, errorWithTimestamp } from '../utils/logger';

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
    // Consolidated processing state: single source of truth
    const [isProcessing, setIsProcessing] = useState(false);
    const [audioLevel, setAudioLevel] = useState(0);
    const [liveTranscription, setLiveTranscription] = useState<string>(''); // Live transcription text
    // Notification state for side notifications (not main messages)
    const [notification, setNotification] = useState<{ message: string; id: number } | null>(null);
    const conversationIdRef = useRef<string | null>(conversationId || null);
    const userIdRef = useRef<string>(userId);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const recordingStartTimeRef = useRef<number | null>(null);
    const isMountedRef = useRef<boolean>(true); // Track if component is mounted
    const lastClickTimeRef = useRef<number>(0); // For debouncing
    const currentRequestAbortControllerRef = useRef<AbortController | null>(null); // For request cancellation
    // Removed: vadProcessingRef - using isProcessing state as single source of truth
    
    // Streaming STT state
    const streamingSessionIdRef = useRef<string | null>(null);
    const streamingChunkIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const streamingChunksRef = useRef<Blob[]>([]); // Accumulated chunks for current speech
    const lastChunkTimeRef = useRef<number>(0);
    const CHUNK_INTERVAL_MS = 1500; // Send chunk every 1.5 seconds (faster response)
    
    // STT error tracking
    const sttErrorCountRef = useRef<number>(0); // Track consecutive STT errors
    const lastSttErrorTimeRef = useRef<number>(0); // Track when last STT error occurred
    
    useEffect(() => {
        userIdRef.current = userId;
    }, [userId]);
    
    useEffect(() => {
        if (conversationId) {
            conversationIdRef.current = conversationId;
        }
    }, [conversationId]);

    // Cleanup on unmount
    useEffect(() => {
        isMountedRef.current = true;
        return () => {
            isMountedRef.current = false;
            // Cancel any pending requests
            if (currentRequestAbortControllerRef.current) {
                currentRequestAbortControllerRef.current.abort();
                currentRequestAbortControllerRef.current = null;
            }
            // Reset processing state
            setIsProcessing(false);
            // Clear any intervals
            if (streamingChunkIntervalRef.current) {
                clearInterval(streamingChunkIntervalRef.current);
                streamingChunkIntervalRef.current = null;
            }
            // Cleanup audio service
            // CRITICAL: Don't force stop if mic should still be active (component might be re-rendering)
            // Only force stop if component is actually unmounting
            if (audioService.isRecording() && !isMicActive) {
                audioService.forceStop();
            }
            audioService.stopAudio();
        };
    }, []);

    // Initialize connection and check backend health periodically
    useEffect(() => {
        if (!isMountedRef.current) return;
        
        const checkHealth = async () => {
            if (!isMountedRef.current) return;
            try {
                const isHealthy = await apiService.healthCheck();
                if (!isMountedRef.current) return;
                if (isHealthy) {
                    setConnectionState(LiveConnectionState.CONNECTED);
                } else {
                    setConnectionState(LiveConnectionState.DISCONNECTED);
                    // Show warning in chat if backend is down and we're in voice mode
                    if (mode === InteractionMode.VOICE && messages.length === 0 && isMountedRef.current) {
                        onReceiveMessage('⚠️ Backend server is not running. Please start it with: python backend/run.py');
                    }
                }
            } catch (error) {
                if (!isMountedRef.current) return;
                console.error('Health check failed:', error);
                setConnectionState(LiveConnectionState.DISCONNECTED);
                // Show warning in chat if backend is down and we're in voice mode
                if (mode === InteractionMode.VOICE && messages.length === 0 && isMountedRef.current) {
                    onReceiveMessage('⚠️ Backend server is not running. Please start it with: python backend/run.py');
                }
            }
        };
        
        checkHealth();
        // Check less frequently (every 15 seconds) to reduce server load
        const interval = setInterval(checkHealth, 15000);
        return () => {
            clearInterval(interval);
        };
    }, [mode, messages.length, onReceiveMessage]);

    // Handle tab visibility changes (pause/resume recording)
    useEffect(() => {
        const handleVisibilityChange = () => {
            if (!isMountedRef.current) return;
            
            if (document.hidden) {
                // Tab is hidden - check if we should pause
                if (isMicActive && audioService.isRecording()) {
                    console.log('Tab hidden - recording may pause depending on browser behavior');
                }
        } else {
                // Tab is visible again - verify recording state
                if (isMicActive && !audioService.isRecording()) {
                    console.warn('Tab visible but recording stopped - may need to restart');
                    // Sync state with actual MediaRecorder state
            setIsMicActive(false);
                }
            }
        };

        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => {
            document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
    }, [isMicActive]);

    // Send initial greeting when voice mode starts (only once per conversation)
    const hasGreetedRef = useRef<string | null>(null);
    const greetingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const hasAutoStartedRef = useRef<boolean>(false);
    const isGreetingPlayingRef = useRef<boolean>(false); // Track if greeting is currently playing (prevents VAD from stopping it)
    
    // Reset greeting ref when conversation changes OR when interface first loads
    // ALWAYS reset for new conversations and when interface opens
    useEffect(() => {
        const currentConvId = conversationIdRef.current || conversationId || 'new';
        // Always reset greeting when conversation ID changes (ensures greeting plays for each new conversation)
        // Also reset if we haven't greeted yet and there are no messages (interface just opened)
        // This ensures greeting plays every time you open the interface or start a new conversation
        if (hasGreetedRef.current !== currentConvId || (messages.length === 0 && hasGreetedRef.current === null)) {
            console.log('Resetting greeting ref for new conversation/interface load:', { 
                old: hasGreetedRef.current, 
                new: currentConvId,
                messageCount: messages.length
            });
            hasGreetedRef.current = null; // Reset for new conversation - allows greeting to play again
            hasAutoStartedRef.current = false; // Reset auto-start flag
            if (greetingTimeoutRef.current) {
                clearTimeout(greetingTimeoutRef.current);
                greetingTimeoutRef.current = null;
            }
        }
    }, [conversationId, messages.length]);
    
    // Reset auto-start flag when mode changes or when user manually stops recording
    useEffect(() => {
        if (mode !== InteractionMode.VOICE) {
            hasAutoStartedRef.current = false;
        }
    }, [mode]);

    // Reset auto-start flag when mic is manually stopped (so it can auto-start again on next voice mode entry)
    useEffect(() => {
        if (mode === InteractionMode.VOICE && !isMicActive && !isProcessing) {
            // Reset after a delay to allow for re-starting
            const resetTimeout = setTimeout(() => {
                if (!isMicActive && !isProcessing && isMountedRef.current) {
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
        
        // Check if we should send greeting: voice mode, no messages, and haven't greeted for this conversation
        // IMPORTANT: Always play greeting for new conversations (reset hasGreetedRef when conversation changes)
        const currentConvId = conversationIdRef.current || conversationId || 'new';
        // Allow greeting even if backend isn't connected yet (will use cached greeting)
        // Reset greeting ref if conversation changed (ensures greeting plays for each new conversation)
        if (hasGreetedRef.current && hasGreetedRef.current !== currentConvId) {
            console.log('New conversation detected in greeting check, resetting greeting:', { old: hasGreetedRef.current, new: currentConvId });
            hasGreetedRef.current = null;
        }
        const shouldGreet = mode === InteractionMode.VOICE && 
                           messages.length === 0 && 
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
                    
                    // Check for cached greeting first
                    const cachedGreeting = greetingService.getCachedGreeting();
                    const isCachedForUser = cachedGreeting && greetingService.isCachedForUser(userName);
                    
                    // Play cached greeting immediately if available
                    if (cachedGreeting && isCachedForUser && cachedGreeting.audioBase64) {
                        console.log('GreetingService: Playing cached greeting immediately');
                        
                        // Add text to chat immediately
                        if (cachedGreeting.text) {
                            onReceiveMessage(cachedGreeting.text);
                        }
                        
                        // Play audio immediately - ensure it plays completely
                        try {
                            // Stop any current audio first
                            audioService.stopAudio();
                            
                            // Small delay to ensure audio service is ready
                            await new Promise(resolve => setTimeout(resolve, 100));
                            
                            const audioBytes = Uint8Array.from(atob(cachedGreeting.audioBase64), c => c.charCodeAt(0));
                            // Try WAV first, fallback to MP3 if needed
                            let audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                            console.log('GreetingService: Playing cached greeting audio (size:', audioBlob.size, 'bytes)');
                            
                            // IMPORTANT: Wait for greeting audio to play completely before continuing
                            // This ensures the greeting is heard fully before microphone auto-starts
                            try {
                                // Play audio and wait for it to complete
                                console.log('GreetingService: Starting audio playback, waiting for completion...');
                                isGreetingPlayingRef.current = true; // Mark greeting as playing (prevents VAD from stopping it)
                                await audioService.playAudio(audioBlob);
                                console.log('GreetingService: Cached greeting audio finished playing completely');
                                isGreetingPlayingRef.current = false; // Mark greeting as finished
                                isGreetingPlayingRef.current = false; // Mark greeting as finished
                            } catch (error) {
                                // If WAV fails, try MP3 format
                                if (error instanceof Error && !error.name.includes('AbortError')) {
                                    console.warn('GreetingService: WAV format failed, trying MP3:', error);
                                    audioBlob = new Blob([audioBytes], { type: 'audio/mpeg' });
                                    try {
                                        await audioService.playAudio(audioBlob);
                                        console.log('GreetingService: Cached greeting audio (MP3) finished playing completely');
                                    } catch (mp3Error) {
                                        console.error('GreetingService: Error playing cached audio (both formats failed):', mp3Error);
                                    }
                                } else if (error instanceof Error && error.name === 'AbortError') {
                                    console.log('GreetingService: Audio playback interrupted (user may have started speaking)');
                                    isGreetingPlayingRef.current = false; // Reset flag on interruption
                                } else {
                                    console.error('GreetingService: Error playing cached audio:', error);
                                    isGreetingPlayingRef.current = false; // Reset flag on error
                                }
                            }
                        } catch (error) {
                            console.error('GreetingService: Error preparing cached audio:', error);
                        }
                    }
                    
                    // Generate fresh greeting in background (for personalization and future cache)
                    const greetingPrompt = "Start the conversation with a friendly greeting.";
                    
                    try {
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
                        
                        // If we didn't have cached greeting, use the fresh one
                        if (!cachedGreeting || !isCachedForUser) {
                            // Only add the assistant's response to chat (not the user prompt)
                            if (response.text_response) {
                                console.log('Adding greeting response to chat:', response.text_response);
                                onReceiveMessage(response.text_response);
                            }
                            
                            // Play audio greeting - ensure it plays completely
                            if (response.audio_base64) {
                                try {
                                    // Small delay to ensure audio service is ready
                                    await new Promise(resolve => setTimeout(resolve, 100));
                                    
                                    const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                                    // Try WAV first, fallback to MP3 if needed
                                    let audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                                    console.log('Playing fresh greeting audio (size:', audioBlob.size, 'bytes)');
                                    
                                    // Stop any current audio first
                                    audioService.stopAudio();
                                    
                                    // IMPORTANT: Wait for greeting audio to play completely
                                    // This ensures the greeting is heard fully before microphone auto-starts
                                    try {
                                        // Play audio and wait for it to complete
                                        isGreetingPlayingRef.current = true; // Mark greeting as playing (prevents VAD from stopping it)
                                        await audioService.playAudio(audioBlob);
                                        console.log('Fresh greeting audio finished playing completely');
                                        isGreetingPlayingRef.current = false; // Mark greeting as finished
                                    } catch (err) {
                                        // If WAV fails, try MP3 format
                                        if (err instanceof Error && !err.name.includes('AbortError')) {
                                            console.warn('GreetingService: WAV format failed, trying MP3:', err);
                                            const mp3Blob = new Blob([audioBytes], { type: 'audio/mpeg' });
                                            try {
                                                await audioService.playAudio(mp3Blob);
                                                console.log('Fresh greeting audio (MP3) finished playing completely');
                                            } catch (mp3Err) {
                                                console.error('Error playing greeting audio (both formats failed):', mp3Err);
                                            }
                                        } else if (err instanceof Error && err.name === 'AbortError') {
                                            console.log('Greeting audio playback interrupted (user may have started speaking)');
                                            isGreetingPlayingRef.current = false; // Reset flag on interruption
                                        } else {
                                            console.error('Error playing greeting audio:', err);
                                            isGreetingPlayingRef.current = false; // Reset flag on error
                                        }
                                    }
                                } catch (error) {
                                    console.error('Error preparing greeting audio:', error);
                                }
                            } else {
                                console.warn('Greeting response has no audio_base64 - TTS may have failed');
                                console.warn('Check backend logs for TTS errors. Available providers:', response);
                            }
                        }
                        
                        // Cache the fresh greeting for next time
                        if (response.text_response && response.audio_base64) {
                            greetingService.cacheGreeting(response.text_response, response.audio_base64, userName);
                            console.log('GreetingService: Cached fresh greeting for future use');
                        }
                    } catch (error) {
                        console.error('Error generating fresh greeting:', error);
                        // If we played cached greeting, that's fine - continue
                        if (!cachedGreeting || !isCachedForUser) {
                            // Reset on error to allow retry only if we didn't have cached greeting
                            hasGreetedRef.current = null;
                        }
                    }
                    
                    // Mark greeting as done - auto-start will happen via the useEffect hook
                    // This ensures consistent auto-start behavior
                } catch (error) {
                    console.error('Error sending initial greeting:', error);
                    // Reset on error to allow retry
                    hasGreetedRef.current = null;
                }
            };
            
            // Immediate execution - no delay
            sendInitialGreeting();
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

    // Auto-start microphone when voice mode is activated (only once, no re-triggering)
    useEffect(() => {
        if (!isMountedRef.current) return;
        if (hasAutoStartedRef.current) return; // Already auto-started, don't do it again
        if (isMicActive) return; // Already active, skip
        
        // Set connection state to CONNECTED when voice mode starts (enables auto-start)
        if (mode === InteractionMode.VOICE && connectionState === LiveConnectionState.DISCONNECTED) {
            setConnectionState(LiveConnectionState.CONNECTED);
        }
        
        // Auto-start if:
        // 1. Voice mode is active
        // 2. Not currently processing
        // 3. AI is not speaking (or wait for it to finish)
        const shouldAutoStart = mode === InteractionMode.VOICE && 
            !isProcessing &&
            !isProcessing &&
            !audioService.isRecording();
        
        if (shouldAutoStart) {
            // For new conversations, wait for greeting to play; for existing, start faster
            // Reduced delay to start mic sooner
            const delay = messages.length === 0 && hasGreetedRef.current === null ? 2000 : 100;
            
            const autoStartTimeout = setTimeout(async () => {
                if (!isMountedRef.current) return;
                if (hasAutoStartedRef.current) return; // Double-check
                if (isMicActive) return; // Already active
                if (audioService.isRecording()) return; // Already recording (prevent duplicate starts)
                
                try {
                    // Final check before starting - wait for greeting audio to finish completely
                    // IMPORTANT: Wait longer to ensure greeting plays completely (up to 15 seconds)
                    // This prevents microphone from interrupting the greeting
                    let waitCount = 0;
                    const maxWait = 30; // Wait up to 15 seconds (30 * 500ms) to allow greeting to play completely
                    
                    console.log('Auto-start: Waiting for greeting audio to finish before starting mic...');
                    while (audioService.isPlaying() && waitCount < maxWait && isMountedRef.current) {
                        await new Promise(resolve => setTimeout(resolve, 500));
                        waitCount++;
                        if (waitCount % 4 === 0) { // Log every 2 seconds
                            console.log(`Auto-start: Still waiting for audio to finish (${waitCount * 0.5}s)...`);
                        }
                    }
                    
                    if (audioService.isPlaying()) {
                        console.log('Auto-start: Greeting audio still playing after max wait (15s), starting mic anyway');
                    } else {
                        console.log('Auto-start: Greeting audio finished, ready to start mic');
                    }
                    
                    // Final check before starting - start mic immediately when voice mode is active
                    if (mode === InteractionMode.VOICE && 
                        !isMicActive && 
                        !isProcessing &&
                        !audioService.isRecording() &&
                        isMountedRef.current) {
                        console.log('Auto-starting microphone in voice mode...');
                        setIsMicActive(true);
                        setConnectionState(LiveConnectionState.CONNECTED); // Ensure connected state
                        try {
                            await audioService.startRecording();
                            if (isMountedRef.current && audioService.isRecording()) {
                                hasAutoStartedRef.current = true;
                                setConnectionState(LiveConnectionState.CONNECTED);
                                console.log('Microphone auto-started successfully');
                                
                                // CRITICAL: Verify VAD is also started
                                if (!audioService.getVADActive()) {
                                    console.warn('Auto-start: VAD not active after recording started, this may prevent speech detection');
                                } else {
                                    console.log('Auto-start: VAD confirmed active, ready for speech detection');
                                }
                            } else {
                                console.error('Auto-start: Recording started but isRecording() returned false');
                                setIsMicActive(false);
                            }
                        } catch (recordingError) {
                            console.error('Auto-start: Error starting recording:', recordingError);
                            setIsMicActive(false);
                        }
                    } else {
                        console.log('Auto-start: Conditions not met:', {
                            mode: mode === InteractionMode.VOICE,
                            isMicActive,
                            isProcessing,
                            isRecording: audioService.isRecording(),
                            isMounted: isMountedRef.current
                        });
                    }
                } catch (error) {
                    console.error('Error auto-starting microphone:', error);
                    if (isMountedRef.current) {
                        setIsMicActive(false);
                    }
                }
            }, delay);
            
            return () => clearTimeout(autoStartTimeout);
        }
    }, [mode, connectionState, isMicActive, isProcessing]); // Include dependencies to trigger when needed

    // Process streaming chunk - defined before useEffect to avoid dependency issues
    const processStreamChunk = useCallback(async (chunkBlob: Blob, isFinal: boolean, userNameParam?: string): Promise<any> => {
        if (!isMountedRef.current) {
            return null;
        }

        // Don't process if already processing (prevents concurrent requests and timeouts)
        // Only allow final chunks to go through (they have priority)
        if (isProcessing && !isFinal) {
            console.log('Streaming: Already processing, skipping chunk to prevent concurrent requests');
            // UX MESSAGES: Show busy message
            onReceiveMessage('⚠️ I\'m a bit busy — give me 2 seconds and I\'ll get it.');
            return null;
        }

        // Set processing flag to prevent concurrent requests
        if (!isFinal) {
            setIsProcessing(true);
            // UX MESSAGES: Show processing message
            onReceiveMessage('🔄 Listening... processing your message.');
        }

        try {
            console.log(`Streaming: Sending chunk (size: ${chunkBlob.size} bytes, final: ${isFinal})`);
            
            // Create session if needed
            if (!streamingSessionIdRef.current || streamingSessionIdRef.current === 'pending') {
                streamingSessionIdRef.current = 'pending';
            }

            // Send chunk to backend (queue will handle sequential processing)
            const result = await apiService.processStreamChunk(
                chunkBlob,
                streamingSessionIdRef.current === 'pending' ? '' : streamingSessionIdRef.current,
                userIdRef.current,
                conversationIdRef.current || undefined,
                'en-US',
                isFinal,
                userName // Send user name for personalization
            );

            logWithTimestamp('Streaming: Chunk response:', {
                hasSessionId: !!result.session_id,
                chunkText: result.chunk_text,
                isNoise: result.is_noise,
                shouldProcess: result.should_process,
                mergedText: result.merged_text
            });

            // Update session ID
            if (result.session_id) {
                streamingSessionIdRef.current = result.session_id;
            }

            // Update conversation ID (important for syncing with backend storage)
            if (result.conversation_id) {
                conversationIdRef.current = result.conversation_id;
                console.log('Streaming: Updated conversation ID:', result.conversation_id);
            }
            
            // Return result so caller can use it
            const returnValue = result;

            // If chunk has text, update live transcription
            if (result.chunk_text && result.chunk_text.trim()) {
                logWithTimestamp(`Streaming: Chunk transcribed: "${result.chunk_text}"`);
                
                // Reset STT error count on successful transcription
                sttErrorCountRef.current = 0;
                lastSttErrorTimeRef.current = 0;
                
                // Update live transcription immediately
                if (isMountedRef.current) {
                    setLiveTranscription(prev => {
                        // Merge with previous transcription, avoiding duplicates
                        const newText = result.chunk_text.trim();
                        if (prev && prev.includes(newText)) {
                            return prev; // Already shown
                        }
                        // Append new text
                        return prev ? `${prev} ${newText}` : newText;
                    });
                }
            } else if (result.is_noise && !result.chunk_text) {
                // Show "Listening..." when we're getting noise responses (STT is working but no speech detected)
                if (isMountedRef.current && isMicActive) {
                    setLiveTranscription(prev => {
                        // Only show "Listening..." if we don't have any transcription yet
                        if (!prev || prev.trim() === '' || prev === 'Listening...') {
                            return 'Listening...';
                        }
                        return prev; // Keep existing transcription
                    });
                }
                // Log when transcription fails completely (not just noise)
                // UX MESSAGES: Show user-friendly error as notification (only once per failure to prevent spam)
                const errorMsg = result.error_message || "I couldn't quite hear that — would you like to repeat?";
                console.warn('Streaming: Transcription failed - no text returned. Audio may be too short, corrupted, or STT service unavailable.');
                // Only show error if we haven't shown one recently (prevent spam)
                const now = Date.now();
                if (isMountedRef.current && isMicActive && (now - lastSttErrorTimeRef.current) > 3000) {
                    lastSttErrorTimeRef.current = now;
                    // Show as notification instead of main message
                    setNotification({ message: `⚠️ ${errorMsg}`, id: Date.now() });
                }
            }

            // If noise detected or should process, trigger LLM
            if (result.should_process && result.merged_text && result.merged_text.trim()) {
                logWithTimestamp(`Streaming: Processing merged text: "${result.merged_text}"`);
                
                // Process with LLM (only if not already processing)
                if (!isProcessing) {
                    setIsProcessing(true);

                    // CRITICAL: Declare llmResponse outside try block so it's accessible in finally
                    let llmResponse: any = null;

                    try {
                        // Clear live transcription before adding final message
                        if (isMountedRef.current) {
                            setLiveTranscription('');
                        }
                        
                        // Add user message to chat (ensures it's stored in conversation history)
                        // This will be saved to backend conversation via /api/voice/stream/process
                        onSendMessage(result.merged_text.trim());
                        
                        // Clear chunks only after successful message addition
                        // This marks chunks as sent but allows new chunks to continue accumulating
                        const chunksBeforeClear = audioService.getAllChunks().length;
                        audioService.clearSpeechChunks();
                        const chunksAfterClear = audioService.getAllChunks().length;
                        
                        // Reset last chunk time to allow new chunks to accumulate immediately
                        lastChunkTimeRef.current = Date.now();
                        
                        // Log for debugging - ensure streaming continues
                        console.log(`Streaming: [CLEANUP] Cleared processed chunks (${chunksBeforeClear} → ${chunksAfterClear}), ready for new audio. Session:`, streamingSessionIdRef.current);

                        // Get LLM response
                        llmResponse = await apiService.processStreamedText(
                            result.session_id,
                            result.merged_text.trim(),
                            userName
                        );

                        if (!isMountedRef.current) return;

                        // Update conversation ID
                        if (llmResponse.conversation_id) {
                            conversationIdRef.current = llmResponse.conversation_id;
                        }

                        // Add assistant message
                        if (llmResponse.text_response) {
                            onReceiveMessage(llmResponse.text_response.trim());
                        }

                        // CRITICAL: Clear accumulated chunks on backend after TTS response is ready
                        // This prevents old chunks from accumulating and causing large file issues
                        // Discard unnecessary chunks after response is ready (as user suggested)
                        try {
                            // Clear backend session chunks after response is ready
                            // This ensures fresh start for next interaction
                            if (streamingSessionIdRef.current) {
                                // Clear chunks by sending empty chunk or calling clear endpoint
                                // For now, we'll let the backend clear on next chunk, but we can also clear frontend chunks
                                const chunksBeforeClear = audioService.getAllChunks().length;
                                audioService.clearSpeechChunks(); // Clear frontend chunks
                                const chunksAfterClear = audioService.getAllChunks().length;
                                console.log(`Streaming: [CLEANUP] TTS response ready, cleared old accumulated chunks (${chunksBeforeClear} → ${chunksAfterClear})`);
                            }
                        } catch (clearError) {
                            console.warn('Streaming: Error clearing chunks after response:', clearError);
                        }
                        
                        // Play audio (always play if available, recording should continue during playback)
                        // IMPORTANT: Recording continues while TTS plays - user can interrupt by speaking
                        if (llmResponse.audio_base64) {
                            try {
                                logWithTimestamp('Streaming: Playing TTS audio response (recording continues)');
                                
                                // CRITICAL: Verify recording is still active before playing audio
                                if (!audioService.isRecording() && isMicActive) {
                                    console.warn('Streaming: Recording stopped unexpectedly before TTS, restarting...');
                                    try {
                                        await audioService.startRecording();
                                        console.log('Streaming: Recording restarted successfully before TTS');
                                    } catch (restartError) {
                                        console.error('Streaming: Failed to restart recording before TTS:', restartError);
                                    }
                                }
                                
                                const audioBytes = Uint8Array.from(atob(llmResponse.audio_base64), c => c.charCodeAt(0));
                                const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                                // Play audio without blocking - recording continues in background
                                // VAD will stop audio if user speaks (handled in VAD callback)
                                audioService.playAudio(audioBlob).then(() => {
                                    logWithTimestamp('Streaming: TTS audio played successfully');
                                    
                                    // CRITICAL: Ensure isProcessing is false so new speech can be processed
                                    if (isMountedRef.current) {
                                        setIsProcessing(false);
                                        console.log('Streaming: Reset isProcessing after TTS playback');
                                    }
                                    
                                    // CRITICAL: Clear any accumulated chunks after TTS finishes
                                    // This ensures we start fresh for the next interaction
                                    const chunksBeforeClear = audioService.getAllChunks().length;
                                    audioService.clearSpeechChunks();
                                    const chunksAfterClear = audioService.getAllChunks().length;
                                    console.log(`Streaming: [CLEANUP] Cleared accumulated chunks after TTS playback (${chunksBeforeClear} → ${chunksAfterClear})`);
                                    
                                    // CRITICAL: Reset VAD state after TTS to allow new speech detection
                                    // This ensures VAD can detect new speech immediately after TTS
                                    audioService.resetVADState();
                                    
                                    // CRITICAL: Reset last chunk time to allow immediate new speech detection
                                    lastChunkTimeRef.current = Date.now();
                                    
                                    // CRITICAL: Add small delay before allowing VAD to detect speech
                                    // This prevents TTS audio from being detected as user speech (feedback loop)
                                    // Reduced from 500ms to 200ms for faster response
                                    setTimeout(() => {
                                        // VAD is now ready to detect new speech
                                        console.log('Streaming: VAD ready for new speech detection after TTS');
                                        
                                        // CRITICAL: Ensure isProcessing is false (double-check)
                                        if (isMountedRef.current) {
                                            setIsProcessing(false);
                                        }
                                        
                                        // CRITICAL: Ensure VAD can detect speech even if resetVADState() was called
                                        // Force a fresh start by ensuring isCurrentlySpeaking can be set to true
                                        // This handles the case where VAD might miss speech start after TTS
                                        const currentChunks = audioService.getAllChunks();
                                        if (currentChunks.length > 0) {
                                            console.log(`Streaming: Found ${currentChunks.length} chunks after TTS - VAD should detect speech if user is speaking`);
                                        }
                                        
                                        // CRITICAL: Verify recording is still active
                                        if (!audioService.isRecording() && isMicActive && isMountedRef.current) {
                                            console.warn('Streaming: Recording stopped after TTS, restarting...');
                                            audioService.startRecording().then(() => {
                                                console.log('Streaming: Recording restarted after TTS');
                                            }).catch((restartError) => {
                                                console.error('Streaming: Failed to restart recording after TTS:', restartError);
                                            });
                                        } else if (audioService.isRecording()) {
                                            console.log('Streaming: Recording confirmed active after TTS');
                                        }
                                    }, 200); // 200ms delay (reduced from 500ms) to ensure TTS audio has fully stopped
                                }).catch((error) => {
                                    // Don't log AbortError - it's expected if user interrupts
                                    if (error.name !== 'AbortError') {
                                        console.error('Streaming: Error playing audio:', error);
                                    }
                                    // CRITICAL: Ensure isProcessing is reset even on error
                                    if (isMountedRef.current) {
                                        setIsProcessing(false);
                                    }
                                });
                            } catch (error) {
                                console.error('Streaming: Error preparing audio:', error);
                            }
                        } else {
                            warnWithTimestamp('Streaming: No audio_base64 in LLM response - TTS may have failed (rate limit or provider error)');
                            // Show notification that audio is not available
                            setNotification({ 
                                message: "⚠️ Response generated but audio unavailable (TTS rate-limited). Text response shown.", 
                                id: Date.now() 
                            });
                            // Even without audio, clear chunks after response is ready
                            audioService.clearSpeechChunks();
                            // CRITICAL: Reset isProcessing when no audio (since audio callback won't fire)
                            setIsProcessing(false);
                            console.log('Streaming: Reset isProcessing (no audio to play), ready for new speech');
                        }
                    } catch (error) {
                        console.error('Streaming: Error processing LLM response:', error);
                        if (isMountedRef.current) {
                            onReceiveMessage(`I'm sorry, I'm having trouble processing your voice. ${error instanceof Error ? error.message : 'Please try again.'}`);
                        }
                    } finally {
                        // CRITICAL: Only reset isProcessing if there's no audio to play
                        // If audio is playing, isProcessing will be reset in the audio callback
                        // This prevents race conditions where new speech arrives before TTS finishes
                        // Check if llmResponse exists and has audio_base64
                        if (!llmResponse || !llmResponse.audio_base64) {
                            // No audio to play, reset immediately
                            setIsProcessing(false);
                            console.log('Streaming: Processing complete (no audio), ready for new speech');
                        } else {
                            // Audio will play, isProcessing will be reset in audio callback
                            console.log('Streaming: Processing complete, TTS audio will play, isProcessing will reset after playback');
                        }
                        
                        // CRITICAL: Reset max recording duration timer after successful processing
                        // This prevents the 60-second limit from stopping recording prematurely
                        if (maxRecordingDurationRef.current) {
                            clearTimeout(maxRecordingDurationRef.current);
                            maxRecordingDurationRef.current = null;
                        }
                        if (warningTimeoutRef.current) {
                            clearTimeout(warningTimeoutRef.current);
                            warningTimeoutRef.current = null;
                        }
                        console.log('Streaming: Reset max recording duration timer after successful processing');
                    }
                }
            }
            
            // Return result for caller
            return returnValue;
        } catch (error) {
            // Reset processing flag on error
            if (!isFinal) {
                setIsProcessing(false);
            }
            // Don't log AbortError as it's expected when component unmounts
            if (error instanceof Error && error.name !== 'AbortError') {
                console.error('Streaming: Error processing chunk:', error);
                
                // Track STT errors (timeouts, failures)
                const isSttError = error.message.includes('timeout') || 
                                  error.message.includes('STT') || 
                                  error.message.includes('transcribe');
                
                if (isSttError) {
                    const now = Date.now();
                    const timeSinceLastError = lastSttErrorTimeRef.current > 0 ? now - lastSttErrorTimeRef.current : Infinity;
                    sttErrorCountRef.current += 1;
                    lastSttErrorTimeRef.current = now;
                    
                    // If we have multiple consecutive STT errors, trigger helpful response
                    // Wait at least 5 seconds between error responses to avoid spam
                    const shouldRespond = sttErrorCountRef.current >= 2 && 
                                        (timeSinceLastError > 5000 || sttErrorCountRef.current === 2);
                    
                    if (shouldRespond && isMountedRef.current && !isProcessing && isMicActive) {
                        console.log('Streaming: Multiple STT errors detected, sending helpful response');
                        
                        // Reset error count after responding (but keep track for next time)
                        sttErrorCountRef.current = 0; // Reset to allow new error tracking
                        lastSttErrorTimeRef.current = Date.now(); // Update timestamp
                        
                        // Trigger helpful TTS response
                        try {
                            setIsProcessing(true);
                            setIsProcessing(true);
                            
                            // Send a text message to LLM to get helpful TTS response
                            const helpfulResponse = await apiService.processText(
                                "The user's voice couldn't be heard clearly. Respond naturally and friendly, asking them to repeat what they said. Keep it brief and conversational, like 'Sorry, I couldn't hear you clearly. Could you repeat that?'",
                                userIdRef.current,
                                conversationIdRef.current || undefined,
                                true, // Generate audio
                                userName
                            );
                            
                            if (isMountedRef.current && helpfulResponse.text_response) {
                                onReceiveMessage(helpfulResponse.text_response);
                                
                                // Play TTS audio - ensure it plays
                                if (helpfulResponse.audio_base64) {
                                    try {
                                        // Stop any current audio first
                                        audioService.stopAudio();
                                        
                                        const audioBytes = Uint8Array.from(atob(helpfulResponse.audio_base64), c => c.charCodeAt(0));
                                        const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                                        console.log('Playing "request to repeat" audio (size:', audioBlob.size, 'bytes)');
                                        
                                        // Play audio without await to allow it to play in background
                                        audioService.playAudio(audioBlob).then(() => {
                                            console.log('"Request to repeat" audio finished playing');
                                        }).catch((err) => {
                                            console.error('Error playing helpful response audio:', err);
                                        });
                                    } catch (err) {
                                        console.error('Error preparing helpful response audio:', err);
                                    }
                                } else {
                                    console.warn('Helpful response has no audio_base64 - TTS may have failed');
                                    console.warn('Check backend logs for TTS errors. Response:', helpfulResponse);
                                }
                            }
                        } catch (err) {
                            console.error('Error sending helpful STT error response:', err);
                            // Fallback: show text message if TTS fails
                            if (isMountedRef.current) {
                                onReceiveMessage("Sorry, I couldn't hear you clearly. Could you repeat that?");
                            }
                        } finally {
                            setIsProcessing(false);
                            if (isMountedRef.current) {
                                setIsProcessing(false);
                            }
                        }
                    }
                }
            }
        }
    }, [isMicActive, onSendMessage, onReceiveMessage, userName]);

    // Turn-based STT: Only initialize session, no continuous chunk sending
    // Audio is buffered until VAD detects speech end, then ONE STT request is sent
    useEffect(() => {
        if (mode !== InteractionMode.VOICE || !isMicActive) {
            streamingSessionIdRef.current = null;
            return;
        }

        // Initialize streaming session when mic becomes active
        const initSession = async () => {
            if (!streamingSessionIdRef.current) {
                try {
                    const sessionId = await apiService.createStreamingSession(
                        userIdRef.current,
                        conversationIdRef.current || undefined,
                        'en-US',
                        userName // Send user name for personalization
                    );
                    streamingSessionIdRef.current = sessionId;
                    console.log('Turn-based STT: Session initialized, waiting for speech end (VAD-based)');
                } catch (error) {
                    console.error('Turn-based STT: Failed to create session:', error);
                }
            }
        };

        // Wait for recording to start, then initialize session
        const checkRecording = setInterval(() => {
            if (!audioService.isRecording()) {
                return; // Wait for recording to start
            }

            clearInterval(checkRecording);
            initSession();
        }, 100);

        return () => {
            clearInterval(checkRecording);
        };
    }, [mode, isMicActive]);


    // VAD callback - updates audio level visualization and triggers processing on silence
    useEffect(() => {
        if (mode !== InteractionMode.VOICE) {
            audioService.setVADCallback(null);
            return;
        }

        const vadHandler = async (isSpeaking: boolean | null, audioLevel: number) => {
            // DEBUG: Log all VAD callbacks to track why speech end isn't processing
            if (isSpeaking === null) {
                console.log('[VAD DEBUG] Speech ended callback received, isMounted:', isMountedRef.current, 'mode:', mode, 'isMicActive:', isMicActive, 'isProcessing:', isProcessing);
            }
            if (!isMountedRef.current) {
                console.log('[VAD DEBUG] Component not mounted, skipping callback');
                return;
            }
            
            // Update audio level for visualization (smooth updates)
            setAudioLevel(prev => {
                // Smooth transition for better UX (normalize to 0-1)
                const normalizedLevel = audioLevel / 100;
                return Math.round((prev * 0.7 + normalizedLevel * 0.3) * 100) / 100;
            });
            
            // Stop TTS audio immediately when user starts speaking
            // CRITICAL: Don't stop greeting audio - VAD might detect it as speech (feedback loop)
            if (isSpeaking === true && audioService.isPlaying() && !isGreetingPlayingRef.current) {
                console.log('VAD: User speaking detected, stopping AI audio playback (not greeting)');
                audioService.stopAudio();
            } else if (isSpeaking === true && audioService.isPlaying() && isGreetingPlayingRef.current) {
                console.log('VAD: Speech detected during greeting playback - ignoring (likely feedback loop, greeting audio being detected as speech)');
            }
            
            // null = special signal that speech has ended (trigger processing)
            // Turn-based STT: Send ONE STT request per complete utterance
            if (isSpeaking === null) {
                logWithTimestamp('VAD: Speech ended - preparing single STT request');
                
                // Prevent concurrent processing (using isProcessing as single source of truth)
                if (isProcessing) {
                    console.log('VAD: Already processing, skipping (isProcessing=true)');
                    return;
                }
                if (!isMicActive) {
                    console.log('VAD: Mic inactive, skipping (isMicActive=false)');
                    return;
                }

                // STT cooldown: prevent request storms (200ms minimum between requests)
                // Reduced from 500ms to 200ms for faster response
                const now = Date.now();
                const lastSttTime = lastChunkTimeRef.current || 0;
                const STT_COOLDOWN_MS = 200; // 200ms cooldown (reduced for faster response)
                if (now - lastSttTime < STT_COOLDOWN_MS) {
                    console.log(`VAD: STT cooldown active (${now - lastSttTime}ms < ${STT_COOLDOWN_MS}ms), skipping`);
                    return;
                }

                setIsProcessing(true);
                
                try {
                    // Get all accumulated chunks for this utterance
                    const allChunks = audioService.getAllChunksWithHeader();
                    console.log(`VAD: Found ${allChunks.length} chunks for utterance`);
                    
                    if (allChunks.length === 0) {
                        console.log('VAD: No chunks to process (likely noise/silence)');
                        setIsProcessing(false);
                        return;
                    }

                    // CRITICAL: Check if speech was actually detected before creating blob
                    // If VAD never detected speech, these chunks are likely noise
                    if (!audioService.hasDetectedSpeech()) {
                        console.log('VAD: No speech detected in chunks, clearing noise');
                        audioService.clearSpeechChunks();
                        setIsProcessing(false);
                        return;
                    }
                    
                    // CRITICAL: Concatenate chunks to create WebM blob
                    // While MediaRecorder chunks are fragments, concatenation sometimes works
                    // This is more reliable than requestData() which also returns fragments
                    const blobType = allChunks[0]?.type || 'audio/webm';
                    const speechBlob = new Blob(allChunks, { type: blobType });
                    const totalSize = allChunks.reduce((sum, chunk) => sum + chunk.size, 0);
                    logWithTimestamp(`VAD: Concatenating ${allChunks.length} chunks (${totalSize} bytes) to create WebM blob`);
                    
                    // Minimum utterance length check (300ms minimum to filter noise)
                    // Estimate duration: ~64kbps for WebM/Opus = ~8KB per second
                    const estimatedDurationMs = (speechBlob.size / 8000) * 1000;
                    const MIN_UTTERANCE_DURATION_MS = 200; // 200ms minimum (reduced from 300ms for faster response, still filters noise)
                    const MAX_SEGMENT_DURATION_MS = 30000; // 30 seconds max (increased from 10s for better user experience in demo)
                    const BOUNDARY_OVERLAP_MS = 300; // 200-500ms overlap for long utterances
                    
                    if (estimatedDurationMs < MIN_UTTERANCE_DURATION_MS) {
                        console.log(`VAD: Utterance too short (${estimatedDurationMs.toFixed(0)}ms < ${MIN_UTTERANCE_DURATION_MS}ms), ignoring`);
                        audioService.clearSpeechChunks(); // Clear short utterances
                        setIsProcessing(false);
                        return;
                    }
                    
                    // DEMO MODE: Allow longer utterances (up to 30 seconds)
                    // For very long utterances, show a warning but still process
                    if (estimatedDurationMs > MAX_SEGMENT_DURATION_MS) {
                        console.warn(`VAD: Utterance very long (${estimatedDurationMs.toFixed(0)}ms > ${MAX_SEGMENT_DURATION_MS}ms) - processing anyway, but may take longer`);
                        // Show notification but continue processing
                        setNotification({ message: "⚠️ Long message detected - processing may take a moment.", id: Date.now() });
                        // Continue processing instead of rejecting
                    }
                    
                    console.log(`VAD: Sending single STT request for utterance (${speechBlob.size} bytes, ~${estimatedDurationMs.toFixed(0)}ms)`);
                    
                    // Clear live transcription before processing
                    if (isMountedRef.current) {
                        setLiveTranscription('');
                    }
                    
                    // Send ONE STT request for the complete utterance
                    lastChunkTimeRef.current = now;
                    const sttResult = await processStreamChunk(speechBlob, true, userName); // isFinal = true, include userName
                    
                    // UX MESSAGES: Handle error messages from backend as notification (only once to prevent spam)
                    if (sttResult && sttResult.error_message) {
                        console.log('Streaming: Backend error message:', sttResult.error_message);
                        const now = Date.now();
                        // Only show error if we haven't shown one recently (prevent spam)
                        if ((now - lastSttErrorTimeRef.current) > 3000) {
                            lastSttErrorTimeRef.current = now;
                            // Show as notification instead of main message
                            setNotification({ message: `⚠️ ${sttResult.error_message}`, id: Date.now() });
                        }
                    }
                    
                    // Ensure user message is added to chat if transcription succeeded
                    // This ensures voice messages are stored in conversation history and visible in chat
                    if (sttResult && sttResult.chunk_text && sttResult.chunk_text.trim()) {
                        // Check if message should be processed (will be added via should_process flow)
                        // But if it's not being processed, still add it to chat so it's visible
                        if (!sttResult.should_process) {
                            console.log('VAD: Adding transcribed text to chat (not processed):', sttResult.chunk_text.trim());
                            onSendMessage(sttResult.chunk_text.trim());
                        }
                        // If should_process is true, the message will be added in the should_process handler above
                    }
                    
                    // Clear chunks after successful processing
                    audioService.clearSpeechChunks();
                    console.log('VAD: STT request completed, chunks cleared');
                    
                    // CRITICAL: Reset max recording duration timer after successful STT processing
                    // This ensures the 120-second limit doesn't stop recording prematurely
                    if (maxRecordingDurationRef.current) {
                        clearTimeout(maxRecordingDurationRef.current);
                        maxRecordingDurationRef.current = null;
                    }
                    if (warningTimeoutRef.current) {
                        clearTimeout(warningTimeoutRef.current);
                        warningTimeoutRef.current = null;
                    }
                    console.log('VAD: Reset max recording duration timer after STT processing');
                } catch (error) {
                    if (error instanceof Error && error.name !== 'AbortError') {
                        console.error('VAD: Error processing utterance:', error);
                    }
                } finally {
                    setIsProcessing(false);
                }
                return; // Don't update audio level again for speech-ended signal
            }
            
            // Normal state update (isSpeaking is boolean)
            // Audio level already updated above
        };

        audioService.setVADCallback(vadHandler);

        return () => {
            audioService.setVADCallback(null);
        };
    }, [mode, processStreamChunk]);

    // Audio level is now handled by VAD callback, no need for simulation
    // This effect is kept for fallback if VAD fails
    useEffect(() => {
        if (!isMicActive || !audioService.isRecording()) {
            // Only reset if VAD is not providing levels
            if (audioLevel === 0) {
                return; // VAD will update it
            }
            setAudioLevel(0);
            return;
        }
    }, [isMicActive, audioLevel]);
    
    // Periodic check to ensure recording continues after TTS
    useEffect(() => {
        if (mode !== InteractionMode.VOICE || !isMicActive) {
            return;
        }
        
        // Check every 2 seconds if recording is still active
        const recordingHealthCheck = setInterval(() => {
            if (!isMountedRef.current) {
                clearInterval(recordingHealthCheck);
                return;
            }
            
            // If mic should be active but recording stopped, restart it
            if (isMicActive && !audioService.isRecording() && !isProcessing) {
                console.warn('Recording health check: Recording stopped unexpectedly, restarting...');
                audioService.startRecording().then(() => {
                    console.log('Recording health check: Recording restarted successfully');
                }).catch((error) => {
                    console.error('Recording health check: Failed to restart recording:', error);
                });
            }
        }, 2000); // Check every 2 seconds
        
        return () => {
            clearInterval(recordingHealthCheck);
        };
    }, [mode, isMicActive, isProcessing]);
    
    // Fallback timeout: Force speech end detection if chunks accumulate too much
    // This prevents chunks from accumulating indefinitely if VAD fails to detect speech end
    const vadFallbackTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    useEffect(() => {
        // Clear any existing fallback timeout
        if (vadFallbackTimeoutRef.current) {
            clearTimeout(vadFallbackTimeoutRef.current);
            vadFallbackTimeoutRef.current = null;
        }
        
        if (!isMicActive || !audioService.isRecording() || isProcessing) {
            return;
        }
        
        // Set fallback timeout: If chunks accumulate for 10 seconds without VAD detecting speech end,
        // force speech end detection (prevents infinite accumulation)
        // CRITICAL: Only trigger if speech was actually detected (not just background noise)
        vadFallbackTimeoutRef.current = setTimeout(() => {
            if (!isMountedRef.current || isProcessing || !isMicActive) return;
            
            const allChunks = audioService.getAllChunks();
            if (allChunks.length === 0) return;
            
            // Estimate duration: ~64kbps for WebM/Opus = ~8KB per second
            const estimatedDurationMs = (allChunks.reduce((sum, chunk) => sum + chunk.size, 0) / 8000) * 1000;
            
            // If VAD never detected speech, this is usually noise – but long continuous audio
            // is likely real speech that VAD missed. In that case, force a best‑effort send.
            if (!audioService.hasDetectedSpeech()) {
                if (estimatedDurationMs > 8000) {
                    // Best‑effort fallback: send concatenated blob so the backend can try STT.
                    // This may occasionally fail if the WebM header is invalid, but it ensures
                    // the user’s second turn is at least attempted instead of silently discarded.
                    warnWithTimestamp(`VAD Fallback: No speech detected but substantial audio (${estimatedDurationMs.toFixed(0)}ms) - forcing best-effort STT with concatenated WebM`);
                    const blobType = allChunks[0]?.type || 'audio/webm';
                    const speechBlob = new Blob(allChunks, { type: blobType });
                    processStreamChunk(speechBlob, true, userName).catch(err => {
                        errorWithTimestamp('VAD Fallback: Error processing best-effort chunks:', err);
                    });
                    return;
                }
                if (estimatedDurationMs > 5000) {
                    logWithTimestamp(`VAD Fallback: No speech detected after ${estimatedDurationMs.toFixed(0)}ms - clearing noise chunks`);
                    audioService.clearSpeechChunks();
                }
                // For shorter audio, wait a bit more - VAD might detect speech soon
                return;
            }
            
            // Speech was detected, check if we need to force speech end
            // CRITICAL: Only trigger fallback if we have significant audio (at least 5 seconds)
            // AND speech was detected (checked above)
            if (estimatedDurationMs > 5000) {
                console.warn(`VAD Fallback: Forcing speech end detection after ${estimatedDurationMs.toFixed(0)}ms of accumulated audio (VAD may have missed speech end)`);
                
                // Try to force VAD to detect speech end first
                const vadTriggered = audioService.forceSpeechEnd();
                if (!vadTriggered) {
                    // DEMO FIX: If VAD forceSpeechEnd() failed, don't send concatenated blob
                    // This prevents invalid WebM containers from being sent to STT
                    // The happy path (VAD naturally detects speech end) is the only reliable path
                    // MediaRecorder fragments cannot be safely concatenated without proper remuxing
                    logWithTimestamp(`VAD Fallback: VAD forceSpeechEnd() failed after ${estimatedDurationMs.toFixed(0)}ms - waiting for natural speech end detection (not sending invalid WebM)`);
                    // Don't clear chunks - VAD might still detect speech end naturally
                    // The timeout will fire again in 15s if needed
                }
            }
        }, 15000); // Check every 15 seconds (increased to give VAD more time to detect speech naturally)
        
        return () => {
            if (vadFallbackTimeoutRef.current) {
                clearTimeout(vadFallbackTimeoutRef.current);
                vadFallbackTimeoutRef.current = null;
            }
        };
    }, [isMicActive, isProcessing, messages.length, userName]); // Reset when processing completes or conversation changes
    
    // Auto-stop recording after maximum duration (prevent huge files)
    const maxRecordingDurationRef = useRef<NodeJS.Timeout | null>(null);
    const warningTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    useEffect(() => {
        // Clear any existing timeouts
        if (maxRecordingDurationRef.current) {
            clearTimeout(maxRecordingDurationRef.current);
            maxRecordingDurationRef.current = null;
        }
        if (warningTimeoutRef.current) {
            clearTimeout(warningTimeoutRef.current);
            warningTimeoutRef.current = null;
        }
        
        if (!isMicActive || !audioService.isRecording()) {
            return;
        }
        
        // Warn user at 110 seconds (10 seconds before 120s limit)
        warningTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current && isMicActive && audioService.isRecording()) {
                onReceiveMessage('⚠️ Recording will stop automatically in 10 seconds. Please finish your message.');
            }
        }, 110000); // 110 seconds warning (10s before 120s limit)
        
        // Set timeout to auto-stop after 120 seconds (increased from 60s)
        // This gives more time for conversations, and the timer resets after each successful processing
        maxRecordingDurationRef.current = setTimeout(() => {
            if (!isMountedRef.current) return;
            console.warn('Maximum recording duration reached (120s), auto-stopping...');
            if (isMicActive && !isProcessing && audioService.isRecording()) {
                // Before stopping, try to process any accumulated chunks
                const allChunks = audioService.getAllChunks();
                if (allChunks.length > 0) {
                    console.log('Max duration reached: Processing accumulated chunks before stopping');
                    const speechBlob = new Blob(allChunks, { type: 'audio/webm' });
                    processStreamChunk(speechBlob, true, userName).catch(err => {
                        console.error('Error processing chunks before max duration stop:', err);
                    });
                }
                // Force stop the recording
                audioService.forceStop();
                setIsMicActive(false);
                onReceiveMessage('⚠️ Recording stopped automatically after 120 seconds. Please try a shorter recording.');
            }
        }, 120000); // 120 seconds max (increased from 60s, resets after each successful processing)
        
        return () => {
            if (maxRecordingDurationRef.current) {
                clearTimeout(maxRecordingDurationRef.current);
                maxRecordingDurationRef.current = null;
            }
            if (warningTimeoutRef.current) {
                clearTimeout(warningTimeoutRef.current);
                warningTimeoutRef.current = null;
            }
        };
        }, [isMicActive, isProcessing, messages.length]); // Reset timer when conversation changes or processing completes

    // Separate function to process recording (called automatically when mic stops)
    const handleProcessRecording = useCallback(async (audioBlob: Blob) => {
        if (isProcessing) {
            console.log('Already processing, ignoring');
            return;
        }

        if (!isMountedRef.current) {
            console.log('Component unmounted, aborting processing');
            return;
        }

        try {
            setIsProcessing(true);
            setIsProcessing(true);

            // Add a temporary "transcribing..." message
            onSendMessage('[Transcribing your voice...]');

            // Check audio size
            const minAudioSize = 1000; // 1KB minimum
            if (audioBlob.size < minAudioSize) {
                console.warn(`Audio too short (${audioBlob.size} bytes), ignoring`);
                setIsProcessing(false);
                setIsProcessing(false);
                return;
            }

            const MAX_AUDIO_SIZE = 10 * 1024 * 1024; // 10MB
            if (audioBlob.size > MAX_AUDIO_SIZE) {
                const sizeMB = (audioBlob.size / 1024 / 1024).toFixed(2);
                const errorMsg = `Audio file too large (${sizeMB}MB). Maximum size is 10MB.`;
                onReceiveMessage(`⚠️ ${errorMsg}`);
                setIsProcessing(false);
                setIsProcessing(false);
                return;
            }

            console.log(`Processing audio: ${audioBlob.size} bytes, type: ${audioBlob.type}`);

            // Check backend health
            let isBackendHealthy = false;
            try {
                const healthCheckPromise = apiService.healthCheck();
                const timeoutPromise = new Promise<boolean>((resolve) => 
                    setTimeout(() => resolve(false), 2000)
                );
                isBackendHealthy = await Promise.race([healthCheckPromise, timeoutPromise]) as boolean;
            } catch (error) {
                console.warn('Health check failed:', error);
                isBackendHealthy = false;
            }

            if (!isBackendHealthy) {
                const errorMsg = 'Backend server is not running. Please restart it with: python backend/run.py';
                setConnectionState(LiveConnectionState.DISCONNECTED);
                onReceiveMessage(`⚠️ ${errorMsg}`);
                setIsProcessing(false);
                setIsProcessing(false);
                return;
            }

            // Cancel any previous request
            if (currentRequestAbortControllerRef.current) {
                currentRequestAbortControllerRef.current.abort();
            }
            currentRequestAbortControllerRef.current = new AbortController();

            console.log('Calling processVoice API...');
            let response: VoiceResponse;
            try {
                response = await apiService.processVoice(
                    audioBlob,
                    userIdRef.current,
                    conversationIdRef.current || undefined,
                    'en-US',
                    userName
                );
            } catch (error: any) {
                if (error.message?.includes('Cannot connect') || error.message?.includes('network') || error.message?.includes('fetch')) {
                    setConnectionState(LiveConnectionState.DISCONNECTED);
                }
                throw error;
            }

            if (!isMountedRef.current) {
                console.log('Component unmounted during API call, aborting');
                return;
            }

            if (!response) {
                throw new Error('No response received from backend');
            }

            if (response.conversation_id) {
                conversationIdRef.current = response.conversation_id;
            }

            // Add user message (transcribed text)
            if (response.user_text && response.user_text.trim()) {
                console.log('Adding user message (transcribed text):', response.user_text);
                onSendMessage(response.user_text.trim());
            } else {
                console.error('CRITICAL: No user_text in response');
                onSendMessage('[Transcription failed - your voice was recorded but could not be converted to text]');
            }

            // Add assistant message
            if (response.text_response && response.text_response.trim()) {
                console.log('Adding assistant message:', response.text_response);
                onReceiveMessage(response.text_response.trim());
            } else {
                console.warn('No text_response in response');
                onReceiveMessage('I received your message, but I couldn\'t generate a response. Please try again.');
            }

            // Play audio response (but don't stop mic - it should stay on)
            if (!isMountedRef.current) {
                console.log('Component unmounted, skipping audio playback');
                return;
            }
            
            // Only skip if user manually stopped mic (not if VAD processed)
            // IMPORTANT: Allow audio playback even if recording is active - recording should continue
            if (!audioService.isRecording() && !isMicActive) {
                console.log('Mic is off, skipping audio playback');
                return;
            }

            if (response.audio_base64) {
                console.log('Playing audio from base64 response (recording continues)');
                try {
                    const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                    // Play audio without blocking - recording continues in background
                    // VAD will stop audio if user speaks (handled in VAD callback)
                    audioService.playAudio(audioBlob).then(() => {
                        console.log('Audio playback started');
                    }).catch((error) => {
                        // Don't log AbortError - it's expected if user interrupts
                        if (error.name !== 'AbortError') {
                            console.error('Error playing audio:', error);
                        }
                    });
                } catch (error) {
                    console.error('Error preparing audio:', error);
                }
            } else if (response.audio_url) {
                console.log('Fetching audio from URL:', response.audio_url);
                try {
                    const audioBlob = await apiService.getAudio(response.audio_url);
                    // IMPORTANT: Don't check isRecording() here - allow playback during recording
                    if (!isMountedRef.current) {
                        return;
                    }
                    // Play audio without blocking - recording continues in background
                    audioService.playAudio(audioBlob).then(() => {
                        console.log('Audio playback started from URL');
                    }).catch((error) => {
                        // Don't log AbortError - it's expected if user interrupts
                        if (error.name !== 'AbortError') {
                            console.error('Error playing audio from URL:', error);
                        }
                    });
                } catch (error) {
                    console.error('Error fetching audio from URL:', error);
                }
            }
        } catch (error) {
            if (!isMountedRef.current) {
                return;
            }
            console.error('Error processing voice:', error);
            const errorMessage = error instanceof Error ? error.message : 'Failed to process voice. Please try again.';
            onReceiveMessage(`I'm sorry, I'm having trouble processing your voice. ${errorMessage}`);
        } finally {
            setIsProcessing(false);
            if (isMountedRef.current) {
                setIsProcessing(false);
            }
            currentRequestAbortControllerRef.current = null;
        }
    }, [isProcessing, onSendMessage, onReceiveMessage, userName]);

    const handleMicToggle = useCallback(async () => {
        // Debounce rapid clicks (prevent race conditions) - reduced for faster response
        const now = Date.now();
        if (now - lastClickTimeRef.current < 100) {
            console.log('Click debounced, ignoring');
            return;
        }
        lastClickTimeRef.current = now;

        // Check if component is still mounted
        if (!isMountedRef.current) {
            console.log('Component unmounted, ignoring click');
            return;
        }

        // Use current state value (before update) to determine action
        const wasActive = isMicActive;
        
        // Immediately update UI state for instant feedback
        setIsMicActive(!wasActive);

        if (wasActive) {
            // Stop recording (send final chunk and process)
            // State already updated above for instant feedback
            try {
                // Check if recording is actually active before trying to stop
                if (!audioService.isRecording()) {
                    console.warn('No active recording to stop');
                    return;
                }
                
                // Stop streaming chunks first
                if (streamingChunkIntervalRef.current) {
                    clearInterval(streamingChunkIntervalRef.current);
                    streamingChunkIntervalRef.current = null;
                }
                
                // Send final chunk if we have one
                const speechChunks = audioService.getSpeechChunks();
                if (speechChunks.length > 0 && streamingSessionIdRef.current) {
                    try {
                        const blobType = speechChunks[0]?.type || 'audio/webm';
                        const finalBlob = new Blob(speechChunks, { type: blobType });
                        console.log('Streaming: Sending final chunk before stopping');
                        await processStreamChunk(finalBlob, true, userName); // isFinal = true, include userName
                    } catch (error) {
                        console.error('Streaming: Error sending final chunk:', error);
                    }
                }
                
                // Stop recording immediately (don't wait)
                setIsMicActive(false);
                setLiveTranscription(''); // Clear live transcription
                
                // Reset STT error tracking when mic is turned off
                sttErrorCountRef.current = 0;
                lastSttErrorTimeRef.current = 0;
                
                // Stop recording asynchronously (don't wait for it)
                if (audioService.isRecording()) {
                    // Fire and forget - don't await
                    audioService.stopRecording().catch(error => {
                        console.error('Error stopping recording:', error);
                    });
                }
                
                audioService.clearSpeechChunks();
                
                // Clear streaming session
                streamingSessionIdRef.current = null;
            } catch (error) {
                console.error('Error stopping recording:', error);
                setIsMicActive(false);
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
                
                // CRITICAL: If recording is already active, don't restart it
                // This prevents interrupting an active recording session
                if (audioService.isRecording() || isMicActive) {
                    console.log('Recording already active, skipping start request');
                    return; // Don't restart if already recording
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
                
                // Verify recording actually started and sync state
                if (!audioService.isRecording()) {
                    // Sync state with actual MediaRecorder state
                    setIsMicActive(false);
                    throw new Error('Recording failed to start - MediaRecorder state is not recording');
                }
                
                // Double-check state is synced
                if (isMountedRef.current && audioService.isRecording()) {
                    setConnectionState(LiveConnectionState.CONNECTED);
                    console.log('Recording started successfully');
                } else {
                    // State mismatch - sync it
                    setIsMicActive(audioService.isRecording());
                }
            } catch (error) {
                if (!isMountedRef.current) {
                    console.log('Component unmounted during recording start');
                    return;
                }
                console.error('Error starting recording:', error);
                const errorMessage = error instanceof Error ? error.message : 'Failed to start recording. Please check microphone permissions.';
                // Show error in chat
                onReceiveMessage(`⚠️ I couldn't start recording. ${errorMessage}`);
                setIsMicActive(false);
                setConnectionState(LiveConnectionState.DISCONNECTED);
            }
        }
    }, [isMicActive, handleProcessRecording, onSendMessage, onReceiveMessage, userName]);

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
    }, [isProcessing, onSendMessage, onReceiveMessage, userName]);

    // Auto-dismiss notification after 4 seconds
    useEffect(() => {
        if (notification) {
            const timer = setTimeout(() => {
                setNotification(null);
            }, 4000);
            return () => clearTimeout(timer);
        }
    }, [notification]);

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
                                        {msg.role === 'assistant' ? (
                                            <MarkdownMessage content={msg.content} />
                                        ) : (
                                            <span className="whitespace-pre-wrap">{msg.content}</span>
                                        )}
                                    </div>
                                </div>
                            ))}
                            
                            {/* Live Transcription Display */}
                            {liveTranscription && isMicActive && (
                                <div className="chat chat-end animate-in fade-in duration-200">
                                    <div className="chat-bubble bg-primary/80 text-white shadow-sm">
                                        <span className="whitespace-pre-wrap italic opacity-90">
                                            {liveTranscription}
                                            <span className="inline-block w-2 h-4 ml-1 bg-white/50 animate-pulse" />
                                        </span>
                                    </div>
                                </div>
                            )}
                            
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

                    {/* Notification Toast - Side notification (not main message) */}
                    <AnimatePresence>
                        {notification && (
                            <motion.div
                                initial={{ opacity: 0, x: 100 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 100 }}
                                transition={{ duration: 0.3 }}
                                className="fixed top-20 right-4 z-50 pointer-events-none"
                            >
                                <div className="bg-warning/90 backdrop-blur-md text-warning-content px-4 py-3 rounded-lg shadow-lg border border-warning/30 max-w-sm">
                                    <p className="text-sm font-medium">{notification.message}</p>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

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