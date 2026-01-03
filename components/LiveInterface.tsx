import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ControlPanel } from './ControlPanel';
import { TextChat } from './TextChat';
import { InteractionMode, Message, LiveConnectionState } from '../types';
import { apiService, VoiceResponse } from '../services/apiService';
import { audioService } from '../services/audioService';
import { greetingService } from '../services/greetingService';
import { motion, AnimatePresence } from 'framer-motion';
import { MarkdownMessage } from './MarkdownMessage';

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
    const [liveTranscription, setLiveTranscription] = useState<string>(''); // Live transcription text
    const conversationIdRef = useRef<string | null>(conversationId || null);
    const userIdRef = useRef<string>(userId);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const recordingStartTimeRef = useRef<number | null>(null);
    const isProcessingRef = useRef<boolean>(false); // Ref to prevent race conditions
    const isMountedRef = useRef<boolean>(true); // Track if component is mounted
    const lastClickTimeRef = useRef<number>(0); // For debouncing
    const currentRequestAbortControllerRef = useRef<AbortController | null>(null); // For request cancellation
    const vadProcessingRef = useRef<boolean>(false); // Prevent duplicate VAD processing
    
    // Streaming STT state
    const streamingSessionIdRef = useRef<string | null>(null);
    const streamingChunkIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const streamingChunksRef = useRef<Blob[]>([]); // Accumulated chunks for current speech
    const lastChunkTimeRef = useRef<number>(0);
    const CHUNK_INTERVAL_MS = 3000; // Send chunk every 3 seconds (reduced API calls)
    
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
            // Cleanup audio service
            if (audioService.isRecording()) {
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
        // Check more frequently (every 5 seconds) to catch backend issues faster
        const interval = setInterval(checkHealth, 5000);
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
        
        // Check if we should send greeting: voice mode, no messages, connected, and haven't greeted for this conversation
        const currentConvId = conversationIdRef.current || conversationId || 'new';
        // Allow greeting even if backend isn't connected yet (will use cached greeting)
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
                        
                        // Play audio immediately - don't await to allow it to play in background
                        try {
                            // Stop any current audio first
                            audioService.stopAudio();
                            
                            const audioBytes = Uint8Array.from(atob(cachedGreeting.audioBase64), c => c.charCodeAt(0));
                            const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                            console.log('GreetingService: Playing cached greeting audio (size:', audioBlob.size, 'bytes)');
                            
                            // Play audio without await to allow it to play in background
                            audioService.playAudio(audioBlob).then(() => {
                                console.log('GreetingService: Cached greeting audio finished playing');
                            }).catch((error) => {
                                // Ignore AbortError - it's expected if audio is interrupted
                                if (error instanceof Error && error.name !== 'AbortError') {
                                    console.error('GreetingService: Error playing cached audio:', error);
                                    // If cached audio fails, try to generate fresh one
                                    console.log('GreetingService: Cached audio failed, will use fresh greeting');
                                }
                            });
                        } catch (error) {
                            // Ignore AbortError - it's expected if audio is interrupted
                            if (error instanceof Error && error.name !== 'AbortError') {
                                console.error('GreetingService: Error preparing cached audio:', error);
                            }
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
                            
                            // Play audio greeting - ensure it plays even if cached was already played
                            if (response.audio_base64) {
                                try {
                                    const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                                    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                                    console.log('Playing fresh greeting audio (size:', audioBlob.size, 'bytes)');
                                    
                                    // Stop any current audio first
                                    audioService.stopAudio();
                                    
                                    // Play audio without await to allow it to play in background
                                    audioService.playAudio(audioBlob).then(() => {
                                        console.log('Fresh greeting audio finished playing');
                                    }).catch((error) => {
                                        // Ignore AbortError - it's expected if audio is interrupted
                                        if (error instanceof Error && error.name !== 'AbortError') {
                                            console.error('Error playing greeting audio:', error);
                                        }
                                    });
                                } catch (error) {
                                    // Ignore AbortError - it's expected if audio is interrupted
                                    if (error instanceof Error && error.name !== 'AbortError') {
                                        console.error('Error playing greeting audio:', error);
                                    }
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
        
        // Auto-start if:
        // 1. Voice mode is active
        // 2. Backend is connected
        // 3. Not currently processing
        // 4. AI is not speaking
        const shouldAutoStart = mode === InteractionMode.VOICE && 
            connectionState === LiveConnectionState.CONNECTED && 
            !isProcessing &&
            !isProcessingRef.current &&
            !audioService.isPlaying() &&
            !audioService.isRecording();
        
        if (shouldAutoStart) {
            // For new conversations, wait longer for greeting to play; for existing, start immediately
            // Increased delay to 3 seconds to allow greeting audio to play fully
            const delay = messages.length === 0 && hasGreetedRef.current === null ? 3000 : 300;
            
            const autoStartTimeout = setTimeout(async () => {
                if (!isMountedRef.current) return;
                if (hasAutoStartedRef.current) return; // Double-check
                if (isMicActive) return; // Already active
                
                try {
                    // Final check before starting - wait for audio to finish if it's playing
                    // Give greeting audio time to play (check multiple times)
                    let waitCount = 0;
                    const maxWait = 10; // Wait up to 5 seconds (10 * 500ms)
                    
                    while (audioService.isPlaying() && waitCount < maxWait && isMountedRef.current) {
                        await new Promise(resolve => setTimeout(resolve, 500));
                        waitCount++;
                    }
                    
                    // Final check before starting
                    if (mode === InteractionMode.VOICE && 
                        connectionState === LiveConnectionState.CONNECTED && 
                        !isMicActive && 
                        !isProcessing &&
                        !isProcessingRef.current &&
                        !audioService.isPlaying() &&
                        !audioService.isRecording() &&
                        isMountedRef.current) {
                        console.log('Auto-starting microphone in voice mode...');
                        setIsMicActive(true);
                        await audioService.startRecording();
                        if (isMountedRef.current && audioService.isRecording()) {
                            hasAutoStartedRef.current = true;
                            console.log('Microphone auto-started successfully');
                        } else {
                            setIsMicActive(false);
                        }
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
    }, [mode, connectionState]); // Removed isMicActive and isProcessing from deps to prevent re-triggering

    // Process streaming chunk - defined before useEffect to avoid dependency issues
    const processStreamChunk = useCallback(async (chunkBlob: Blob, isFinal: boolean) => {
        if (!isMountedRef.current) {
            return;
        }

        // Don't process if already processing (prevents concurrent requests and timeouts)
        // Only allow final chunks to go through
        if (isProcessingRef.current && !isFinal) {
            console.log('Streaming: Already processing, skipping chunk to prevent concurrent requests');
            return;
        }

        try {
            console.log(`Streaming: Sending chunk (size: ${chunkBlob.size} bytes, final: ${isFinal})`);
            
            // Create session if needed
            if (!streamingSessionIdRef.current || streamingSessionIdRef.current === 'pending') {
                streamingSessionIdRef.current = 'pending';
            }

            // Send chunk to backend
            const result = await apiService.processStreamChunk(
                chunkBlob,
                streamingSessionIdRef.current === 'pending' ? '' : streamingSessionIdRef.current,
                userIdRef.current,
                conversationIdRef.current || undefined,
                'en-US',
                isFinal
            );

            console.log('Streaming: Chunk response:', {
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

            // Update conversation ID
            if (result.conversation_id) {
                conversationIdRef.current = result.conversation_id;
            }

            // If chunk has text, update live transcription
            if (result.chunk_text && result.chunk_text.trim()) {
                console.log(`Streaming: Chunk transcribed: "${result.chunk_text}"`);
                
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
            }

            // If noise detected or should process, trigger LLM
            if (result.should_process && result.merged_text && result.merged_text.trim()) {
                console.log(`Streaming: Processing merged text: "${result.merged_text}"`);
                
                // Process with LLM (only if not already processing)
                if (!isProcessingRef.current && !vadProcessingRef.current) {
                    vadProcessingRef.current = true;
                    setIsProcessing(true);
                    isProcessingRef.current = true;

                    try {
                        // Clear live transcription before adding final message
                        if (isMountedRef.current) {
                            setLiveTranscription('');
                        }
                        
                        // Add user message (this will replace live transcription)
                        onSendMessage(result.merged_text.trim());
                        
                        // Clear chunks only after successful message addition
                        // This marks chunks as sent but allows new chunks to continue accumulating
                        audioService.clearSpeechChunks();
                        
                        // Reset last chunk time to allow new chunks to accumulate immediately
                        lastChunkTimeRef.current = Date.now();
                        
                        // Log for debugging - ensure streaming continues
                        console.log('Streaming: Cleared processed chunks, ready for new audio. Session:', streamingSessionIdRef.current);

                        // Get LLM response
                        const llmResponse = await apiService.processStreamedText(
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

                        // Play audio (always play if available, not just when mic is on)
                        if (llmResponse.audio_base64) {
                            try {
                                console.log('Streaming: Playing TTS audio response');
                                const audioBytes = Uint8Array.from(atob(llmResponse.audio_base64), c => c.charCodeAt(0));
                                const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                                await audioService.playAudio(audioBlob);
                                console.log('Streaming: TTS audio played successfully');
                            } catch (error) {
                                console.error('Streaming: Error playing audio:', error);
                            }
                        } else {
                            console.warn('Streaming: No audio_base64 in LLM response');
                        }
                    } catch (error) {
                        console.error('Streaming: Error processing LLM response:', error);
                        if (isMountedRef.current) {
                            onReceiveMessage(`I'm sorry, I'm having trouble processing your voice. ${error instanceof Error ? error.message : 'Please try again.'}`);
                        }
                    } finally {
                        vadProcessingRef.current = false;
                        isProcessingRef.current = false;
                        if (isMountedRef.current) {
                            setIsProcessing(false);
                        }
                    }
                }
            }
        } catch (error) {
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
                    
                    if (shouldRespond && isMountedRef.current && !isProcessingRef.current && isMicActive) {
                        console.log('Streaming: Multiple STT errors detected, sending helpful response');
                        
                        // Reset error count after responding (but keep track for next time)
                        sttErrorCountRef.current = 0; // Reset to allow new error tracking
                        lastSttErrorTimeRef.current = Date.now(); // Update timestamp
                        
                        // Trigger helpful TTS response
                        try {
                            setIsProcessing(true);
                            isProcessingRef.current = true;
                            
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
                            isProcessingRef.current = false;
                            if (isMountedRef.current) {
                                setIsProcessing(false);
                            }
                        }
                    }
                }
            }
        }
    }, [isMicActive, onSendMessage, onReceiveMessage, userName]);

    // Streaming STT: Continuously send chunks to backend
    useEffect(() => {
        if (mode !== InteractionMode.VOICE || !isMicActive) {
            // Stop streaming if mic is off
            if (streamingChunkIntervalRef.current) {
                clearInterval(streamingChunkIntervalRef.current);
                streamingChunkIntervalRef.current = null;
            }
            streamingSessionIdRef.current = null;
            return;
        }

        // Wait for recording to actually start
        const checkRecording = setInterval(() => {
            if (!audioService.isRecording()) {
                return; // Wait for recording to start
            }

            // Clear the check interval
            clearInterval(checkRecording);

            // Initialize streaming
            console.log('Streaming: Starting continuous chunk streaming');
            streamingChunksRef.current = [];
            lastChunkTimeRef.current = Date.now();

            // Start sending chunks periodically
            const sendChunk = async () => {
                if (!isMountedRef.current || !isMicActive) {
                    console.log('Streaming: Stopping chunk sending - mic off or unmounted');
                    if (streamingChunkIntervalRef.current) {
                        clearInterval(streamingChunkIntervalRef.current);
                        streamingChunkIntervalRef.current = null;
                    }
                    return;
                }

                // Check if recording is still active
                if (!audioService.isRecording()) {
                    console.log('Streaming: Recording stopped, waiting for restart...');
                    return; // Don't stop interval, just skip this cycle
                }

                try {
                    // Get chunks from MediaRecorder
                    // Get speech chunks (all chunks collected, not just during detected speech)
                    const speechChunks = audioService.getSpeechChunks();
                    const now = Date.now();
                    
                    // Debug: Log chunk status
                    if (speechChunks.length === 0) {
                        console.log('Streaming: No new speech chunks available (this is normal after processing)');
                    } else {
                        console.log(`Streaming: Found ${speechChunks.length} new speech chunks`);
                    }
                    
                    // Create blob from speech chunks if available
                    let chunkBlob: Blob;
                    if (speechChunks.length > 0) {
                        const blobType = speechChunks[0]?.type || 'audio/webm';
                        chunkBlob = new Blob(speechChunks, { type: blobType });
                        
                        // Accumulate chunks until we have at least 30KB for 3-4 seconds of audio
                        // 30KB ≈ 3-4 seconds of audio at typical WebM/Opus bitrates (~64kbps)
                        // Process more frequently to prevent chunks from growing too large and becoming invalid
                        const MIN_CHUNK_SIZE = 30000; // 30KB minimum (faster processing)
                        const MAX_CHUNK_SIZE = 300000; // 300KB maximum (≈20 seconds) - prevent STT errors and invalid WebM
                        
                        // Force send if chunk is getting too large
                        if (chunkBlob.size >= MAX_CHUNK_SIZE) {
                            // Prevent concurrent requests
                            if (isProcessingRef.current) {
                                console.log('Streaming: Already processing, skipping large chunk send');
                                return;
                            }
                            
                            console.log(`Streaming: WARNING - Chunk too large (${chunkBlob.size} bytes), forcing send to prevent errors`);
                            lastChunkTimeRef.current = now;
                            await processStreamChunk(chunkBlob, false);
                            audioService.clearSpeechChunks();
                        } else if (chunkBlob.size >= MIN_CHUNK_SIZE) {
                            // Prevent concurrent requests
                            if (isProcessingRef.current) {
                                console.log('Streaming: Already processing, skipping chunk send');
                                return;
                            }
                            
                            // Mark as sent but DON'T clear yet - keep for VAD processing
                            lastChunkTimeRef.current = now;
                            console.log(`Streaming: Sending accumulated chunk with ${speechChunks.length} audio chunks (${chunkBlob.size} bytes)`);
                            
                            // Send chunk to backend
                            await processStreamChunk(chunkBlob, false);
                            
                            // Only clear chunks after successful send (but keep in audioChunks for VAD)
                            audioService.clearSpeechChunks();
                        } else {
                            // Too small, but if we've been waiting a while, send anyway (fallback for faster response)
                            const timeSinceLastChunk = now - lastChunkTimeRef.current;
                            if (timeSinceLastChunk > 5000 && chunkBlob.size >= 20000) {
                                // Send if we have at least 20KB (≈2.5 seconds) after 5 seconds (fallback threshold)
                                // Prevent concurrent requests
                                if (isProcessingRef.current) {
                                    console.log('Streaming: Already processing, skipping fallback chunk send');
                                    return;
                                }
                                
                                console.log(`Streaming: Sending smaller chunk (${chunkBlob.size} bytes) after waiting ${timeSinceLastChunk}ms`);
                                lastChunkTimeRef.current = now;
                                await processStreamChunk(chunkBlob, false);
                                audioService.clearSpeechChunks();
                            } else {
                                // Too small, wait for more chunks to accumulate
                                console.log(`Streaming: Chunk too small (${chunkBlob.size} bytes), waiting for more chunks...`);
                                return;
                            }
                        }
                    } else {
                        // No speech chunks - check if we should send empty chunk
                        // Only send empty chunks occasionally (every 5 seconds) to reduce API calls
                        const timeSinceLastChunk = now - lastChunkTimeRef.current;
                        if (timeSinceLastChunk > 5000 && !isProcessingRef.current) {
                            // Send empty blob to detect noise (reduced frequency to 5 seconds)
                            chunkBlob = new Blob([], { type: 'audio/webm' });
                            lastChunkTimeRef.current = now;
                            console.log('Streaming: No speech chunks, sending empty chunk to detect noise (every 5s)');
                            
                            // Send chunk to backend
                            await processStreamChunk(chunkBlob, false);
                        } else {
                            // Skip this cycle - too soon to send another empty chunk or already processing
                            return;
                        }
                    }
                } catch (error) {
                    if (error instanceof Error && error.name !== 'AbortError') {
                        console.error('Streaming: Error sending chunk:', error);
                    }
                }
            };

            // Send chunks less frequently to reduce API calls and prevent timeouts
            const CHUNK_INTERVAL = 3000; // Send every 3 seconds (reduced from 1 second)
            streamingChunkIntervalRef.current = setInterval(sendChunk, CHUNK_INTERVAL);
            console.log(`Streaming: Started interval (every ${CHUNK_INTERVAL}ms)`);
            
            // Send first chunk after accumulating more audio (2 seconds)
            setTimeout(() => {
                if (isMountedRef.current && isMicActive && audioService.isRecording()) {
                    sendChunk();
                }
            }, 2000); // Wait 2 seconds to accumulate more audio before first send
        }, 100); // Check every 100ms if recording has started

        return () => {
            if (streamingChunkIntervalRef.current) {
                clearInterval(streamingChunkIntervalRef.current);
                streamingChunkIntervalRef.current = null;
            }
        };
    }, [mode, isMicActive, processStreamChunk]);


    // VAD callback - updates audio level visualization and triggers processing on silence
    useEffect(() => {
        if (mode !== InteractionMode.VOICE) {
            audioService.setVADCallback(null);
            return;
        }

        const vadHandler = async (isSpeaking: boolean | null, audioLevel: number) => {
            if (!isMountedRef.current) return;
            
            // Update audio level for visualization (smooth updates)
            setAudioLevel(prev => {
                // Smooth transition for better UX (normalize to 0-1)
                const normalizedLevel = audioLevel / 100;
                return Math.round((prev * 0.7 + normalizedLevel * 0.3) * 100) / 100;
            });
            
            // null = special signal that speech has ended (trigger processing)
            // Backend VAD (silero-vad) will provide final filtering, but frontend VAD
            // helps reduce unnecessary processing and provides faster response
            if (isSpeaking === null) {
                console.log('VAD: Received speech-ended signal (frontend detection), checking for accumulated chunks');
                // Speech ended - trigger processing
                if (!isProcessingRef.current && !vadProcessingRef.current && isMicActive) {
                    vadProcessingRef.current = true;
                    
                    // Use getAllChunks to get ALL chunks (not just unsent ones)
                    // This ensures we can process even if chunks were already sent
                    const allChunks = audioService.getAllChunks();
                    console.log(`VAD: Found ${allChunks.length} total chunks to process`);
                    
                    if (allChunks.length > 0) {
                        // Small delay to ensure all chunks are collected
                        await new Promise(resolve => setTimeout(resolve, 50));
                        
                        // Double-check we still have chunks and aren't processing
                        const currentAllChunks = audioService.getAllChunks();
                        if (currentAllChunks.length > 0 && !isProcessingRef.current && isMountedRef.current && isMicActive) {
                            console.log(`VAD: Speech ended, triggering processing with ${currentAllChunks.length} accumulated chunks`);
                            
                            // Create blob from accumulated speech chunks
                            const blobType = currentAllChunks[0]?.type || 'audio/webm';
                            const speechBlob = new Blob(currentAllChunks, { type: blobType });
                            
                            console.log(`VAD: Created speech blob: ${speechBlob.size} bytes`);
                            
                            // Minimum size check - backend VAD will do final filtering
                            // But we can skip very small chunks to reduce API calls
                            if (speechBlob.size >= 2000) { // At least 2KB
                                // Clear live transcription before processing
                                if (isMountedRef.current) {
                                    setLiveTranscription('');
                                }
                                
                                // Send final chunk to trigger processing
                                // Backend VAD (silero-vad) will filter noise before STT
                                try {
                                    console.log('VAD: Sending final chunk to trigger processing (backend VAD will filter)');
                                    await processStreamChunk(speechBlob, true); // isFinal = true
                                    console.log('VAD: Final chunk sent successfully');
                                    
                                    // Clear chunks only after successful processing
                                    audioService.clearSpeechChunks();
                                } catch (error) {
                                    if (error instanceof Error && error.name !== 'AbortError') {
                                        console.error('VAD: Error processing silence trigger:', error);
                                    }
                                } finally {
                                    vadProcessingRef.current = false;
                                }
                            } else {
                                console.log(`VAD: Speech blob too small (${speechBlob.size} bytes), likely noise - skipping`);
                                audioService.clearSpeechChunks();
                                vadProcessingRef.current = false;
                            }
                        } else {
                            console.log('VAD: Chunks cleared or already processing, skipping');
                            vadProcessingRef.current = false;
                        }
                    } else {
                        console.log('VAD: No chunks to process');
                        vadProcessingRef.current = false;
                    }
                } else {
                    console.log('VAD: Already processing or mic inactive, skipping VAD trigger');
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
        
        // Warn user at 50 seconds
        warningTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current && isMicActive && audioService.isRecording()) {
                onReceiveMessage('⚠️ Recording will stop automatically in 10 seconds. Please finish your message.');
            }
        }, 50000); // 50 seconds warning
        
        // Set timeout to auto-stop after 60 seconds
        maxRecordingDurationRef.current = setTimeout(() => {
            if (!isMountedRef.current) return;
            console.warn('Maximum recording duration reached (60s), auto-stopping...');
            if (isMicActive && !isProcessing && !isProcessingRef.current && audioService.isRecording()) {
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
            if (warningTimeoutRef.current) {
                clearTimeout(warningTimeoutRef.current);
                warningTimeoutRef.current = null;
            }
        };
    }, [isMicActive, isProcessing]);

    // Separate function to process recording (called automatically when mic stops)
    const handleProcessRecording = useCallback(async (audioBlob: Blob) => {
        if (isProcessing || isProcessingRef.current) {
            console.log('Already processing, ignoring');
            return;
        }

        if (!isMountedRef.current) {
            console.log('Component unmounted, aborting processing');
            return;
        }

        try {
            setIsProcessing(true);
            isProcessingRef.current = true;

            // Add a temporary "transcribing..." message
            onSendMessage('[Transcribing your voice...]');

            // Check audio size
            const minAudioSize = 1000; // 1KB minimum
            if (audioBlob.size < minAudioSize) {
                console.warn(`Audio too short (${audioBlob.size} bytes), ignoring`);
                isProcessingRef.current = false;
                setIsProcessing(false);
                return;
            }

            const MAX_AUDIO_SIZE = 10 * 1024 * 1024; // 10MB
            if (audioBlob.size > MAX_AUDIO_SIZE) {
                const sizeMB = (audioBlob.size / 1024 / 1024).toFixed(2);
                const errorMsg = `Audio file too large (${sizeMB}MB). Maximum size is 10MB.`;
                onReceiveMessage(`⚠️ ${errorMsg}`);
                isProcessingRef.current = false;
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
                isProcessingRef.current = false;
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
            if (!audioService.isRecording() && !isMicActive) {
                console.log('Mic is off, skipping audio playback');
                return;
            }

            if (response.audio_base64) {
                console.log('Playing audio from base64 response');
                try {
                    const audioBytes = Uint8Array.from(atob(response.audio_base64), c => c.charCodeAt(0));
                    const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                    await audioService.playAudio(audioBlob);
                    console.log('Audio playback started');
                } catch (error) {
                    console.error('Error playing audio:', error);
                }
            } else if (response.audio_url) {
                console.log('Fetching audio from URL:', response.audio_url);
                try {
                    const audioBlob = await apiService.getAudio(response.audio_url);
                    if (!isMountedRef.current || audioService.isRecording()) {
                        return;
                    }
                    await audioService.playAudio(audioBlob);
                    console.log('Audio playback started from URL');
                } catch (error) {
                    console.error('Error playing audio from URL:', error);
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
            isProcessingRef.current = false;
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
                        await processStreamChunk(finalBlob, true); // isFinal = true
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