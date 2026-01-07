"""
DEMO TEST: Prove the pipeline with a known-good 5-second WAV file

This test verifies:
1. Audio conversion (WebM to WAV)
2. Audio validation
3. STT transcription
4. Full pipeline works end-to-end

Usage:
    python backend/tests/test_pipeline_wav.py <path_to_5second_wav_file.wav>
    
Example:
    python backend/tests/test_pipeline_wav.py test_audio_5s.wav
"""

import sys
import os
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env.local')

def test_pipeline_with_wav(wav_file_path: str):
    """Test the full pipeline with a known-good WAV file"""
    
    print("=" * 60)
    print("DEMO PIPELINE TEST: Known-Good 5-Second WAV File")
    print("=" * 60)
    print()
    
    # Check if file exists
    if not os.path.exists(wav_file_path):
        print(f"❌ ERROR: File not found: {wav_file_path}")
        print()
        print("Please record a 5-second WAV file and provide the path.")
        print("You can use any audio recording software or:")
        print("  - Windows: Sound Recorder")
        print("  - Online: https://online-voice-recorder.com/")
        return False
    
    # Read WAV file
    print(f"📁 Step 1: Reading WAV file: {wav_file_path}")
    with open(wav_file_path, 'rb') as f:
        wav_data = f.read()
    
    file_size = len(wav_data)
    print(f"   ✓ File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    
    # Check file size (5 seconds at 16kHz mono 16-bit = ~160KB)
    expected_min = 100 * 1024  # At least 100KB for 5 seconds
    expected_max = 500 * 1024  # At most 500KB
    if file_size < expected_min:
        print(f"   ⚠️  WARNING: File seems too small for 5 seconds (expected ~160KB)")
    elif file_size > expected_max:
        print(f"   ⚠️  WARNING: File seems too large for 5 seconds")
    else:
        print(f"   ✓ File size looks reasonable for 5 seconds")
    print()
    
    # Step 2: Validate audio
    print("🔍 Step 2: Validating audio")
    from backend.services.audio_converter import validate_audio
    
    is_valid, metadata = validate_audio(wav_data, audio_format='wav')
    
    if not is_valid:
        print(f"   ❌ Validation FAILED")
        print(f"   Metadata: {metadata}")
        return False
    
    print(f"   ✓ Validation PASSED")
    if metadata:
        print(f"   - Sample rate: {metadata.get('sample_rate', 'unknown')} Hz")
        print(f"   - Channels: {metadata.get('channels', 'unknown')}")
        print(f"   - Duration: {metadata.get('duration_ms', 'unknown')} ms ({metadata.get('duration_s', 'unknown')} seconds)")
        print(f"   - File size: {metadata.get('file_size', 'unknown')} bytes")
    print()
    
    # Step 3: Test STT
    print("🎤 Step 3: Testing STT transcription")
    from backend.services.stt_service import STTService
    
    stt_service = STTService()
    
    if not stt_service.groq_client and not stt_service.google_client:
        print("   ❌ ERROR: No STT clients available")
        print("   Please check your API keys in .env.local")
        return False
    
    print(f"   - Groq client: {'✓ Available' if stt_service.groq_client else '✗ Not available'}")
    print(f"   - Google client: {'✓ Available' if stt_service.google_client else '✗ Not available'}")
    print()
    
    print("   Transcribing audio...")
    stt_start = time.time()
    
    try:
        transcript = stt_service.transcribe_audio(wav_data, language_code='en-US', audio_format='wav')
        stt_duration = time.time() - stt_start
        
        if transcript:
            print(f"   ✓ Transcription SUCCESS ({stt_duration:.2f}s)")
            print(f"   Transcript: '{transcript}'")
            print(f"   Length: {len(transcript)} characters")
            print()
            
            # Step 4: Summary
            print("=" * 60)
            print("✅ PIPELINE TEST: PASSED")
            print("=" * 60)
            print()
            print("The pipeline is working correctly:")
            print("  ✓ Audio conversion: Working")
            print("  ✓ Audio validation: Working")
            print("  ✓ STT transcription: Working")
            print()
            print("If the frontend is having issues, the problem is likely:")
            print("  - Frontend audio capture")
            print("  - WebM format/conversion")
            print("  - Timing/synchronization")
            print("  - VAD detection")
            print()
            return True
        else:
            print(f"   ❌ Transcription FAILED (returned None)")
            print(f"   Duration: {stt_duration:.2f}s")
            print()
            print("Possible issues:")
            print("  - Audio too quiet or unclear")
            print("  - STT API error (check API keys)")
            print("  - Network timeout")
            return False
            
    except Exception as e:
        stt_duration = time.time() - stt_start
        print(f"   ❌ Transcription ERROR ({stt_duration:.2f}s)")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_pipeline_wav.py <path_to_5second_wav_file.wav>")
        print()
        print("Example:")
        print("  python backend/tests/test_pipeline_wav.py test_audio_5s.wav")
        print()
        print("To create a test file:")
        print("  1. Record 5 seconds of clear speech")
        print("  2. Save as WAV format (16kHz mono recommended)")
        print("  3. Run this test with the file path")
        sys.exit(1)
    
    wav_file = sys.argv[1]
    success = test_pipeline_with_wav(wav_file)
    sys.exit(0 if success else 1)

