/**
 * Backend API Service
 * Connects frontend to backend API
 */

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

      console.log(`Sending audio to backend: ${filename}, size: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
      console.log(`Backend URL: ${this.baseUrl}/api/voice/process`);
      console.log(`User ID: ${userId}, Conversation ID: ${conversationId || 'new'}`);

      // Add timeout (60 seconds for voice processing)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

      const startTime = Date.now();
      const response = await fetch(`${this.baseUrl}/api/voice/process`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      const duration = Date.now() - startTime;
      console.log(`Backend response received in ${duration}ms, status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        let errorMessage = 'Failed to process voice';
        try {
          const errorData = await response.json();
          errorMessage = errorData.error || errorMessage;
          console.error('Backend error response:', errorData);
        } catch (e) {
          const errorText = await response.text();
          console.error('Backend error (text):', errorText);
          errorMessage = errorText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      const responseData = await response.json();
      console.log('Voice response received:', {
        hasConversationId: !!responseData.conversation_id,
        hasUserText: !!responseData.user_text,
        hasTextResponse: !!responseData.text_response,
        hasAudioBase64: !!responseData.audio_base64,
        hasAudioUrl: !!responseData.audio_url
      });
      
      return responseData;
    } catch (error) {
      console.error('Error in processVoice:', error);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Voice processing timed out. The backend took too long to respond. Please try again.');
      }
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Cannot connect to backend server. Please ensure the backend is running on http://localhost:5000');
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
    console.log(`Sending text to backend: "${text}", user: ${userId}, conversation: ${conversationId || 'new'}, audio: ${generateAudio}`);
    console.log(`Backend URL: ${this.baseUrl}/api/text/process`);

    try {
      // Add timeout (60 seconds for LLM processing)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

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
      console.log(`Backend response received in ${duration}ms, status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        let errorMessage = `Failed to process text (${response.status})`;
        try {
          const errorData = await response.json();
          errorMessage = errorData.error || errorMessage;
          console.error('Backend error response:', errorData);
        } catch (e) {
          const errorText = await response.text();
          console.error('Backend error (text):', errorText);
          errorMessage = errorText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      const responseData = await response.json();
      console.log('Text response received:', {
        hasConversationId: !!responseData.conversation_id,
        hasTextResponse: !!responseData.text_response,
        hasAudioBase64: !!responseData.audio_base64,
        hasAudioUrl: !!responseData.audio_url,
        responseLength: responseData.text_response?.length || 0
      });
      
      return responseData;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.error('Request timeout - LLM took too long to respond');
        throw new Error('The response is taking too long. Please try again with a shorter message.');
      }
      if (error instanceof TypeError && error.message.includes('fetch')) {
        console.error('Network error - backend may not be running:', error);
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
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      return response.ok;
    } catch (error) {
      console.log('Health check failed:', error instanceof Error ? error.message : 'Unknown error');
      return false;
    }
  }
}

export const apiService = new ApiService();

