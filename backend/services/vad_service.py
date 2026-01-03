"""
Voice Activity Detection Service
Uses silero-vad (ML-based, highest accuracy) with webrtcvad fallback
Can be used to filter audio chunks before sending to STT
"""

import os
import struct
from typing import Optional, Tuple

# Try to import numpy (required for silero-vad)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

# Try to import silero-vad (primary - highest accuracy)
try:
    import torch
    from silero_vad import load_silero_vad
    SILERO_VAD_AVAILABLE = True
except ImportError:
    SILERO_VAD_AVAILABLE = False
    torch = None
    load_silero_vad = None

# Try to import webrtcvad (fallback - faster but less accurate)
try:
    import webrtcvad
    WEBRTCVAD_AVAILABLE = True
except ImportError:
    WEBRTCVAD_AVAILABLE = False
    webrtcvad = None


class VADService:
    """Voice Activity Detection service using silero-vad (primary) or webrtcvad (fallback)"""
    
    def __init__(self, aggressiveness: int = 2, use_silero: bool = True):
        """
        Initialize VAD service
        
        Args:
            aggressiveness: 0 (least aggressive) to 3 (most aggressive) - for webrtcvad only
            use_silero: Use silero-vad if available (highest accuracy), otherwise fallback to webrtcvad
        """
        self.aggressiveness = aggressiveness
        self.use_silero = use_silero
        self.silero_model = None
        self.silero_utils = None
        self.webrtc_vad = None
        
        # Try silero-vad first (highest accuracy)
        if use_silero and SILERO_VAD_AVAILABLE:
            try:
                self.silero_model, self.silero_utils = load_silero_vad()
                print("VAD: silero-vad initialized (highest accuracy, ML-based)")
            except Exception as e:
                print(f"VAD: Warning - Could not initialize silero-vad: {e}")
                self.silero_model = None
                self.silero_utils = None
        
        # Fallback to webrtcvad
        if not self.silero_model and WEBRTCVAD_AVAILABLE:
            try:
                self.webrtc_vad = webrtcvad.Vad(aggressiveness)
                print(f"VAD: webrtcvad initialized with aggressiveness {aggressiveness} (fallback)")
            except Exception as e:
                print(f"VAD: Warning - Could not initialize webrtcvad: {e}")
                self.webrtc_vad = None
        
        if not self.silero_model and not self.webrtc_vad:
            print("VAD: No VAD library available. Install with:")
            print("  pip install silero-vad torch  # For highest accuracy")
            print("  OR")
            print("  pip install webrtcvad  # For faster, lighter option")
            print("VAD: Falling back to simple energy-based detection")
    
    def is_speech(self, audio_data: bytes, sample_rate: int = 16000) -> bool:
        """
        Detect if audio contains speech using silero-vad (primary) or webrtcvad (fallback)
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit, mono)
            sample_rate: Sample rate in Hz (silero-vad supports any, webrtcvad: 8000, 16000, 32000, 48000)
            
        Returns:
            True if speech detected, False if noise/silence
        """
        if not audio_data or len(audio_data) < 2:
            return False
        
        # Try silero-vad first (highest accuracy)
        if self.silero_model and self.silero_utils:
            try:
                return self._is_speech_silero(audio_data, sample_rate)
            except Exception as e:
                print(f"VAD: silero-vad error: {e}, falling back to webrtcvad")
        
        # Fallback to webrtcvad
        if self.webrtc_vad:
            try:
                return self._is_speech_webrtc(audio_data, sample_rate)
            except Exception as e:
                print(f"VAD: webrtcvad error: {e}, falling back to simple detection")
        
        # Final fallback to simple energy-based detection
        return self._simple_energy_detection(audio_data)
    
    def _is_speech_silero(self, audio_data: bytes, sample_rate: int = 16000) -> bool:
        """
        Detect speech using silero-vad (ML-based, highest accuracy)
        
        Args:
            audio_data: Raw PCM audio bytes
            sample_rate: Sample rate in Hz
            
        Returns:
            True if speech detected
        """
        # Convert bytes to numpy array (16-bit PCM)
        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        
        # Normalize to [-1, 1] range
        samples = samples / 32768.0
        
        # Resample if needed (silero-vad works best with 16kHz, but handles others)
        if sample_rate != 16000:
            # Simple resampling (for production, use librosa or scipy)
            # For now, assume it's close enough or already 16kHz
            pass
        
        # Convert to tensor
        audio_tensor = torch.from_numpy(samples).unsqueeze(0)
        
        # Get speech probabilities
        speech_prob = self.silero_model(audio_tensor, sample_rate).item()
        
        # Threshold: consider it speech if probability > 0.5
        return speech_prob > 0.5
    
    def _is_speech_webrtc(self, audio_data: bytes, sample_rate: int = 16000) -> bool:
        """
        Detect speech using webrtcvad (faster, less accurate)
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit, mono)
            sample_rate: Sample rate in Hz (must be 8000, 16000, 32000, or 48000)
            
        Returns:
            True if speech detected
        """
        # webrtcvad requires specific frame sizes based on sample rate
        # Frame must be 10ms, 20ms, or 30ms
        frame_duration_ms = 30  # 30ms frames for better accuracy
        frame_size = int(sample_rate * frame_duration_ms / 1000) * 2  # *2 for 16-bit samples
        
        if len(audio_data) < frame_size:
            # Too short, use simple detection
            return self._simple_energy_detection(audio_data)
        
        # Process in frames
        num_frames = len(audio_data) // frame_size
        speech_frames = 0
        
        for i in range(num_frames):
            frame_start = i * frame_size
            frame_end = frame_start + frame_size
            frame = audio_data[frame_start:frame_end]
            
            try:
                if self.webrtc_vad.is_speech(frame, sample_rate):
                    speech_frames += 1
            except Exception:
                # If frame processing fails, skip it
                continue
        
        # Consider it speech if more than 30% of frames contain speech
        speech_ratio = speech_frames / num_frames if num_frames > 0 else 0
        return speech_ratio > 0.3
    
    def _simple_energy_detection(self, audio_data: bytes) -> bool:
        """
        Simple energy-based voice detection (fallback)
        
        Args:
            audio_data: Raw PCM audio bytes
            
        Returns:
            True if likely speech, False if likely noise/silence
        """
        if len(audio_data) < 2:
            return False
        
        # Convert bytes to 16-bit integers
        samples = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
        
        # Calculate RMS (Root Mean Square) energy
        sum_squares = sum(s * s for s in samples)
        rms = (sum_squares / len(samples)) ** 0.5
        
        # Normalize to 0-1 range (16-bit audio max is 32768)
        normalized_rms = rms / 32768.0
        
        # Threshold: consider it speech if RMS > 0.01 (1% of max)
        return normalized_rms > 0.01
    
    def filter_speech_chunks(self, audio_chunks: list, sample_rate: int = 16000) -> list:
        """
        Filter audio chunks to keep only those containing speech
        
        Args:
            audio_chunks: List of audio chunk bytes
            sample_rate: Sample rate in Hz
            
        Returns:
            List of audio chunks that contain speech
        """
        if not self.silero_model and not self.webrtc_vad:
            # Without VAD, return all chunks (let STT handle filtering)
            return audio_chunks
        
        speech_chunks = []
        for chunk in audio_chunks:
            if self.is_speech(chunk, sample_rate):
                speech_chunks.append(chunk)
        
        return speech_chunks
    
    def detect_speech_segments(self, audio_data: bytes, sample_rate: int = 16000,
                              frame_duration_ms: int = 30) -> list:
        """
        Detect speech segments in audio
        
        Args:
            audio_data: Raw PCM audio bytes
            sample_rate: Sample rate in Hz
            frame_duration_ms: Frame duration in milliseconds (10, 20, or 30 for webrtc)
            
        Returns:
            List of (start_ms, end_ms) tuples for speech segments
        """
        if not self.silero_model and not self.webrtc_vad:
            return []
        
        # Use webrtcvad for segment detection (silero-vad is better for overall detection)
        if self.webrtc_vad:
            return self._detect_segments_webrtc(audio_data, sample_rate, frame_duration_ms)
        
        # For silero-vad, process in chunks
        # This is a simplified version - for production, use silero-vad's built-in segment detection
        chunk_size_ms = 512  # Process in 512ms chunks
        chunk_size_samples = int(sample_rate * chunk_size_ms / 1000) * 2
        num_chunks = len(audio_data) // chunk_size_samples
        
        speech_segments = []
        in_speech = False
        speech_start = 0
        
        for i in range(num_chunks):
            chunk_start = i * chunk_size_samples
            chunk_end = chunk_start + chunk_size_samples
            chunk = audio_data[chunk_start:chunk_end]
            
            try:
                is_speech_chunk = self.is_speech(chunk, sample_rate)
                
                if is_speech_chunk and not in_speech:
                    # Speech started
                    in_speech = True
                    speech_start = i * chunk_size_ms
                elif not is_speech_chunk and in_speech:
                    # Speech ended
                    in_speech = False
                    speech_segments.append((speech_start, i * chunk_size_ms))
            except Exception:
                continue
        
        # Handle case where speech continues to end
        if in_speech:
            speech_segments.append((speech_start, num_chunks * chunk_size_ms))
        
        return speech_segments
    
    def _detect_segments_webrtc(self, audio_data: bytes, sample_rate: int = 16000,
                                frame_duration_ms: int = 30) -> list:
        """Detect speech segments using webrtcvad"""
        frame_size = int(sample_rate * frame_duration_ms / 1000) * 2
        num_frames = len(audio_data) // frame_size
        
        speech_segments = []
        in_speech = False
        speech_start = 0
        
        for i in range(num_frames):
            frame_start = i * frame_size
            frame_end = frame_start + frame_size
            frame = audio_data[frame_start:frame_end]
            
            try:
                is_speech_frame = self.webrtc_vad.is_speech(frame, sample_rate)
                
                if is_speech_frame and not in_speech:
                    # Speech started
                    in_speech = True
                    speech_start = i * frame_duration_ms
                elif not is_speech_frame and in_speech:
                    # Speech ended
                    in_speech = False
                    speech_segments.append((speech_start, i * frame_duration_ms))
            except Exception:
                continue
        
        # Handle case where speech continues to end
        if in_speech:
            speech_segments.append((speech_start, num_frames * frame_duration_ms))
        
        return speech_segments


# Singleton instance
_vad_service: Optional[VADService] = None


def get_vad_service(aggressiveness: int = 2, use_silero: bool = True) -> VADService:
    """
    Get VAD service instance (singleton)
    
    Args:
        aggressiveness: For webrtcvad fallback (0-3)
        use_silero: Use silero-vad if available (highest accuracy, recommended)
    """
    global _vad_service
    if _vad_service is None:
        _vad_service = VADService(aggressiveness=aggressiveness, use_silero=use_silero)
    return _vad_service

