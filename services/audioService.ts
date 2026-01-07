/**
 * Audio Recording and Playback Service
 */

import { logWithTimestamp, warnWithTimestamp, errorWithTimestamp } from '../utils/logger';

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
  
  // VAD thresholds - optimized for better accuracy and preventing premature speech end detection
  // These work in conjunction with backend VAD (silero-vad) for highest accuracy
  private readonly VAD_THRESHOLD = 25; // Volume threshold (0-255) - lowered for better sensitivity
  private readonly SILENCE_DURATION = 500; // ms of silence to detect speech end (reduced from 800ms for faster response)
  private readonly MIN_SPEECH_DURATION = 200; // ms minimum speech duration (reduced from 300ms for faster response, still filters noise)
  
  // Advanced VAD parameters for better accuracy
  private readonly RMS_THRESHOLD = 12; // RMS threshold for time domain (lowered for better sensitivity)
  private readonly FREQUENCY_THRESHOLD = 20; // Frequency domain threshold
  
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
            logWithTimestamp(`Audio chunk received: ${event.data.size} bytes (total chunks: ${this.audioChunks.length}, total size: ${totalSize} bytes)`);
          }
        } else {
          console.warn('Received empty audio chunk');
        }
      };

      this.mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event);
      };

      this.mediaRecorder.onstart = () => {
        logWithTimestamp('Recording started');
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
      }, 500); // Reduced timeout to 500ms for faster response

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
      // Only stop currently playing audio if it's not the greeting (allow greeting to play)
      // For now, always stop previous audio to prevent overlap
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
        console.log('Audio playback ended - audio finished playing completely');
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
        // Ensure audio is loaded before playing
        if (audio.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA) {
          console.log('Audio has enough data to play');
        }
      };
      
      // Set volume to ensure audio is audible (max volume)
      audio.volume = 1.0;
      
      // CRITICAL: Ensure audio is not muted
      audio.muted = false;
      
      // CRITICAL: Pause and reset audio BEFORE setting src to prevent auto-play
      audio.pause();
      audio.currentTime = 0;
      
      // CRITICAL: Prevent autoplay by setting preload
      audio.preload = 'auto';
      
      audio.src = url;
      // Load the audio first to ensure it's ready
      audio.load();
      
      // CRITICAL: Immediately pause after load to prevent any auto-play
      setTimeout(() => {
        audio.pause();
        audio.currentTime = 0;
      }, 0);
      
      // CRITICAL: Ensure audio is paused and reset after metadata is loaded
      // This prevents the browser from auto-playing or starting from wrong position
      audio.addEventListener('loadedmetadata', () => {
        audio.pause(); // Ensure it's paused
        audio.currentTime = 0; // Reset to beginning
        console.log('Audio metadata loaded, paused and reset to 0 (duration:', audio.duration, ')');
      }, { once: true });
      
      console.log('Audio element created:', {
        volume: audio.volume,
        muted: audio.muted,
        src: url.substring(0, 50) + '...',
        blobSize: audioBlob.size
      });
      
            // CRITICAL: Wait for ENTIRE audio file to be buffered before playing
            // This prevents the beginning from being cut off
            const playWhenReady = () => {
                return new Promise((resolve, reject) => {
                    const timeout = setTimeout(() => {
                        reject(new Error('Audio load timeout'));
                    }, 10000); // Increased to 10s for large files
                    
                    // Check if entire file is buffered
                    const checkFullyBuffered = () => {
                        if (audio.buffered.length > 0) {
                            const bufferedEnd = audio.buffered.end(audio.buffered.length - 1);
                            const duration = audio.duration;
                            
                            // Check if entire file is buffered (within 0.1s tolerance)
                            if (duration && duration > 0 && !isNaN(duration)) {
                                // For small files (< 5s), just check readyState
                                // For larger files, check if entire file is buffered
                                const isSmallFile = duration < 5.0;
                                const isFullyBuffered = isSmallFile 
                                    ? (audio.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA)
                                    : (bufferedEnd >= duration - 0.1);
                                
                                if (isFullyBuffered || audio.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA) {
                                    // ENTIRE file is buffered - safe to play from beginning
                                    clearTimeout(timeout);
                                    // CRITICAL: Pause, reset to 0, then play to ensure we start from beginning
                                    audio.pause();
                                    audio.currentTime = 0;
                                    // Small delay to ensure currentTime is set and audio is paused before playing
                                    setTimeout(() => {
                                        // Double-check currentTime is 0 before playing
                                        if (audio.currentTime > 0.1) {
                                            audio.currentTime = 0;
                                        }
                                        console.log('Audio fully buffered, starting from beginning (buffered:', bufferedEnd.toFixed(2), 's, duration:', duration.toFixed(2), 's, currentTime:', audio.currentTime, ')');
                                        resolve(audio.play());
                                    }, 50); // 50ms delay to ensure currentTime is set and audio is paused
                                    return true;
                                }
                            }
                        }
                        return false;
                    };
                    
                    // Wait for loadedmetadata first (to know duration)
                    const onLoadedMetadata = () => {
                        console.log('Audio metadata loaded (duration:', audio.duration, 's)');
                        // CRITICAL: Pause and reset to 0 after metadata is loaded
                        // This ensures audio doesn't auto-play and starts from beginning
                        audio.pause();
                        audio.currentTime = 0;
                        
                        // Now wait for entire file to be buffered
                        const onProgress = () => {
                            if (checkFullyBuffered()) {
                                audio.removeEventListener('progress', onProgress);
                                audio.removeEventListener('canplaythrough', onCanPlayThrough);
                            }
                        };
                        
                        const onCanPlayThrough = () => {
                            // canplaythrough means enough is buffered, but check if ALL is buffered
                            if (checkFullyBuffered()) {
                                audio.removeEventListener('progress', onProgress);
                                audio.removeEventListener('canplaythrough', onCanPlayThrough);
                            }
                        };
                        
                        // Listen for progress to track buffering
                        audio.addEventListener('progress', onProgress);
                        audio.addEventListener('canplaythrough', onCanPlayThrough, { once: true });
                        
                        // Also check immediately in case it's already fully buffered
                        if (checkFullyBuffered()) {
                            audio.removeEventListener('progress', onProgress);
                            audio.removeEventListener('canplaythrough', onCanPlayThrough);
                        }
                    };
                    
                    if (audio.duration && audio.duration > 0 && !isNaN(audio.duration)) {
                        // Duration already known
                        onLoadedMetadata();
                    } else {
                        // Wait for metadata
                        audio.addEventListener('loadedmetadata', onLoadedMetadata, { once: true });
                    }
                    
                    audio.addEventListener('error', () => {
                        clearTimeout(timeout);
                        reject(new Error('Audio load error'));
                    }, { once: true });
                });
            };
      
      const playPromise = playWhenReady();
      
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            console.log('Audio play() succeeded - audio is now playing, waiting for onended event...');
            console.log('Audio playback state:', {
              paused: audio.paused,
              ended: audio.ended,
              currentTime: audio.currentTime,
              duration: audio.duration,
              volume: audio.volume,
              muted: audio.muted,
              readyState: audio.readyState
            });
            // Don't resolve here - wait for onended event to ensure audio plays completely
            // The promise will resolve when audio.onended fires
          })
          .catch((error) => {
            // Ignore AbortError - it's expected if audio is interrupted
            if (error.name === 'AbortError') {
              console.log('Audio play() interrupted (expected) - audio was stopped before playing');
              cleanup();
              resolve(); // Resolve instead of reject for AbortError
            } else {
              console.error('Audio play() failed:', error);
              cleanup();
              reject(error);
            }
          });
      } else {
        // Fallback for browsers that don't return promise
        console.log('Audio play() returned undefined, using fallback check');
        setTimeout(() => {
          if (audio.error) {
            console.error('Audio error detected in fallback:', audio.error);
            cleanup();
            reject(new Error(`Failed to play audio: ${audio.error.message}`));
          } else {
            console.log('Audio fallback: No error detected, audio may be playing');
            // Don't resolve here - still wait for onended event
          }
        }, 1000);
      }
    });
  }

  stopAudio(): void {
    if (this.currentAudio) {
      try {
        console.log('Stopping current audio playback');
        // Don't pause if already paused/ended to avoid AbortError
        if (!this.currentAudio.paused) {
          this.currentAudio.pause();
        }
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
    if (!this.currentAudio) return false;
    // Check if audio is actually playing (not paused, not ended, and has started)
    return !this.currentAudio.paused && 
           !this.currentAudio.ended && 
           this.currentAudio.currentTime > 0 &&
           this.currentAudio.readyState >= 2; // HAVE_CURRENT_DATA or higher
  }

  isRecording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }

  getVADActive(): boolean {
    return this.isVADActive;
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
      
      logWithTimestamp('VAD started - monitoring for speech activity');
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
    
    // Enhanced VAD calculation - improved accuracy
    // Frequency domain analysis
    let sum = 0;
    let maxFreq = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
      if (dataArray[i] > maxFreq) {
        maxFreq = dataArray[i];
      }
    }
    const averageVolume = sum / dataArray.length;
    
    // Time domain analysis (RMS)
    const timeData = new Uint8Array(this.analyser.fftSize);
    this.analyser.getByteTimeDomainData(timeData);
    
    // Calculate RMS (Root Mean Square) for time domain
    let rms = 0;
    let zeroCrossings = 0;
    for (let i = 0; i < timeData.length; i++) {
      const normalized = (timeData[i] - 128) / 128;
      rms += normalized * normalized;
      
      // Count zero crossings (speech has more zero crossings than noise)
      if (i > 0) {
        const prevNormalized = (timeData[i - 1] - 128) / 128;
        if ((normalized >= 0 && prevNormalized < 0) || (normalized < 0 && prevNormalized >= 0)) {
          zeroCrossings++;
        }
      }
    }
    rms = Math.sqrt(rms / timeData.length) * 100;
    
    // Zero crossing rate (speech typically has higher ZCR than noise)
    const zcr = (zeroCrossings / timeData.length) * 100;
    
    // Enhanced combined threshold check:
    // 1. Frequency domain: average volume OR peak frequency
    // 2. Time domain: RMS energy
    // 3. Zero crossing rate (speech indicator)
    const freqCheck = averageVolume > this.VAD_THRESHOLD || maxFreq > this.FREQUENCY_THRESHOLD;
    const timeCheck = rms > this.RMS_THRESHOLD;
    const zcrCheck = zcr > 5 && zcr < 50; // Speech has moderate ZCR, noise has very low or very high
    
    // Combined decision: at least 2 out of 3 indicators must be positive
    const indicators = [freqCheck, timeCheck, zcrCheck].filter(Boolean).length;
    const isSpeaking = indicators >= 2;
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
        logWithTimestamp('VAD: Speech detected, continuing to collect audio');
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
            logWithTimestamp(`VAD: Speech ended (duration: ${speechDuration}ms), ready to process`);
            // Mark speech as ended (but keep speechStartTime set so hasDetectedSpeech() works)
            // speechStartTime will be reset in clearSpeechChunks() after processing
            this.isCurrentlySpeaking = false;
            // DON'T reset speechStartTime here - keep it so hasDetectedSpeech() returns true
            
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
      } else {
        // CRITICAL FIX: If we're not currently speaking but have accumulated chunks,
        // check if we should force speech start detection (fallback for missed speech start)
        // This handles the case where VAD missed speech start after TTS
        if (this.audioChunks.length > 0 && this.speechStartTime === 0) {
          // We have chunks but speechStartTime is 0 - VAD missed speech start
          // Check if we have substantial audio that suggests speech is happening
          const totalSize = this.audioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
          const estimatedDurationMs = (totalSize / 8000) * 1000; // ~8KB per second
          const timeSinceLastSpeech = now - (this.lastSpeechTime || now);
          
          // If we have significant audio (>2 seconds) and silence for >1 second,
          // force speech start detection retroactively (VAD missed the start)
          if (estimatedDurationMs > 2000 && timeSinceLastSpeech > 1000) {
            // Force speech start detection retroactively
            this.isCurrentlySpeaking = true;
            this.speechStartTime = now - estimatedDurationMs; // Set start time retroactively
            this.lastSpeechTime = now;
            logWithTimestamp(`VAD: Forcing speech start detection (missed start, ${estimatedDurationMs.toFixed(0)}ms audio accumulated)`);
            
            // Now trigger speech end immediately since we have enough silence
            if (timeSinceLastSpeech > this.SILENCE_DURATION) {
              const speechDuration = this.lastSpeechTime - this.speechStartTime;
              if (speechDuration >= this.MIN_SPEECH_DURATION) {
                this.isCurrentlySpeaking = false;
                // DON'T reset speechStartTime here - keep it so hasDetectedSpeech() works
                
                logWithTimestamp(`VAD: Speech ended (forced, duration: ${speechDuration}ms), ready to process`);
                
                // Trigger callback with special signal: null = speech ended (trigger processing)
                if (this.vadCallback) {
                  this.vadCallback(null, audioLevel); // null = speech ended signal
                }
                return;
              }
            }
          }
        }
      }
    }
    
    // Call callback with current state (normal updates)
    if (this.vadCallback) {
      this.vadCallback(isSpeaking, audioLevel);
    }
    
    // Continue monitoring with adaptive interval
    // Faster checking when speech is detected for more responsive detection
    if (this.isVADActive) {
      const interval = isSpeaking ? 50 : 100; // Check every 50ms during speech, 100ms during silence
      this.vadInterval = window.setTimeout(() => this.monitorVAD(), interval);
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
   * Request a complete chunk from MediaRecorder using requestData()
   * This creates a complete WebM chunk instead of fragments
   * Returns a Promise that resolves with the complete chunk blob
   */
  async requestCompleteChunk(): Promise<Blob | null> {
    if (!this.mediaRecorder || this.mediaRecorder.state !== 'recording') {
      console.warn('MediaRecorder not recording, cannot request complete chunk');
      return null;
    }

    return new Promise((resolve) => {
      // Set up a one-time listener for the complete chunk
      const onDataAvailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          // Remove the listener after receiving data
          this.mediaRecorder!.removeEventListener('dataavailable', onDataAvailable);
          console.log(`Requested complete chunk received: ${event.data.size} bytes`);
          resolve(event.data);
        } else {
          // Empty chunk - try again or resolve with null
          this.mediaRecorder!.removeEventListener('dataavailable', onDataAvailable);
          console.warn('Requested complete chunk is empty');
          resolve(null);
        }
      };

      // Add listener
      this.mediaRecorder.addEventListener('dataavailable', onDataAvailable);

      // Request data - this forces MediaRecorder to create a complete chunk
      try {
        this.mediaRecorder.requestData();
        // Set timeout in case requestData doesn't trigger event
        setTimeout(() => {
          this.mediaRecorder?.removeEventListener('dataavailable', onDataAvailable);
          if (this.audioChunks.length > 0) {
            // Fallback: use accumulated chunks if requestData doesn't work
            const blobType = this.audioChunks[0]?.type || 'audio/webm';
            const fallbackBlob = new Blob(this.audioChunks, { type: blobType });
            console.warn(`requestData timeout, using accumulated chunks: ${fallbackBlob.size} bytes`);
            resolve(fallbackBlob);
          } else {
            resolve(null);
          }
        }, 500); // 500ms timeout
      } catch (error) {
        this.mediaRecorder.removeEventListener('dataavailable', onDataAvailable);
        console.error('Error requesting complete chunk:', error);
        resolve(null);
      }
    });
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
    // CRITICAL: After an utterance is processed, clear ALL chunks to start fresh
    // This prevents accumulation of old chunks that can confuse VAD
    const oldLength = this.speechChunks.length;
    this.speechChunks = [];
    this.lastSentChunkIndex = 0;
    this.audioChunks = []; // Also clear raw audio chunks
    // Reset speech detection state after processing is complete
    this.speechStartTime = 0;
    this.isCurrentlySpeaking = false;
    console.log(`AudioService: Cleared all speech chunks (${oldLength} → 0) for fresh start`);
  }

  /**
   * Reset VAD state (call after TTS playback to allow immediate new speech detection)
   */
  resetVADState(): void {
    const wasSpeaking = this.isCurrentlySpeaking;
    this.isCurrentlySpeaking = false;
    // DON'T reset speechStartTime here - it should only be reset in clearSpeechChunks()
    // This ensures hasDetectedSpeech() works correctly
    this.lastSpeechTime = Date.now(); // Reset to current time so silence detection starts fresh
    
    // CRITICAL: After TTS, temporarily lower VAD thresholds to be more sensitive
    // This helps detect speech start that might be missed due to TTS audio interference
    // The thresholds will naturally adjust back as speech is detected
    console.log(`VAD state reset - ready for new speech detection (wasSpeaking: ${wasSpeaking})`);
    
    // Note: VAD thresholds are already set to reasonable values
    // The issue is that VAD might not be detecting speech immediately after TTS
    // The fallback mechanism will handle this if VAD misses speech start
  }
  
  /**
   * Check if speech was ever detected (for fallback logic)
   */
  hasDetectedSpeech(): boolean {
    // If speechStartTime was set, speech was detected at some point
    return this.speechStartTime > 0;
  }

  /**
   * Force speech end detection (fallback when VAD misses speech end)
   * This is called when chunks accumulate but VAD hasn't detected speech end
   * CRITICAL: Only processes if speech was actually detected (not just noise)
   */
  forceSpeechEnd(): boolean {
    if (this.speechChunks.length === 0) {
      return false; // No chunks to process
    }
    
    // CRITICAL: Only process if speech was actually detected
    // If speechStartTime is 0, VAD never detected speech, so this is likely noise
    if (!this.hasDetectedSpeech()) {
      console.log('VAD: Force speech end skipped - no speech was ever detected (likely noise)');
      return false;
    }
    
    // Check if we have significant audio (at least 2 seconds worth)
    const totalSize = this.speechChunks.reduce((sum, chunk) => sum + chunk.size, 0);
    const estimatedDurationMs = (totalSize / 8000) * 1000; // ~8KB per second for WebM/Opus
    
    if (estimatedDurationMs < 2000) {
      return false; // Not enough audio yet
    }
    
    console.log(`VAD: Force speech end detection (fallback triggered) - ${estimatedDurationMs.toFixed(0)}ms of audio, isCurrentlySpeaking: ${this.isCurrentlySpeaking}`);
    
    // Mark speech as ended (but keep speechStartTime set so hasDetectedSpeech() works)
    // speechStartTime will be reset in clearSpeechChunks() after processing
    this.isCurrentlySpeaking = false;
    // DON'T reset speechStartTime here - keep it so hasDetectedSpeech() returns true
    
    // Trigger callback with speech ended signal
    if (this.vadCallback) {
      this.vadCallback(null, 0); // null = speech ended signal
      return true;
    }
    return false;
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
    
    console.log('VAD stopped');
  }
}

export const audioService = new AudioService();

