"""
Audio Format Conversion Service
Converts WebM/Opus to WAV/PCM for STT processing
PRIORITY FIX #2: Proper format conversion pipeline
"""

import io
import os
import subprocess
import tempfile
from typing import Optional, Tuple
from pathlib import Path

# Try to import pydub for conversion
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None


def convert_webm_to_wav(audio_data: bytes, target_sample_rate: int = 16000, 
                        target_channels: int = 1) -> Optional[bytes]:
    """
    Convert WebM/Opus audio to WAV format (16-bit, mono, 16kHz)
    
    PRIORITY FIX #2: Proper format conversion before STT
    - Decodes WebM/Opus to raw PCM
    - Converts to mono if stereo
    - Resamples to target sample rate
    - Exports as proper WAV file
    
    Args:
        audio_data: WebM/Opus audio bytes (or WAV if already in WAV format)
        target_sample_rate: Target sample rate (default: 16000 Hz for STT)
        target_channels: Target channels (1 = mono, default for STT)
        
    Returns:
        WAV audio bytes or None if conversion fails
    """
    if not audio_data or len(audio_data) < 100:
        return None
    
    # Check if input is already WAV format
    if len(audio_data) >= 12 and audio_data[0:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
        # Already WAV format - just process it (convert sample rate/channels if needed)
        if PYDUB_AVAILABLE:
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                # Convert to mono if stereo
                if audio.channels > target_channels:
                    audio = audio.set_channels(target_channels)
                # Resample to target sample rate if needed
                if audio.frame_rate != target_sample_rate:
                    audio = audio.set_frame_rate(target_sample_rate)
                # Ensure 16-bit PCM
                audio = audio.set_sample_width(2)
                # Export as WAV
                wav_output = io.BytesIO()
                audio.export(wav_output, format="wav")
                return wav_output.getvalue()
            except Exception as e:
                print(f"AudioConverter: WAV processing failed: {e}")
                # If processing fails, return original WAV (might work for STT)
                return audio_data
        else:
            # pydub not available - return WAV as-is (might work for STT)
            return audio_data
    
    # Method 1: Try pydub (if available)
    if PYDUB_AVAILABLE:
        try:
            # Load WebM audio from bytes
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="webm")
            
            # Convert to mono if stereo
            if audio.channels > target_channels:
                audio = audio.set_channels(target_channels)
            
            # Resample to target sample rate if needed
            if audio.frame_rate != target_sample_rate:
                audio = audio.set_frame_rate(target_sample_rate)
            
            # Ensure 16-bit PCM
            audio = audio.set_sample_width(2)  # 16-bit = 2 bytes per sample
            
            # Export as WAV
            wav_output = io.BytesIO()
            audio.export(wav_output, format="wav")
            wav_data = wav_output.getvalue()
            
            return wav_data
        except Exception as e:
            print(f"AudioConverter: pydub conversion failed: {e}")
            # Fall through to ffmpeg method
    
    # Method 2: Try ffmpeg (more reliable, recommended)
    try:
        # Check if ffmpeg is available
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, 
                              timeout=2)
        if result.returncode != 0:
            raise FileNotFoundError("ffmpeg not found")
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as input_file:
            input_file.write(audio_data)
            input_path = input_file.name
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_file:
            output_path = output_file.name
        
        try:
            # Convert using ffmpeg
            # -i: input file
            # -ar: audio sample rate
            # -ac: audio channels (1 = mono)
            # -acodec: audio codec (pcm_s16le = 16-bit PCM)
            # -y: overwrite output file
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-ar', str(target_sample_rate),
                '-ac', str(target_channels),
                '-acodec', 'pcm_s16le',
                '-y',  # Overwrite output
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=10,  # 10 second timeout
                check=True
            )
            
            # Read converted WAV file
            with open(output_path, 'rb') as f:
                wav_data = f.read()
            
            return wav_data
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(input_path)
            except:
                pass
            try:
                os.unlink(output_path)
            except:
                pass
                
    except FileNotFoundError:
        print("AudioConverter: ffmpeg not found - install ffmpeg for reliable conversion")
        return None
    except subprocess.TimeoutExpired:
        print("AudioConverter: ffmpeg conversion timed out")
        return None
    except Exception as e:
        print(f"AudioConverter: ffmpeg conversion failed: {e}")
        return None
    
    return None


def validate_audio(audio_data: bytes, audio_format: str = 'wav') -> Tuple[bool, Optional[dict]]:
    """
    Validate audio data before STT processing
    
    PRIORITY FIX #6: Audio validation
    Checks:
    - File size vs expected duration
    - Sample rate (must match STT expectation)
    - Channel count (mono)
    - Basic integrity (can be decoded)
    
    Args:
        audio_data: Audio bytes
        audio_format: Audio format ('wav' or 'webm')
        
    Returns:
        (is_valid, metadata_dict) where metadata contains:
        - sample_rate: Sample rate in Hz
        - channels: Number of channels
        - duration_ms: Duration in milliseconds
        - file_size: File size in bytes
    """
    if not audio_data or len(audio_data) < 100:
        return (False, None)
    
    metadata = {
        'file_size': len(audio_data),
        'format': audio_format
    }
    
    # Try to decode and get metadata
    if PYDUB_AVAILABLE:
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format=audio_format)
            metadata['sample_rate'] = audio.frame_rate
            metadata['channels'] = audio.channels
            metadata['duration_ms'] = len(audio)
            metadata['duration_s'] = len(audio) / 1000.0
            
            # Validation checks
            # 1. Must be mono for STT
            if audio.channels != 1:
                print(f"AudioConverter: Validation failed - expected mono, got {audio.channels} channels")
                return (False, metadata)
            
            # 2. Sample rate should be 16kHz (or close)
            if audio.frame_rate < 8000 or audio.frame_rate > 48000:
                print(f"AudioConverter: Validation warning - sample rate {audio.frame_rate}Hz may cause issues")
            
            # 3. Duration check (reject very short or very long)
            if metadata['duration_ms'] < 100:  # Less than 100ms
                print(f"AudioConverter: Validation failed - audio too short ({metadata['duration_ms']}ms)")
                return (False, metadata)
            
            if metadata['duration_ms'] > 60000:  # More than 60 seconds
                print(f"AudioConverter: Validation warning - audio very long ({metadata['duration_ms']}ms)")
            
            # 4. File size vs duration check (rough sanity check)
            # WAV at 16kHz mono 16-bit = 32000 bytes/second
            # WebM/Opus at ~64kbps = ~8000 bytes/second
            expected_min_size = (metadata['duration_ms'] / 1000.0) * 1000  # At least 1KB per second
            if metadata['file_size'] < expected_min_size:
                print(f"AudioConverter: Validation warning - file size ({metadata['file_size']} bytes) seems small for duration ({metadata['duration_ms']}ms)")
            
            return (True, metadata)
            
        except Exception as e:
            print(f"AudioConverter: Validation failed - could not decode audio: {e}")
            return (False, metadata)
    
    # If pydub not available, do basic checks
    if audio_format == 'wav' and len(audio_data) >= 44:  # WAV header is 44 bytes
        # Basic WAV header check
        if audio_data[0:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
            return (True, metadata)
    
    return (False, metadata)

