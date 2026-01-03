/**
 * Audio Recording and Playback Service
 */

export class AudioService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null; // Track URL for cleanup
  private readonly MAX_CHUNKS = 1000; // Prevent memory leak from too many chunks
  
  // VAD (Voice Activity Detection) properties
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private microphone: MediaStreamAudioSourceNode | null = null;
  private vadCallback: ((isSpeaking: boolean | null, audioLevel: number) => void) | null = null;
  private vadInterval: number | null = null;
  private isVADActive: boolean = false;
  
  // VAD thresholds
  private readonly VAD_THRESHOLD = 30; // Volume threshold (0-255)
  private readonly SILENCE_DURATION = 1500; // ms of silence before auto-stop
  private readonly MIN_SPEECH_DURATION = 500; // ms minimum speech to process
  
  // Speech detection state
  private lastSpeechTime: number = 0;
  private speechStartTime: number = 0;
  private isCurrentlySpeaking: boolean = false;
  private speechChunks: Blob[] = []; // Chunks collected for streaming (all chunks, not just speech)
  private lastSentChunkIndex: number = 0; // Track which chunks have been sent for streaming

  async startRecording(): Promise<void> {
    try {
      // CRITICAL: Stop any existing recording first to prevent multiple instances
      if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
        console.warn('WARNING: Stopping existing recording before starting new one');
        try {
          this.mediaRecorder.stop();
          // Wait a moment for it to stop
          await new Promise(resolve => setTimeout(resolve, 100));
        } catch (e) {
          console.warn('Error stopping existing recorder:', e);
        }
      }
      
      // Clean up any existing stream and recorder
      this.cleanup();
      
      console.log('Requesting microphone access...');
      
      // Check if getUserMedia is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Microphone access not available in this browser. Please use a modern browser like Chrome, Firefox, or Edge.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      console.log('Microphone access granted');
      this.stream = stream;
      this.audioChunks = [];

      // Try different audio formats in order of preference
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
        '' // Browser default
      ];

      let selectedMimeType = '';
      for (const mimeType of mimeTypes) {
        if (!mimeType || MediaRecorder.isTypeSupported(mimeType)) {
          selectedMimeType = mimeType;
          break;
        }
      }

      const options: MediaRecorderOptions = {};
      if (selectedMimeType) {
        options.mimeType = selectedMimeType;
        console.log(`Using audio format: ${selectedMimeType}`);
      } else {
        console.log('Using browser default audio format');
      }

      this.mediaRecorder = new MediaRecorder(stream, options);

      // Track stream tracks for permission revocation detection
      const audioTracks = stream.getAudioTracks();
      audioTracks.forEach(track => {
        track.onended = () => {
          console.warn('Audio track ended - microphone permission may have been revoked');
          // This will be handled by cleanup
        };
      });

      // Track last sent chunk index for streaming
      this.lastSentChunkIndex = 0;

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          // Prevent memory leak - limit chunk count
          if (this.audioChunks.length >= this.MAX_CHUNKS) {
            console.warn(`Maximum chunk limit reached (${this.MAX_CHUNKS}), removing oldest chunks`);
            // Remove oldest 100 chunks to make room
            this.audioChunks.splice(0, 100);
            // Adjust last sent index
            this.lastSentChunkIndex = Math.max(0, this.lastSentChunkIndex - 100);
          }
          this.audioChunks.push(event.data);
          
          // CRITICAL: Always collect chunks for streaming (not just during detected speech)
          // This ensures continuous streaming regardless of VAD state
          // NOTE: VAD might not be active immediately, so we collect all chunks
          this.speechChunks.push(event.data);
          
          // Limit speech chunks to prevent memory issues (keep last 200 chunks for streaming)
          // Only limit if we have way too many (safety measure)
          if (this.speechChunks.length > 200) {
            const removedCount = this.speechChunks.length - 200;
            const oldLength = this.speechChunks.length;
            this.speechChunks.splice(0, removedCount);
            // Adjust last sent index when chunks are removed
            this.lastSentChunkIndex = Math.max(0, this.lastSentChunkIndex - removedCount);
            console.log(`Streaming: Removed ${removedCount} old chunks (${oldLength} -> ${this.speechChunks.length}), adjusted index to ${this.lastSentChunkIndex}`);
          }
          
          // Only log every 10th chunk to reduce console spam
          if (this.audioChunks.length % 10 === 0) {
            const totalSize = this.audioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
            console.log(`Audio chunk received: ${event.data.size} bytes (total chunks: ${this.audioChunks.length}, total size: ${totalSize} bytes)`);
          }
        } else {
          console.warn('Received empty audio chunk');
        }
      };

      this.mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event);
      };

      this.mediaRecorder.onstart = () => {
        console.log('Recording started');
      };

      this.mediaRecorder.onstop = () => {
        console.log('Recording stopped');
      };

      // Start recording with timeslice to ensure chunks are collected
      // Using 250ms timeslice for better chunk collection
      this.mediaRecorder.start(250); // Collect data every 250ms
      console.log('MediaRecorder started successfully with 250ms timeslice');
      
      // Initialize VAD (Voice Activity Detection)
      this.startVAD(stream);
      
      // Log recording state after a short delay to verify it's actually recording
      setTimeout(() => {
        if (this.mediaRecorder) {
          console.log(`MediaRecorder state after 500ms: ${this.mediaRecorder.state}`);
          if (this.mediaRecorder.state === 'recording') {
            console.log('Recording confirmed active');
          } else {
            console.warn(`WARNING: MediaRecorder state is ${this.mediaRecorder.state}, expected 'recording'`);
          }
        }
      }, 500);
    } catch (error: any) {
      console.error('Error starting recording:', error);
      if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
        throw new Error('Microphone permission denied. Please allow microphone access in your browser settings.');
      } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
        throw new Error('No microphone found. Please connect a microphone and try again.');
      } else if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
        throw new Error('Microphone is being used by another application. Please close other apps using the microphone.');
      } else {
        throw new Error(`Failed to start recording: ${error.message || error}`);
      }
    }
  }

  async stopRecording(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder) {
        reject(new Error('No active recording'));
        return;
      }

      const currentState = this.mediaRecorder.state;
      console.log(`Stopping recording. Current state: ${currentState}`);
      
      if (currentState === 'inactive') {
        console.warn('Recording already stopped or inactive');
        // If already stopped but we have chunks, try to create blob anyway
        if (this.audioChunks.length > 0) {
          const totalSize = this.audioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
          const blobType = this.audioChunks[0].type || 'audio/webm';
          const audioBlob = new Blob(this.audioChunks, { type: blobType });
          console.log(`Created audio blob from stopped recorder: ${audioBlob.size} bytes`);
          this.cleanup();
          resolve(audioBlob);
          return;
        }
        reject(new Error('Recording already stopped'));
        return;
      }

      const timeout = setTimeout(() => {
        console.error('Recording stop timeout - forcing cleanup');
        // Force cleanup and try to create blob from collected chunks
        if (this.audioChunks.length > 0) {
          const totalSize = this.audioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
          const blobType = this.audioChunks[0].type || 'audio/webm';
          const audioBlob = new Blob(this.audioChunks, { type: blobType });
          console.log(`Created audio blob after timeout: ${audioBlob.size} bytes`);
          this.cleanup();
          resolve(audioBlob);
        } else {
          this.cleanup();
          reject(new Error('Recording stop timeout - no audio data'));
        }
      }, 3000); // Reduced timeout to 3 seconds

      // Store reference to current recorder to avoid race conditions
      const recorder = this.mediaRecorder;
      const chunks = this.audioChunks;

      recorder.onstop = () => {
        clearTimeout(timeout);
        const totalSize = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
        console.log(`Recording stopped. Total audio chunks: ${chunks.length}, Total size: ${totalSize} bytes`);
        
        if (chunks.length === 0) {
          console.error('ERROR: No audio chunks collected. Possible reasons:');
          console.error('  1. Recording was stopped too quickly (before any chunks were collected)');
          console.error('  2. MediaRecorder did not receive any data');
          console.error('  3. Microphone is not working or not capturing audio');
          console.error('  4. Browser permissions issue');
          this.cleanup();
          reject(new Error('No audio data recorded. Please ensure you speak for at least 1 second and your microphone is working.'));
          return;
        }
        
        if (totalSize < 100) {
          console.warn(`WARNING: Very small audio size (${totalSize} bytes). This might be silence or a recording issue.`);
        }

        // Determine blob type from the first chunk or use webm as default
        const blobType = chunks[0].type || 'audio/webm';
        const audioBlob = new Blob(chunks, { type: blobType });
        console.log(`Created audio blob: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
        
        this.cleanup();
        resolve(audioBlob);
      };

      recorder.onerror = (event: any) => {
        clearTimeout(timeout);
        console.error('Error stopping recording:', event);
        // Try to create blob from collected chunks even on error
        if (chunks.length > 0) {
          const totalSize = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
          const blobType = chunks[0].type || 'audio/webm';
          const audioBlob = new Blob(chunks, { type: blobType });
          console.log(`Created audio blob despite error: ${audioBlob.size} bytes`);
          this.cleanup();
          resolve(audioBlob);
        } else {
          this.cleanup();
          reject(new Error('Error stopping recording'));
        }
      };

      try {
        console.log('Calling MediaRecorder.stop()...');
        recorder.stop();
        console.log('MediaRecorder.stop() called successfully');
      } catch (error) {
        clearTimeout(timeout);
        console.error('Exception calling MediaRecorder.stop():', error);
        // Try to create blob from collected chunks even on exception
        if (chunks.length > 0) {
          const totalSize = chunks.reduce((sum, chunk) => sum + chunk.size, 0);
          const blobType = chunks[0].type || 'audio/webm';
          const audioBlob = new Blob(chunks, { type: blobType });
          console.log(`Created audio blob despite exception: ${audioBlob.size} bytes`);
          this.cleanup();
          resolve(audioBlob);
        } else {
          this.cleanup();
          reject(new Error(`Failed to stop recording: ${error}`));
        }
      }
    });
  }

  private cleanup(): void {
    console.log('Cleaning up audio service...');
    
    // Stop VAD first
    this.stopVAD();
    
    // Stop MediaRecorder if it exists and is still recording
    if (this.mediaRecorder) {
      try {
        if (this.mediaRecorder.state !== 'inactive') {
          console.log(`Stopping MediaRecorder in cleanup (state: ${this.mediaRecorder.state})`);
          this.mediaRecorder.stop();
          // Wait a moment for stop to complete
          setTimeout(() => {}, 100);
        }
      } catch (e) {
        console.warn('Error stopping MediaRecorder in cleanup:', e);
      }
      // Remove event listeners to prevent memory leaks
      try {
        this.mediaRecorder.ondataavailable = null;
        this.mediaRecorder.onerror = null;
        this.mediaRecorder.onstart = null;
        this.mediaRecorder.onstop = null;
      } catch (e) {
        console.warn('Error removing event listeners:', e);
      }
    }
    
    // Stop all tracks in the stream
    if (this.stream) {
      this.stream.getTracks().forEach(track => {
        try {
          // Remove event listeners from tracks
          track.onended = null;
          track.stop();
          console.log('Stopped audio track');
        } catch (e) {
          console.warn('Error stopping track:', e);
        }
      });
      this.stream = null;
    }
    
    // Clear references
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.speechChunks = [];
    this.lastSentChunkIndex = 0;
    this.isCurrentlySpeaking = false;
    console.log('Audio service cleanup complete');
  }
  
  // Force stop method for emergency cleanup
  forceStop(): void {
    console.log('FORCE STOP: Emergency cleanup of audio service');
    this.stopVAD();
    this.cleanup();
  }

  /**
   * Get audio blob from speech chunks (for VAD-based processing)
   */
  getSpeechBlob(): Blob | null {
    if (this.speechChunks.length === 0) {
      return null;
    }
    
    // Determine blob type from first chunk
    const blobType = this.speechChunks[0].type || 'audio/webm';
    return new Blob(this.speechChunks, { type: blobType });
  }

  async playAudio(audioBlob: Blob): Promise<void> {
    return new Promise((resolve, reject) => {
      // Stop any currently playing audio
      this.stopAudio();
      
      const audio = new Audio();
      const url = URL.createObjectURL(audioBlob);
      this.currentAudio = audio;
      this.currentAudioUrl = url; // Track URL for cleanup

      // Ensure URL is always revoked, even on errors
      const cleanup = () => {
        if (this.currentAudioUrl === url) {
          URL.revokeObjectURL(url);
          this.currentAudioUrl = null;
        }
        if (this.currentAudio === audio) {
          this.currentAudio = null;
        }
      };

      audio.onended = () => {
        console.log('Audio playback ended');
        cleanup();
        resolve();
      };

      audio.onerror = (error) => {
        console.error('Audio playback error:', error, audio.error);
        cleanup();
        reject(new Error(`Failed to play audio: ${audio.error?.message || 'Unknown error'}`));
      };

      audio.oncanplaythrough = () => {
        console.log('Audio ready to play');
      };

      audio.src = url;
      const playPromise = audio.play();
      
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            console.log('Audio play() succeeded');
          })
          .catch((error) => {
            console.error('Audio play() failed:', error);
            cleanup();
            reject(error);
          });
      } else {
        // Fallback for browsers that don't return promise
        setTimeout(() => {
          if (audio.error) {
            cleanup();
            reject(new Error(`Failed to play audio: ${audio.error.message}`));
          }
        }, 1000);
      }
    });
  }

  stopAudio(): void {
    if (this.currentAudio) {
      try {
        console.log('Stopping current audio playback');
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        // Remove event listeners to prevent memory leaks
        this.currentAudio.onended = null;
        this.currentAudio.onerror = null;
        this.currentAudio.oncanplaythrough = null;
        this.currentAudio.onloadstart = null;
        this.currentAudio.onloadeddata = null;
        // Clean up the audio element
        this.currentAudio.src = '';
        this.currentAudio.load(); // Reset audio element
        this.currentAudio = null;
      } catch (error) {
        console.error('Error stopping audio:', error);
        this.currentAudio = null;
      }
    }
    // Revoke URL if it exists (always cleanup)
    if (this.currentAudioUrl) {
      try {
        URL.revokeObjectURL(this.currentAudioUrl);
        this.currentAudioUrl = null;
      } catch (error) {
        console.warn('Error revoking audio URL:', error);
        // Still clear the reference even if revoke fails
        this.currentAudioUrl = null;
      }
    }
  }

  isPlaying(): boolean {
    return this.currentAudio !== null && !this.currentAudio.paused && !this.currentAudio.ended;
  }

  isRecording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }

  /**
   * Start Voice Activity Detection (VAD)
   * Monitors audio levels to detect speech vs noise
   */
  private startVAD(stream: MediaStream): void {
    try {
      // Create AudioContext for VAD
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.8;
      
      // Connect microphone to analyser
      this.microphone = this.audioContext.createMediaStreamSource(stream);
      this.microphone.connect(this.analyser);
      
      // Initialize speech detection state
      this.lastSpeechTime = Date.now();
      this.speechStartTime = 0;
      this.isCurrentlySpeaking = false;
      // Don't clear speechChunks here - they should persist for streaming
      // Only reset the sent index
      this.lastSentChunkIndex = this.speechChunks.length; // Continue from where we left off
      this.isVADActive = true;
      
      // Start VAD monitoring
      this.monitorVAD();
      
      console.log('VAD started - monitoring for speech activity');
    } catch (error) {
      console.error('Error starting VAD:', error);
      this.isVADActive = false;
    }
  }

  /**
   * Monitor audio levels for voice activity detection
   */
  private monitorVAD(): void {
    if (!this.isVADActive || !this.analyser) {
      return;
    }

    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(dataArray);
    
    // Calculate average volume (simple energy-based VAD)
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const averageVolume = sum / dataArray.length;
    
    // Also check time domain for better detection
    const timeData = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteTimeDomainData(timeData);
    
    // Calculate RMS (Root Mean Square) for time domain
    let rms = 0;
    for (let i = 0; i < timeData.length; i++) {
      const normalized = (timeData[i] - 128) / 128;
      rms += normalized * normalized;
    }
    rms = Math.sqrt(rms / timeData.length) * 100;
    
    // Combined threshold check (frequency + time domain)
    const isSpeaking = averageVolume > this.VAD_THRESHOLD || rms > 15;
    const audioLevel = Math.min(100, (averageVolume / 255) * 100);
    
    const now = Date.now();
    
    if (isSpeaking) {
      // Speech detected
      if (!this.isCurrentlySpeaking) {
        // Speech just started
        this.isCurrentlySpeaking = true;
        this.speechStartTime = now;
        // Don't reset chunks - keep accumulating for streaming
        // Chunks will be cleared after processing by the frontend
        console.log('VAD: Speech detected, continuing to collect audio');
      }
      this.lastSpeechTime = now;
    } else {
      // Silence detected
      if (this.isCurrentlySpeaking) {
        // Check if silence duration exceeds threshold
        const silenceDuration = now - this.lastSpeechTime;
        if (silenceDuration > this.SILENCE_DURATION) {
          // Speech ended, check if we have enough audio
          const speechDuration = this.lastSpeechTime - this.speechStartTime;
          if (speechDuration >= this.MIN_SPEECH_DURATION) {
            console.log(`VAD: Speech ended (duration: ${speechDuration}ms), ready to process`);
            // Mark speech as ended
            this.isCurrentlySpeaking = false;
            this.speechStartTime = 0;
            
            // Trigger callback with special signal: null = speech ended (trigger processing)
            if (this.vadCallback) {
              this.vadCallback(null, audioLevel); // null = speech ended signal
            }
            return; // Don't call callback again with current state
          } else {
            console.log(`VAD: Speech too short (${speechDuration}ms), ignoring`);
            this.speechChunks = []; // Clear short speech
            this.isCurrentlySpeaking = false;
            this.speechStartTime = 0;
          }
        }
      }
    }
    
    // Call callback with current state (normal updates)
    if (this.vadCallback) {
      this.vadCallback(isSpeaking, audioLevel);
    }
    
    // Continue monitoring
    if (this.isVADActive) {
      this.vadInterval = window.setTimeout(() => this.monitorVAD(), 100); // Check every 100ms
    }
  }

  /**
   * Set callback for VAD events
   * @param callback Function called with (isSpeaking: boolean | null, audioLevel: number)
   *                 null = speech ended signal (trigger processing)
   */
  setVADCallback(callback: ((isSpeaking: boolean | null, audioLevel: number) => void) | null): void {
    this.vadCallback = callback;
  }

  /**
   * Get current speech chunks (audio collected for streaming)
   * Returns chunks since last call (for continuous streaming)
   */
  getSpeechChunks(): Blob[] {
    // Return chunks since last sent index
    const newChunks = this.speechChunks.slice(this.lastSentChunkIndex);
    return [...newChunks];
  }

  /**
   * Get all audio chunks (for streaming - gets recent chunks)
   */
  getAllChunks(): Blob[] {
    return [...this.audioChunks];
  }

  /**
   * Get chunks since a specific time (for streaming)
   */
  getChunksSince(timestamp: number): Blob[] {
    // For now, return all chunks (we'll optimize later)
    // In a real implementation, we'd track timestamps per chunk
    return [...this.audioChunks];
  }

  /**
   * Clear speech chunks (call after processing)
   * Actually just updates the sent index to mark chunks as sent
   */
  clearSpeechChunks(): void {
    // Update sent index instead of clearing (allows continuous streaming)
    this.lastSentChunkIndex = this.speechChunks.length;
    // Only clear if we have too many chunks (memory management)
    if (this.speechChunks.length > 200) {
      const chunksToKeep = this.speechChunks.slice(-100);
      this.speechChunks = chunksToKeep;
      this.lastSentChunkIndex = 0; // Reset index since we cleared old chunks
    }
  }

  /**
   * Stop VAD monitoring
   */
  private stopVAD(): void {
    this.isVADActive = false;
    if (this.vadInterval !== null) {
      clearTimeout(this.vadInterval);
      this.vadInterval = null;
    }
    
    // Disconnect audio nodes
    if (this.microphone) {
      try {
        this.microphone.disconnect();
      } catch (e) {
        // Ignore disconnect errors
      }
      this.microphone = null;
    }
    
    if (this.analyser) {
      try {
        this.analyser.disconnect();
      } catch (e) {
        // Ignore disconnect errors
      }
      this.analyser = null;
    }
    
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close().catch(e => console.warn('Error closing audio context:', e));
      this.audioContext = null;
    }
    
    this.vadCallback = null;
    console.log('VAD stopped');
  }
}

export const audioService = new AudioService();

