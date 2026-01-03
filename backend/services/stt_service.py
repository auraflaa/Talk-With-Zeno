"""
Speech-to-Text Service
Converts audio/voice input to text
Uses Groq Whisper models (primary) with Google STT as fallback
Supports chunk-wise processing for better accuracy
"""

import os
import io
from google.cloud import speech
from google.oauth2 import service_account
from typing import Optional, BinaryIO, List
import wave
import struct

# Try to import Groq SDK
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False
    Groq = None


class STTService:
    """STT service with Groq Whisper (primary) and Google STT (fallback)"""
    
    def __init__(self):
        self.groq_api_key = os.getenv('GROQ_API_KEY') or os.getenv('VITE_GROQ_API_KEY')
        self.groq_client = None
        self.google_client = None
        self.preferred_model = "whisper-large-v3-turbo"  # Faster option
        self.fallback_model = "whisper-large-v3"  # More accurate option
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize Groq and Google STT clients"""
        # Initialize Groq client (primary)
        if self.groq_api_key and GROQ_SDK_AVAILABLE:
            try:
                self.groq_client = Groq(api_key=self.groq_api_key)
                print("STT: Groq Whisper client initialized (primary)")
            except Exception as e:
                print(f"STT: Warning - Could not initialize Groq client: {e}")
                self.groq_client = None
        else:
            if not self.groq_api_key:
                print("STT: GROQ_API_KEY not set - Groq Whisper will not be available")
            if not GROQ_SDK_AVAILABLE:
                print("STT: Groq SDK not available - install with: pip install groq")
            self.groq_client = None
        
        # Initialize Google STT client (fallback)
        try:
            # Try to use service account credentials if available
            creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            # Also check config folder
            if not creds_path or not os.path.exists(creds_path):
                config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'service-account-key.json')
                if os.path.exists(config_path):
                    creds_path = config_path
            
            # Also check root
            if not creds_path or not os.path.exists(creds_path):
                root_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'service-account-key.json')
                if os.path.exists(root_path):
                    creds_path = root_path
            
            if creds_path and os.path.exists(creds_path):
                credentials = service_account.Credentials.from_service_account_file(creds_path)
                self.google_client = speech.SpeechClient(credentials=credentials)
            else:
                # Use default credentials (for local development)
                self.google_client = speech.SpeechClient()
            print("STT: Google Speech-to-Text client initialized (fallback)")
        except Exception as e:
            print(f"STT: Warning - Could not initialize Google STT client: {e}")
            print("STT: Google STT will not be available as fallback. Make sure GOOGLE_APPLICATION_CREDENTIALS is set or service-account-key.json exists in config/ or root.")
            self.google_client = None
    
    def _detect_wav_sample_rate(self, audio_data: bytes) -> Optional[int]:
        """
        Detect sample rate from WAV file header
        
        Args:
            audio_data: Raw WAV file bytes
            
        Returns:
            Sample rate in Hz or None if detection fails
        """
        try:
            if len(audio_data) < 44:  # WAV header is at least 44 bytes
                return None
            
            # Check for RIFF header
            if audio_data[0:4] != b'RIFF' or audio_data[8:12] != b'WAVE':
                return None
            
            # Find 'fmt ' chunk
            fmt_pos = audio_data.find(b'fmt ')
            if fmt_pos == -1:
                return None
            
            # Sample rate is at offset 24 from start of 'fmt ' chunk
            # Or at byte 24-27 in standard WAV header
            if fmt_pos + 24 < len(audio_data):
                sample_rate = struct.unpack('<I', audio_data[fmt_pos + 12:fmt_pos + 16])[0]
                return sample_rate
            
            return None
        except Exception as e:
            print(f"STT: Error detecting WAV sample rate: {e}")
            return None
    
    def _transcribe_with_groq(self, audio_data: bytes, language_code: str = "en-US") -> Optional[str]:
        """
        Transcribe audio using Groq Whisper models
        
        Args:
            audio_data: Raw audio bytes
            language_code: Language code (default: en-US)
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.groq_client:
            return None
        
        try:
            # Extract language code (e.g., "en-US" -> "en")
            lang = language_code.split('-')[0] if '-' in language_code else language_code
            
            # Try preferred model first (turbo for speed)
            models_to_try = [self.preferred_model, self.fallback_model]
            
            for model in models_to_try:
                try:
                    print(f"STT: Trying Groq Whisper model: {model} (language: {lang})")
                    
                    # Groq expects a file tuple: (filename, file_content)
                    # Determine file extension based on audio format/size
                    # For WebM/Opus, use m4a extension (Groq handles it)
                    # For WAV, use wav extension
                    file_extension = "m4a"  # Default for WebM/Opus
                    if len(audio_data) > 44 and audio_data[0:4] == b'RIFF':
                        file_extension = "wav"  # WAV file detected
                    
                    # Use Groq SDK for transcription
                    # Groq expects: file=(filename, file_content_bytes)
                    transcription = self.groq_client.audio.transcriptions.create(
                        file=(f"audio.{file_extension}", audio_data),
                        model=model,
                        temperature=0,
                        language=lang,
                        response_format="verbose_json",
                    )
                    
                    if hasattr(transcription, 'text') and transcription.text:
                        text = transcription.text.strip()
                        print(f"STT: Groq Whisper ({model}) transcription successful: '{text}'")
                        return text
                    else:
                        print(f"STT: Groq Whisper ({model}) returned empty transcription")
                        continue
                        
                except Exception as e:
                    error_str = str(e).lower()
                    # Check for rate limit errors
                    if 'rate limit' in error_str or '429' in error_str or 'quota' in error_str:
                        print(f"STT: Groq Whisper ({model}) rate limited: {e}")
                        # Try next model, then fallback to Google
                        continue
                    else:
                        print(f"STT: Groq Whisper ({model}) error: {e}")
                        # Try next model
                        continue
            
            print("STT: All Groq Whisper models failed, will try Google STT fallback")
            return None
            
        except Exception as e:
            print(f"STT: Groq Whisper transcription error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _transcribe_with_google(self, audio_data: bytes, language_code: str = "en-US", 
                                sample_rate: int = 16000, audio_format: str = "webm") -> Optional[str]:
        """
        Transcribe audio using Google Speech-to-Text (fallback)
        
        Args:
            audio_data: Raw audio bytes
            language_code: Language code (default: en-US)
            sample_rate: Audio sample rate in Hz (default: 16000, auto-detected for WAV)
            audio_format: Audio format ('webm', 'wav', 'linear16')
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.google_client:
            return None
        
        if not audio_data or len(audio_data) == 0:
            print("STT: Empty audio data - returning None (this is expected for noise detection)")
            return None
        
        # Very small audio chunks are likely noise/silence
        if len(audio_data) < 500:
            print(f"STT: Audio too small ({len(audio_data)} bytes) - likely noise/silence")
            return None
        
        try:
            # Auto-detect sample rate for WAV files
            detected_sample_rate = sample_rate
            if audio_format.lower() == 'wav':
                detected = self._detect_wav_sample_rate(audio_data)
                if detected:
                    detected_sample_rate = detected
                    print(f"STT: Detected WAV sample rate: {detected_sample_rate} Hz")
                else:
                    print(f"STT: Could not detect WAV sample rate, using provided: {sample_rate} Hz")
            
            # Try multiple encoding strategies for WebM/Opus
            encoding_strategies = []
            
            if audio_format.lower() in ['webm', 'opus']:
                # Strategy 1: Try WEBM_OPUS if available
                if hasattr(speech.RecognitionConfig.AudioEncoding, 'WEBM_OPUS'):
                    encoding_strategies.append({
                        'encoding': speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
                        'sample_rate': 48000,
                        'name': 'WEBM_OPUS'
                    })
                
                # Strategy 2: Try OGG_OPUS (similar format)
                if hasattr(speech.RecognitionConfig.AudioEncoding, 'OGG_OPUS'):
                    encoding_strategies.append({
                        'encoding': speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                        'sample_rate': 48000,
                        'name': 'OGG_OPUS'
                    })
                
                # Strategy 3: Let Google auto-detect (most reliable)
                encoding_strategies.append({
                    'encoding': speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                    'sample_rate': 48000,
                    'name': 'ENCODING_UNSPECIFIED (auto-detect)'
                })
            elif audio_format.lower() == 'wav':
                # Use LINEAR16 encoding with detected sample rate
                encoding_strategies.append({
                    'encoding': speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    'sample_rate': detected_sample_rate,
                    'name': f'LINEAR16 ({detected_sample_rate} Hz)'
                })
            else:
                # Default: auto-detect
                encoding_strategies.append({
                    'encoding': speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                    'sample_rate': detected_sample_rate,
                    'name': 'ENCODING_UNSPECIFIED'
                })
            
            # Try each encoding strategy until one works
            for strategy in encoding_strategies:
                try:
                    print(f"STT: Trying {strategy['name']} encoding (format: {audio_format}, size: {len(audio_data)} bytes)")
                    
                    config = speech.RecognitionConfig(
                        encoding=strategy['encoding'],
                        sample_rate_hertz=strategy['sample_rate'],
                        language_code=language_code,
                        enable_automatic_punctuation=True,
                        model='phone_call',  # Optimized for voice conversations (1747ms avg latency)
                    )
                    
                    audio = speech.RecognitionAudio(content=audio_data)
                    
                    # Perform transcription
                    response = self.google_client.recognize(config=config, audio=audio)
                    
                    # Extract transcript
                    if response.results and len(response.results) > 0:
                        if response.results[0].alternatives and len(response.results[0].alternatives) > 0:
                            transcript = response.results[0].alternatives[0].transcript
                            confidence = response.results[0].alternatives[0].confidence if hasattr(response.results[0].alternatives[0], 'confidence') else None
                            print(f"STT: Transcription successful with {strategy['name']}: '{transcript}' (confidence: {confidence})")
                            return transcript.strip()
                    
                    print(f"STT: {strategy['name']} returned no results (response.results length: {len(response.results) if response.results else 0}), trying next strategy...")
                except Exception as e:
                    error_str = str(e).lower()
                    if 'invalid argument' in error_str or 'unsupported' in error_str:
                        print(f"STT: {strategy['name']} not supported: {e}")
                        continue  # Try next strategy
                    else:
                        # For other errors, log and try next
                        print(f"STT: Error with {strategy['name']}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
            
            print("STT: All encoding strategies failed - no transcription results")
            return None
        except Exception as e:
            print(f"STT: Error transcribing audio: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def transcribe_audio(self, audio_data: bytes, language_code: str = "en-US",
                        audio_format: str = "webm") -> Optional[str]:
        """
        Transcribe audio data (public method)
        Uses parallel processing with both Google STT and Groq Whisper simultaneously
        to get the fastest result and reduce error chance. Returns first successful result.
        
        Args:
            audio_data: Raw audio bytes
            language_code: Language code (default: en-US)
            audio_format: Audio format - 'webm' or 'wav' (default: webm)
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.groq_client and not self.google_client:
            print("STT: No STT clients initialized")
            return None
        
        if not audio_data or len(audio_data) < 100:
            print(f"STT: Audio data too small ({len(audio_data)} bytes)")
            return None
        
        # Use parallel processing: call both STT services simultaneously
        # This prevents duplicates by ensuring only one result is returned
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        results = {}
        errors = {}
        lock = threading.Lock()
        
        def transcribe_google():
            """Transcribe using Google STT"""
            if not self.google_client:
                return None
            try:
                # Detect sample rate for WAV files
                sample_rate = 16000  # Default
                if audio_format.lower() == 'wav':
                    detected_rate = self._detect_wav_sample_rate(audio_data)
                    if detected_rate:
                        sample_rate = detected_rate
                
                result = self._transcribe_with_google(
                    audio_data,
                    language_code=language_code,
                    sample_rate=sample_rate,
                    audio_format=audio_format
                )
                if result and result.strip():
                    with lock:
                        results['google'] = result.strip()
                    return result.strip()
            except Exception as e:
                with lock:
                    errors['google'] = str(e)
                return None
        
        def transcribe_groq():
            """Transcribe using Groq Whisper"""
            if not self.groq_client:
                return None
            try:
                result = self._transcribe_with_groq(audio_data, language_code)
                if result and result.strip():
                    with lock:
                        results['groq'] = result.strip()
                    return result.strip()
            except Exception as e:
                with lock:
                    errors['groq'] = str(e)
                return None
        
        # Run both STT services in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            if self.google_client:
                futures['google'] = executor.submit(transcribe_google)
            if self.groq_client:
                futures['groq'] = executor.submit(transcribe_groq)
            
            # Wait for first successful result (prevents duplicates)
            for future in as_completed(futures.values()):
                provider = [k for k, v in futures.items() if v == future][0]
                try:
                    result = future.result()
                    if result and result.strip():
                        # Cancel other futures to prevent duplicate processing
                        for other_provider, other_future in futures.items():
                            if other_provider != provider:
                                other_future.cancel()
                        print(f"STT: {provider.capitalize()} transcription succeeded (parallel): '{result[:50]}...'")
                        return result.strip()
                except Exception as e:
                    print(f"STT: {provider.capitalize()} transcription exception: {e}")
        
        # If we get here, both failed
        if errors:
            print(f"STT: All transcription methods failed. Errors: {errors}")
        else:
            print("STT: All transcription methods returned empty/None")
        return None
    
    def transcribe_chunks(self, audio_chunks: List[bytes], language_code: str = "en-US",
                         audio_format: str = "webm") -> Optional[str]:
        """
        Transcribe audio by processing chunks and merging at sentence boundaries
        
        Args:
            audio_chunks: List of audio chunk bytes (each chunk should be 2-3 seconds)
            language_code: Language code
            audio_format: Audio format
            
        Returns:
            Merged transcribed text or None if failed
        """
        if not self.groq_client and not self.google_client:
            print("STT: No STT clients initialized")
            return None
        
        if not audio_chunks or len(audio_chunks) == 0:
            print("STT: No audio chunks provided")
            return None
        
        print(f"STT: Processing {len(audio_chunks)} audio chunks for chunk-wise transcription")
        
        all_transcripts = []
        
        # Process chunks in parallel for better performance (using ThreadPoolExecutor)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        successful_chunks = 0
        
        def process_chunk(i: int, chunk_data: bytes) -> tuple[int, Optional[str]]:
            """Process a single chunk and return (index, transcript)"""
            if not chunk_data or len(chunk_data) < 500:
                return (i, None)
            try:
                chunk_text = self.transcribe_audio(chunk_data, language_code, audio_format=audio_format)
                return (i, chunk_text.strip() if chunk_text else None)
            except Exception as e:
                print(f"STT: Error processing chunk {i+1}: {e}")
                return (i, None)
        
        # Process chunks in parallel (max 4 concurrent requests to avoid rate limits)
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_chunk = {
                executor.submit(process_chunk, i, chunk_data): i 
                for i, chunk_data in enumerate(audio_chunks)
            }
            
            # Collect results as they complete
            chunk_results = {}
            for future in as_completed(future_to_chunk):
                chunk_idx, transcript = future.result()
                if transcript:
                    chunk_results[chunk_idx] = transcript
                    successful_chunks += 1
                    print(f"STT: Chunk {chunk_idx+1} transcribed: '{transcript}'")
                else:
                    print(f"STT: Chunk {chunk_idx+1} returned no transcription (likely silence or noise)")
        
        # Sort transcripts by chunk index to maintain order
        all_transcripts = [chunk_results[i] for i in sorted(chunk_results.keys())]
        
        print(f"STT: Successfully transcribed {successful_chunks}/{len(audio_chunks)} chunks")
        
        if not all_transcripts:
            print("STT: No successful transcriptions from any chunk")
            return None
        
        # Merge transcripts at sentence boundaries
        merged_text = self._merge_transcripts(all_transcripts)
        print(f"STT: Merged transcription from {len(all_transcripts)} chunks: '{merged_text}'")
        
        return merged_text
    
    def _merge_transcripts(self, transcripts: List[str]) -> str:
        """
        Merge multiple transcript chunks at sentence boundaries
        
        Args:
            transcripts: List of transcript strings
            
        Returns:
            Merged transcript with proper sentence boundaries
        """
        import re
        
        if not transcripts:
            return ""
        
        # Join all transcripts
        combined = " ".join(transcripts)
        
        # Clean up: remove duplicate words/phrases at boundaries
        # Split by sentence boundaries
        sentences = re.split(r'([.!?]\s*)', combined)
        
        # Reconstruct, removing duplicates
        merged_sentences = []
        seen_sentences = set()
        
        for i in range(0, len(sentences), 2):
            if i < len(sentences):
                sentence = sentences[i].strip()
                punctuation = sentences[i+1] if i+1 < len(sentences) else ""
                
                # Normalize sentence for comparison (lowercase, no punctuation)
                normalized = re.sub(r'[.!?,\s]+', ' ', sentence.lower()).strip()
                
                # Skip if we've seen this sentence before (duplicate detection)
                if normalized and normalized not in seen_sentences:
                    seen_sentences.add(normalized)
                    merged_sentences.append(sentence + punctuation)
        
        result = " ".join(merged_sentences).strip()
        
        # Final cleanup: remove extra spaces
        result = re.sub(r'\s+', ' ', result)
        
        return result
    
    def transcribe_stream(self, audio_stream: BinaryIO, language_code: str = "en-US",
                         sample_rate: int = 16000) -> Optional[str]:
        """
        Transcribe audio from stream
        
        Args:
            audio_stream: Audio file-like object
            language_code: Language code
            sample_rate: Audio sample rate
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.client:
            return None
        
        try:
            audio_data = audio_stream.read()
            return self.transcribe_audio(audio_data, language_code, sample_rate)
        except Exception as e:
            print(f"Error transcribing stream: {e}")
            return None


# Singleton instance
_stt_service: Optional[STTService] = None


def get_stt_service() -> STTService:
    """Get STT service instance (singleton)"""
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service
