/**
 * Audio Recording and Playback Service
 */

export class AudioService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private currentAudio: HTMLAudioElement | null = null;

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

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
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
    
    // Stop MediaRecorder if it exists and is still recording
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      try {
        console.log(`Stopping MediaRecorder in cleanup (state: ${this.mediaRecorder.state})`);
        this.mediaRecorder.stop();
      } catch (e) {
        console.warn('Error stopping MediaRecorder in cleanup:', e);
      }
    }
    
    // Stop all tracks in the stream
    if (this.stream) {
      this.stream.getTracks().forEach(track => {
        try {
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
    console.log('Audio service cleanup complete');
  }
  
  // Force stop method for emergency cleanup
  forceStop(): void {
    console.log('FORCE STOP: Emergency cleanup of audio service');
    this.cleanup();
  }

  async playAudio(audioBlob: Blob): Promise<void> {
    return new Promise((resolve, reject) => {
      // Stop any currently playing audio
      this.stopAudio();
      
      const audio = new Audio();
      const url = URL.createObjectURL(audioBlob);
      this.currentAudio = audio;

      audio.onended = () => {
        console.log('Audio playback ended');
        URL.revokeObjectURL(url);
        this.currentAudio = null;
        resolve();
      };

      audio.onerror = (error) => {
        console.error('Audio playback error:', error, audio.error);
        URL.revokeObjectURL(url);
        this.currentAudio = null;
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
            URL.revokeObjectURL(url);
            this.currentAudio = null;
            reject(error);
          });
      }
    });
  }

  stopAudio(): void {
    if (this.currentAudio) {
      try {
        console.log('Stopping current audio playback');
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        // Clean up the audio element
        this.currentAudio.src = '';
        this.currentAudio = null;
      } catch (error) {
        console.error('Error stopping audio:', error);
        this.currentAudio = null;
      }
    }
  }

  isPlaying(): boolean {
    return this.currentAudio !== null && !this.currentAudio.paused && !this.currentAudio.ended;
  }

  isRecording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }
}

export const audioService = new AudioService();

