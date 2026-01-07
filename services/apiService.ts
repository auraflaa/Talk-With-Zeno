/**
 * Backend API Service
 * Connects frontend to backend API
 */

import { logWithTimestamp, warnWithTimestamp, errorWithTimestamp } from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';

export interface VoiceResponse {
  text_response: string;
  conversation_id: string;
  updates_applied: any[];
  user_text: string;
  audio_url?: string;
  audio_base64?: string;
}

export interface TextResponse {
  text_response: string;
  conversation_id: string;
  updates_applied: any[];
  audio_url?: string;
  audio_base64?: string;
}

class ApiService {
  private baseUrl: string;
  private pendingChunkRequests: Map<string, AbortController> = new Map(); // Track pending chunk requests
  private chunkRequestQueue: Array<() => Promise<void>> = []; // Queue for chunk requests
  private isProcessingChunkQueue: boolean = false; // Track if queue is being processed

  constructor() {
    this.baseUrl = API_BASE_URL;
  }

  async processVoice(
    audioBlob: Blob,
    userId: string,
    conversationId?: string,
    languageCode: string = 'en-US',
    userName?: string
  ): Promise<VoiceResponse> {
    try {
      // Check audio size before upload (10MB limit)
      const MAX_AUDIO_SIZE = 10 * 1024 * 1024; // 10MB
      if (audioBlob.size > MAX_AUDIO_SIZE) {
        throw new Error(`Audio file too large (${(audioBlob.size / 1024 / 1024).toFixed(2)}MB). Maximum size is 10MB. Please record a shorter message.`);
      }

      const formData = new FormData();
      // Use the actual blob type (webm) instead of forcing .wav
      const filename = audioBlob.type.includes('webm') ? 'audio.webm' : 'audio.wav';
      formData.append('audio', audioBlob, filename);
      formData.append('user_id', userId);
      formData.append('language_code', languageCode);
      if (conversationId) {
        formData.append('conversation_id', conversationId);
      }
      if (userName) {
        formData.append('user_name', userName);
      }

      logWithTimestamp(`Sending audio to backend: ${filename}, size: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
      logWithTimestamp(`Backend URL: ${this.baseUrl}/api/voice/process`);
      logWithTimestamp(`User ID: ${userId}, Conversation ID: ${conversationId || 'new'}`);

      // Add timeout (90 seconds for voice processing - STT chunk processing can take time)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 90000); // 90 second timeout

      const startTime = Date.now();
      let response: Response;
      try {
        response = await fetch(`${this.baseUrl}/api/voice/process`, {
          method: 'POST',
          body: formData,
          signal: controller.signal,
        });
      } catch (error: any) {
        clearTimeout(timeoutId);
        // Check if it's a network error
        if (error.name === 'AbortError') {
          throw new Error('Voice processing timed out. The backend took too long to respond. Please try again.');
        }
        if (error.message?.includes('fetch') || error.message?.includes('network') || error.message?.includes('Failed to fetch')) {
          throw new Error('Cannot connect to backend server. Please ensure the backend is running on http://localhost:5000');
        }
        throw error;
      }

      clearTimeout(timeoutId);
      const duration = Date.now() - startTime;
      logWithTimestamp(`Backend response received in ${duration}ms, status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        let errorMessage = 'Failed to process voice';
        try {
          const errorData = await response.json();
          errorMessage = errorData.error || errorMessage;
          errorWithTimestamp('Backend error response:', errorData);
        } catch (e) {
          const errorText = await response.text();
          errorWithTimestamp('Backend error (text):', errorText);
          errorMessage = errorText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      const responseData = await response.json();
      logWithTimestamp('Voice response received:', {
        hasConversationId: !!responseData.conversation_id,
        hasUserText: !!responseData.user_text,
        hasTextResponse: !!responseData.text_response,
        hasAudioBase64: !!responseData.audio_base64,
        hasAudioUrl: !!responseData.audio_url
      });
      
      return responseData;
    } catch (error) {
      errorWithTimestamp('Error in processVoice:', error);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error('Voice processing timed out. The backend took too long to respond. Please try again.');
        }
        if (error.message.includes('fetch') || error.message.includes('network') || error.message.includes('Failed to fetch')) {
          throw new Error('Cannot connect to backend server. Please ensure the backend is running on http://localhost:5000');
        }
      }
      throw error;
    }
  }

  async processText(
    text: string,
    userId: string,
    conversationId?: string,
    generateAudio: boolean = false,
    userName?: string
  ): Promise<TextResponse> {
      logWithTimestamp(`Sending text to backend: "${text}", user: ${userId}, conversation: ${conversationId || 'new'}, audio: ${generateAudio}`);
      logWithTimestamp(`Backend URL: ${this.baseUrl}/api/text/process`);

    try {
      // Add timeout (30 seconds for LLM processing - reduced for faster response)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // Reduced to 30 seconds for faster timeout

      const startTime = Date.now();
      const response = await fetch(`${this.baseUrl}/api/text/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text,
          user_id: userId,
          conversation_id: conversationId,
          generate_audio: generateAudio, // Only generate audio if requested
          user_name: userName,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const duration = Date.now() - startTime;
      logWithTimestamp(`Backend response received in ${duration}ms, status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        let errorMessage = `Failed to process text (${response.status})`;
        try {
          const errorData = await response.json();
          errorMessage = errorData.error || errorMessage;
          errorWithTimestamp('Backend error response:', errorData);
        } catch (e) {
          const errorText = await response.text();
          errorWithTimestamp('Backend error (text):', errorText);
          errorMessage = errorText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      const responseData = await response.json();
      logWithTimestamp('Text response received:', {
        hasConversationId: !!responseData.conversation_id,
        hasTextResponse: !!responseData.text_response,
        hasAudioBase64: !!responseData.audio_base64,
        hasAudioUrl: !!responseData.audio_url,
        responseLength: responseData.text_response?.length || 0
      });
      
      return responseData;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        errorWithTimestamp('Request timeout - LLM took too long to respond');
        throw new Error('The response is taking too long. Please try again with a shorter message.');
      }
      if (error instanceof TypeError && error.message.includes('fetch')) {
        errorWithTimestamp('Network error - backend may not be running:', error);
        throw new Error('Cannot connect to backend server. Please make sure the backend is running on http://localhost:5000');
      }
      throw error;
    }
  }

  async getAudio(audioUrl: string): Promise<Blob> {
    const response = await fetch(`${this.baseUrl}${audioUrl}`);
    if (!response.ok) {
      throw new Error('Failed to fetch audio');
    }
    return response.blob();
  }

  async healthCheck(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout
      
      const response = await fetch(`${this.baseUrl}/api/health`, {
        signal: controller.signal,
        cache: 'no-cache' // Prevent caching of health check
      });
      
      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      // Don't log every health check failure to reduce console spam
      // Only log if it's not an abort error (which is expected for timeouts)
      if (error instanceof Error && error.name !== 'AbortError') {
        console.log('Health check failed:', error.message);
      }
      return false;
    }
  }

  /**
   * Create a new streaming session
   */
  async createStreamingSession(
    userId: string,
    conversationId?: string,
    languageCode: string = 'en-US',
    userName?: string
  ): Promise<string> {
    try {
      const response = await fetch(`${this.baseUrl}/api/voice/stream/chunk`, {
        method: 'POST',
        body: new FormData(), // Empty initial request to create session
        headers: {
          'X-Create-Session': 'true',
          'X-User-Id': userId,
          'X-Conversation-Id': conversationId || '',
          'X-Language-Code': languageCode,
          'X-User-Name': userName || '', // Send user name for personalization
        },
      });

      if (!response.ok) {
        throw new Error('Failed to create streaming session');
      }

      const data = await response.json();
      return data.session_id;
    } catch (error) {
      console.error('Error creating streaming session:', error);
      throw error;
    }
  }

  /**
   * Process queued chunk requests sequentially to prevent concurrent requests
   */
  private async processChunkQueue(): Promise<void> {
    if (this.isProcessingChunkQueue || this.chunkRequestQueue.length === 0) {
      return;
    }

    this.isProcessingChunkQueue = true;

    while (this.chunkRequestQueue.length > 0) {
      const requestFn = this.chunkRequestQueue.shift();
      if (requestFn) {
        try {
          await requestFn();
        } catch (error) {
          console.error('Error processing queued chunk request:', error);
        }
      }
    }

    this.isProcessingChunkQueue = false;
  }

  /**
   * Send an audio chunk for streaming STT processing
   * Uses a queue to prevent too many concurrent requests
   */
  async processStreamChunk(
    audioBlob: Blob,
    sessionId: string,
    userId: string,
    conversationId?: string,
    languageCode: string = 'en-US',
    isFinal: boolean = false,
    userName?: string
  ): Promise<{
    chunk_text: string;
    is_noise: boolean;
    merged_text: string;
    should_process: boolean;
    session_id: string;
    conversation_id: string;
  }> {
    // Cancel any pending requests for the same session (except final chunks)
    if (!isFinal && sessionId && sessionId !== 'pending') {
      const existingController = this.pendingChunkRequests.get(sessionId);
      if (existingController && !existingController.signal.aborted) {
        logWithTimestamp('Cancelling previous chunk request for same session');
        existingController.abort();
        this.pendingChunkRequests.delete(sessionId);
      }
    }

    return new Promise((resolve, reject) => {
      const requestFn = async () => {
        try {
          const formData = new FormData();
          const filename = audioBlob.type.includes('webm') ? 'audio.webm' : 'audio.wav';
          formData.append('audio', audioBlob, filename);
          if (sessionId && sessionId !== 'pending') {
            formData.append('session_id', sessionId);
          }
          formData.append('user_id', userId);
          formData.append('language_code', languageCode);
          formData.append('is_final', isFinal.toString());
          if (conversationId) {
            formData.append('conversation_id', conversationId);
          }
          if (userName) {
            formData.append('user_name', userName); // Send user name for personalization
          }

          const controller = new AbortController();
          
          // Track controller for cancellation
          if (sessionId && sessionId !== 'pending' && !isFinal) {
            this.pendingChunkRequests.set(sessionId, controller);
          }

          const timeoutId = setTimeout(() => {
            if (!controller.signal.aborted) {
              controller.abort();
            }
          }, 30000); // Reduced to 30 seconds for faster timeout (STT should be faster with smaller chunks)

          let response: Response;
          try {
            response = await fetch(`${this.baseUrl}/api/voice/stream/chunk`, {
              method: 'POST',
              body: formData,
              signal: controller.signal,
            });
            clearTimeout(timeoutId);
          } catch (error) {
            clearTimeout(timeoutId);
            // Clean up controller
            if (sessionId && sessionId !== 'pending') {
              this.pendingChunkRequests.delete(sessionId);
            }
            // Re-throw if it's not an abort error
            if (error instanceof Error && error.name === 'AbortError') {
              reject(new Error('Request timeout - STT took too long to process chunk'));
              return;
            }
            reject(error);
            return;
          }

          // Clean up controller on success
          if (sessionId && sessionId !== 'pending') {
            this.pendingChunkRequests.delete(sessionId);
          }

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
            reject(new Error(errorData.error || 'Failed to process stream chunk'));
            return;
          }

          const result = await response.json();
          resolve(result);
        } catch (error) {
          errorWithTimestamp('Error processing stream chunk:', error);
          reject(error);
        }
      };

      // Add to queue
      this.chunkRequestQueue.push(requestFn);
      
      // Process queue (will handle sequentially)
      this.processChunkQueue().catch(reject);
    });
  }

  /**
   * Process merged text from streaming session with LLM
   */
  async processStreamedText(
    sessionId: string,
    mergedText: string,
    userName?: string
  ): Promise<VoiceResponse> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // Reduced to 30 seconds for faster timeout

      const response = await fetch(`${this.baseUrl}/api/voice/stream/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          merged_text: mergedText,
          user_name: userName,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || 'Failed to process streamed text');
      }

      const responseData = await response.json();
      logWithTimestamp('Streaming LLM response received:', {
        hasTextResponse: !!responseData.text_response,
        hasAudioBase64: !!responseData.audio_base64,
        textLength: responseData.text_response?.length || 0,
        audioBase64Length: responseData.audio_base64?.length || 0
      });
      return responseData;
    } catch (error) {
      errorWithTimestamp('Error processing streamed text:', error);
      throw error;
    }
  }
}

export const apiService = new ApiService();

