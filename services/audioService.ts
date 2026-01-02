/**
 * Audio Recording and Playback Service
 */

export class AudioService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;

  async startRecording(): Promise<void> {
    try {
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
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
          console.log(`Audio chunk received: ${event.data.size} bytes`);
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

      this.mediaRecorder.start(100); // Collect data every 100ms
      console.log('MediaRecorder started successfully');
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

      if (this.mediaRecorder.state === 'inactive') {
        reject(new Error('Recording already stopped'));
        return;
      }

      const timeout = setTimeout(() => {
        reject(new Error('Recording stop timeout'));
      }, 5000);

      this.mediaRecorder.onstop = () => {
        clearTimeout(timeout);
        const totalSize = this.audioChunks.reduce((sum, chunk) => sum + chunk.size, 0);
        console.log(`Recording stopped. Total audio chunks: ${this.audioChunks.length}, Total size: ${totalSize} bytes`);
        
        if (this.audioChunks.length === 0) {
          this.cleanup();
          reject(new Error('No audio data recorded'));
          return;
        }

        // Determine blob type from the first chunk or use webm as default
        const blobType = this.audioChunks[0].type || 'audio/webm';
        const audioBlob = new Blob(this.audioChunks, { type: blobType });
        console.log(`Created audio blob: ${audioBlob.size} bytes, type: ${audioBlob.type}`);
        
        this.cleanup();
        resolve(audioBlob);
      };

      this.mediaRecorder.onerror = (event: any) => {
        clearTimeout(timeout);
        console.error('Error stopping recording:', event);
        reject(new Error('Error stopping recording'));
      };

      try {
        this.mediaRecorder.stop();
      } catch (error) {
        clearTimeout(timeout);
        reject(new Error(`Failed to stop recording: ${error}`));
      }
    });
  }

  private cleanup(): void {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.audioChunks = [];
  }

  async playAudio(audioBlob: Blob): Promise<void> {
    return new Promise((resolve, reject) => {
      const audio = new Audio();
      const url = URL.createObjectURL(audioBlob);

      audio.onended = () => {
        console.log('Audio playback ended');
        URL.revokeObjectURL(url);
        resolve();
      };

      audio.onerror = (error) => {
        console.error('Audio playback error:', error, audio.error);
        URL.revokeObjectURL(url);
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
            reject(error);
          });
      }
    });
  }

  isRecording(): boolean {
    return this.mediaRecorder?.state === 'recording';
  }
}

export const audioService = new AudioService();

