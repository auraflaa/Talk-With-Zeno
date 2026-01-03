"""
Google Speech-to-Text Service
Converts audio/voice input to text
Supports chunk-wise processing for better accuracy
"""

import os
import io
from google.cloud import speech
from google.oauth2 import service_account
from typing import Optional, BinaryIO, List
import wave
import struct


class STTService:
    """Google Speech-to-Text service"""
    
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Speech-to-Text client"""
        try:
            # Try to use service account credentials if available
            creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if creds_path and os.path.exists(creds_path):
                credentials = service_account.Credentials.from_service_account_file(creds_path)
                self.client = speech.SpeechClient(credentials=credentials)
            else:
                # Use default credentials (for local development)
                self.client = speech.SpeechClient()
            print("STT: Google Speech-to-Text client initialized")
        except Exception as e:
            print(f"Warning: Could not initialize STT client: {e}")
            print("STT will not be available. Make sure GOOGLE_APPLICATION_CREDENTIALS is set.")
    
    def transcribe_audio(self, audio_data: bytes, language_code: str = "en-US", 
                        sample_rate: int = 16000, audio_format: str = "webm") -> Optional[str]:
        """
        Transcribe audio data to text
        
        Args:
            audio_data: Raw audio bytes
            language_code: Language code (default: en-US)
            sample_rate: Audio sample rate in Hz (default: 16000)
            audio_format: Audio format ('webm', 'wav', 'linear16')
            
        Returns:
            Transcribed text or None if failed
        """
        if not self.client:
            print("STT: Client not initialized")
            return None
        
        if not audio_data or len(audio_data) == 0:
            print("STT: Empty audio data")
            return None
        
        try:
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
                encoding_strategies.append({
                    'encoding': speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    'sample_rate': sample_rate,
                    'name': 'LINEAR16'
                })
            else:
                # Default: auto-detect
                encoding_strategies.append({
                    'encoding': speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
                    'sample_rate': sample_rate,
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
                        model='latest_long',  # Use latest model for better accuracy
                    )
                    
                    audio = speech.RecognitionAudio(content=audio_data)
                    
                    # Perform transcription
                    response = self.client.recognize(config=config, audio=audio)
                    
                    # Extract transcript
                    if response.results and len(response.results) > 0:
                        if response.results[0].alternatives and len(response.results[0].alternatives) > 0:
                            transcript = response.results[0].alternatives[0].transcript
                            print(f"STT: Transcription successful with {strategy['name']}: {transcript}")
                            return transcript.strip()
                    
                    print(f"STT: {strategy['name']} returned no results, trying next strategy...")
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
        if not self.client:
            print("STT: Client not initialized")
            return None
        
        if not audio_chunks or len(audio_chunks) == 0:
            print("STT: No audio chunks provided")
            return None
        
        print(f"STT: Processing {len(audio_chunks)} audio chunks for chunk-wise transcription")
        
        all_transcripts = []
        
        # Process each chunk
        successful_chunks = 0
        for i, chunk_data in enumerate(audio_chunks):
            if not chunk_data or len(chunk_data) < 500:  # Skip very small chunks
                print(f"STT: Skipping chunk {i+1} - too small ({len(chunk_data)} bytes)")
                continue
            
            print(f"STT: Processing chunk {i+1}/{len(audio_chunks)} (size: {len(chunk_data)} bytes)")
            try:
                chunk_text = self.transcribe_audio(chunk_data, language_code, audio_format=audio_format)
                
                if chunk_text and chunk_text.strip():
                    print(f"STT: Chunk {i+1} transcribed: '{chunk_text}'")
                    all_transcripts.append(chunk_text.strip())
                    successful_chunks += 1
                else:
                    print(f"STT: Chunk {i+1} returned no transcription (likely silence or noise)")
            except Exception as e:
                print(f"STT: Error processing chunk {i+1}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
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
