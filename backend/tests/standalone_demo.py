"""
Standalone Demo Script
Tests the complete pipeline using demo audio files directly (no HTTP server needed)
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Load environment variables from .env.local (same as backend)
parent_dir = Path(__file__).parent.parent.parent
env_path = parent_dir / '.env.local'
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"[OK] Loaded environment variables from: {env_path}")
else:
    # Try current directory
    load_dotenv('.env.local', override=True)
    print("[OK] Loaded environment variables from: .env.local")

from backend.services.stt_service import get_stt_service
from backend.services.llm_service import get_llm_service
from backend.services.tts_service import get_tts_service
from backend.services.audio_converter import convert_webm_to_wav, validate_audio
from backend.services.metrics_service import get_metrics_service

DEMO_AUDIO_DIR = Path(__file__).parent.parent.parent / "demo_audio"

def test_service_availability():
    """Check if all services are available"""
    print("\n" + "="*60)
    print("SERVICE AVAILABILITY CHECK")
    print("="*60)
    
    stt_service = get_stt_service()
    llm_service = get_llm_service()
    tts_service = get_tts_service()
    metrics_service = get_metrics_service()
    
    services = {
        "STT": (stt_service.groq_client is not None) or (stt_service.google_client is not None),
        "LLM": llm_service.model is not None,
        "TTS": tts_service.providers != [],
        "Metrics": metrics_service is not None
    }
    
    for service, available in services.items():
        status = "✅ Available" if available else "❌ Not Available"
        print(f"{service}: {status}")
    
    return all(services.values())

def process_audio_file(audio_path, description):
    """Process a single audio file through the complete pipeline"""
    print("\n" + "="*60)
    print(f"PROCESSING: {description}")
    print(f"File: {audio_path.name}")
    print("="*60)
    
    if not audio_path.exists():
        print(f"❌ ERROR: File not found: {audio_path}")
        return False
    
    file_size = audio_path.stat().st_size
    print(f"File size: {file_size} bytes ({file_size/1024:.1f} KB)")
    
    metrics_service = get_metrics_service()
    stt_service = get_stt_service()
    llm_service = get_llm_service()
    tts_service = get_tts_service()
    
    try:
        # Step 1: Read audio file
        print("\n[1/5] Reading audio file...")
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        
        # Step 2: Convert to WAV if needed
        print("[2/5] Converting audio to WAV format...")
        if audio_path.suffix.lower() == '.wav':
            wav_data = audio_data
        else:
            wav_data = convert_webm_to_wav(audio_data)
            if not wav_data:
                print("❌ ERROR: Failed to convert audio to WAV")
                return False
        
        # Step 3: Validate audio
        print("[3/5] Validating audio...")
        is_valid, metadata = validate_audio(wav_data)
        if not is_valid:
            print(f"⚠️ WARNING: Audio validation issues: {metadata.get('error', metadata.get('validation_warning', 'Unknown'))}")
        else:
            print(f"✅ Audio valid: {metadata.get('sample_rate', 'N/A')}Hz, {metadata.get('channels', 'N/A')} channels, {metadata.get('duration_seconds', 0):.2f}s")
        
        # Step 4: STT Transcription
        print("[4/5] Transcribing audio (STT)...")
        stt_start = time.time()
        transcript = stt_service.transcribe_audio(wav_data)
        stt_elapsed = (time.time() - stt_start) * 1000
        
        if not transcript or not transcript.strip():
            print("❌ ERROR: STT returned empty transcript")
            metrics_service.record_stt_latency(stt_elapsed)
            metrics_service.record_transcription_success(False)
            return False
        
        print(f"✅ Transcription: '{transcript[:100]}{'...' if len(transcript) > 100 else ''}'")
        print(f"   STT Latency: {stt_elapsed:.1f}ms")
        metrics_service.record_stt_latency(stt_elapsed)
        metrics_service.record_transcription_success(True)
        
        # Step 5: LLM Response
        print("[5/5] Generating LLM response...")
        llm_start = time.time()
        llm_result = llm_service.generate_response(
            user_id="demo_user",
            user_message=transcript,
            user_name="Demo User"
        )
        llm_elapsed = (time.time() - llm_start) * 1000
        
        if not llm_result or not llm_result.get('response'):
            print("❌ ERROR: LLM returned empty response")
            return False
        
        llm_response = llm_result.get('response', '')
        print(f"✅ LLM Response: '{llm_response[:100]}{'...' if len(llm_response) > 100 else ''}'")
        print(f"   LLM Latency: {llm_elapsed:.1f}ms")
        
        # Step 6: TTS Synthesis
        print("[6/6] Synthesizing speech (TTS)...")
        tts_start = time.time()
        tts_audio = tts_service.synthesize_speech(llm_response)
        tts_elapsed = (time.time() - tts_start) * 1000
        
        if not tts_audio:
            print("❌ ERROR: TTS returned empty audio")
            return False
        
        print(f"✅ TTS Audio: {len(tts_audio)} bytes")
        print(f"   TTS Latency: {tts_elapsed:.1f}ms")
        
        # Calculate end-to-end latency
        e2e_latency = (time.time() - stt_start) * 1000
        metrics_service.record_end_to_end_latency(e2e_latency)
        
        print(f"\n✅ COMPLETE!")
        print(f"   Total End-to-End Latency: {e2e_latency:.1f}ms")
        print(f"   Breakdown: STT={stt_elapsed:.1f}ms, LLM={llm_elapsed:.1f}ms, TTS={tts_elapsed:.1f}ms")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def run_demo():
    """Run complete demo with audio files"""
    print("\n" + "="*60)
    print("DEMO: Talk With Zeno - Complete Pipeline Test (Standalone)")
    print("="*60)
    
    # Check service availability
    if not test_service_availability():
        print("\n❌ ERROR: Some services are not available. Check your API keys and configuration.")
        return
    
    # Find demo audio files
    if not DEMO_AUDIO_DIR.exists():
        print(f"\n⚠️ WARNING: Demo audio directory not found: {DEMO_AUDIO_DIR}")
        print("Creating directory...")
        DEMO_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        print("Please add WAV or WebM audio files to:", DEMO_AUDIO_DIR)
        return
    
    audio_files = sorted(list(DEMO_AUDIO_DIR.glob("*.wav")) + list(DEMO_AUDIO_DIR.glob("*.webm")))
    
    if not audio_files:
        print(f"\n⚠️ WARNING: No audio files found in {DEMO_AUDIO_DIR}")
        print("Please add WAV or WebM files to test")
        return
    
    print(f"\nFound {len(audio_files)} audio file(s) in demo_audio/")
    for i, f in enumerate(audio_files, 1):
        size_kb = f.stat().st_size / 1024
        print(f"  {i}. {f.name} ({size_kb:.1f} KB)")
    
    # Process each audio file
    results = []
    for i, audio_file in enumerate(audio_files, 1):
        description = f"Audio File {i}/{len(audio_files)}"
        success = process_audio_file(audio_file, description)
        results.append((audio_file.name, success))
        
        if i < len(audio_files):
            print("\n" + "-"*60)
            time.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*60)
    print("DEMO SUMMARY")
    print("="*60)
    for filename, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {filename}")
    
    success_count = sum(1 for _, s in results if s)
    print(f"\nTotal: {success_count}/{len(results)} passed ({success_count/len(results)*100:.1f}%)")
    
    # Final metrics
    print("\n" + "="*60)
    print("FINAL METRICS")
    print("="*60)
    try:
        metrics_service = get_metrics_service()
        metrics = metrics_service.get_metrics_summary()
        
        # Print metrics in a readable format instead of JSON
        print(f"Transcription Success Rate: {metrics.get('transcription_success_rate', 0):.1f}%")
        print(f"Average STT Latency: {metrics.get('avg_stt_latency_ms', 0):.1f}ms")
        print(f"Average End-to-End Latency: {metrics.get('avg_end_to_end_latency_ms', 0):.1f}ms")
        print(f"Retry Rate: {metrics.get('retry_rate', 0):.1f}%")
        print(f"Validation Failure Rate: {metrics.get('validation_failure_rate', 0):.1f}%")
        print(f"STT Requests/Minute: {metrics.get('stt_requests_per_minute', 0)}")
        print(f"Total Utterances: {metrics.get('total_utterances', 0)}")
        print(f"Successful Transcriptions: {metrics.get('successful_transcriptions', 0)}")
        print(f"Failed Transcriptions: {metrics.get('failed_transcriptions', 0)}")
        print(f"Sample Size: {metrics.get('sample_size', 0)}")
        
        if metrics.get('error_counts'):
            print(f"Error Counts: {metrics.get('error_counts')}")
    except Exception as e:
        print(f"⚠️  Could not retrieve metrics: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("DEMO COMPLETE!")
    print("="*60)
    sys.stdout.flush()  # Ensure output is flushed

if __name__ == "__main__":
    run_demo()

