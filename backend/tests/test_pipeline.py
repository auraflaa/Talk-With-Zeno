"""
End-to-end pipeline test
Tests the complete STT -> LLM -> TTS pipeline with audio files and text input
"""

import os
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    load_dotenv('.env.local', override=True)

from backend.services.stt_service import get_stt_service
from backend.services.llm_service import get_llm_service
from backend.services.tts_service import get_tts_service
from backend.services.storage_service import get_storage_service


def test_text_pipeline():
    """Test text input pipeline (LLM -> TTS)"""
    print("\n" + "="*60)
    print("TESTING TEXT PIPELINE")
    print("="*60)
    
    user_id = "test_user_001"
    conversation_id = "test_conv_001"
    
    # Get services
    llm_service = get_llm_service()
    tts_service = get_tts_service()
    storage_service = get_storage_service()
    
    # Test message
    user_text = "Hello, how are you today?"
    print(f"\nUser message: {user_text}")
    
    # Load conversation history
    conversation = storage_service.load_conversation(user_id, conversation_id)
    conversation_history = conversation.get("messages", []) if conversation else []
    
    # Add user message
    from datetime import datetime
    user_message = {
        "role": "user",
        "content": user_text,
        "timestamp": datetime.now().isoformat()
    }
    conversation_history.append(user_message)
    
    # LLM generation
    print("\n[1/2] Generating LLM response...")
    llm_result = llm_service.generate_response(
        user_id=user_id,
        user_message=user_text,
        conversation_history=conversation_history
    )
    
    assistant_response = llm_result["response"]
    print(f"LLM Response: {assistant_response[:100]}...")
    
    # TTS generation
    print("\n[2/2] Generating TTS audio...")
    audio_data = tts_service.synthesize_speech(text=assistant_response)
    
    if audio_data:
        print(f"[OK] Audio generated: {len(audio_data)} bytes")
        return True
    else:
        print("[X] Audio generation failed")
        return False


def test_voice_pipeline():
    """Test voice input pipeline (STT -> LLM -> TTS)"""
    print("\n" + "="*60)
    print("TESTING VOICE PIPELINE")
    print("="*60)
    
    print("\n[INFO] Voice pipeline requires actual audio input")
    print("       This test validates service availability only")
    
    stt_service = get_stt_service()
    llm_service = get_llm_service()
    tts_service = get_tts_service()
    
    # Check service availability
    checks = {
        "STT": stt_service.client is not None,
        "LLM": llm_service.model is not None,
        "TTS": len(tts_service.providers) > 0
    }
    
    print("\nService availability:")
    for service, available in checks.items():
        status = "[OK]" if available else "[X]"
        print(f"  {status} {service}")
    
    all_available = all(checks.values())
    
    if all_available:
        print("\n[OK] All services available for voice pipeline!")
        return True
    else:
        print("\n[X] Some services unavailable")
        return False


def test_storage():
    """Test storage service"""
    print("\n" + "="*60)
    print("TESTING STORAGE SERVICE")
    print("="*60)
    
    storage_service = get_storage_service()
    user_id = "test_user_001"
    conversation_id = "test_conv_001"
    
    # Test conversation storage
    print("\n[1/3] Testing conversation storage...")
    test_messages = [
        {"role": "user", "content": "Hello", "timestamp": "2024-01-01T00:00:00"},
        {"role": "assistant", "content": "Hi there!", "timestamp": "2024-01-01T00:00:01"}
    ]
    
    saved = storage_service.save_conversation(user_id, conversation_id, test_messages)
    print(f"  Save result: {'[OK]' if saved else '[X]'}")
    
    loaded = storage_service.load_conversation(user_id, conversation_id)
    print(f"  Load result: {'[OK]' if loaded else '[X]'}")
    
    if loaded:
        print(f"  Messages loaded: {len(loaded.get('messages', []))}")
    
    # Test personalization storage
    print("\n[2/3] Testing personalization storage...")
    test_personalization = {
        "tonePreference": "supportive",
        "depthTolerance": "moderate",
        "interactionMode": "voice"
    }
    
    saved = storage_service.save_personalization(user_id, test_personalization)
    print(f"  Save result: {'[OK]' if saved else '[X]'}")
    
    loaded = storage_service.load_personalization(user_id)
    print(f"  Load result: {'[OK]' if loaded else '[X]'}")
    
    if loaded:
        print(f"  Keys loaded: {len(loaded)}")
    
    # Test conversation listing
    print("\n[3/3] Testing conversation listing...")
    conversations = storage_service.list_user_conversations(user_id)
    print(f"  Conversations found: {len(conversations)}")
    
    return True


def test_stt_with_file(audio_file_path: str):
    """Test STT with an audio file"""
    print(f"\n{'='*60}")
    print(f"Testing STT with file: {audio_file_path}")
    print(f"{'='*60}")
    
    if not os.path.exists(audio_file_path):
        print(f"ERROR: Audio file not found: {audio_file_path}")
        return False
    
    stt_service = get_stt_service()
    if not stt_service.client:
        print("ERROR: STT client not initialized")
        return False
    
    with open(audio_file_path, 'rb') as f:
        audio_data = f.read()
    
    print(f"Audio file size: {len(audio_data)} bytes")
    
    audio_format = 'webm'
    if audio_file_path.endswith('.wav'):
        audio_format = 'wav'
    elif audio_file_path.endswith('.mp3'):
        audio_format = 'mp3'
    
    print(f"Audio format: {audio_format}")
    print("Transcribing audio...")
    transcript = stt_service.transcribe_audio(
        audio_data,
        language_code='en-US',
        audio_format=audio_format
    )
    
    if transcript:
        print(f"✓ Transcription successful: '{transcript}'")
        return True
    else:
        print("✗ Transcription failed - no text returned")
        return False


def test_full_audio_pipeline(audio_file_path: str):
    """Test full pipeline with audio file: STT -> LLM -> TTS"""
    print(f"\n{'='*60}")
    print("Testing Full Audio Pipeline: STT -> LLM -> TTS")
    print(f"{'='*60}")
    
    # Step 1: STT
    stt_service = get_stt_service()
    if not stt_service.client:
        print("✗ STT service not available")
        return False
    
    with open(audio_file_path, 'rb') as f:
        audio_data = f.read()
    
    audio_format = 'webm'
    if audio_file_path.endswith('.wav'):
        audio_format = 'wav'
    
    print(f"Step 1: Transcribing audio ({len(audio_data)} bytes)...")
    transcript = stt_service.transcribe_audio(
        audio_data,
        language_code='en-US',
        audio_format=audio_format
    )
    
    if not transcript:
        print("✗ STT failed")
        return False
    print(f"✓ STT: '{transcript}'")
    
    # Step 2: LLM
    print(f"\nStep 2: Generating LLM response...")
    llm_service = get_llm_service()
    if not llm_service.model:
        print("✗ LLM service not available")
        return False
    
    result = llm_service.generate_response(
        user_id='test_user',
        user_message=transcript,
        conversation_history=[],
        user_name='Test User'
    )
    
    if not result or not result.get('response'):
        print("✗ LLM failed")
        return False
    
    llm_response = result['response']
    print(f"✓ LLM: '{llm_response[:100]}...'")
    
    # Step 3: TTS
    print(f"\nStep 3: Generating TTS audio...")
    tts_service = get_tts_service()
    if not tts_service.providers:
        print("✗ TTS service not available")
        return False
    
    audio_data = tts_service.synthesize_speech(text=llm_response)
    
    if audio_data:
        output_file = 'test_pipeline_output.wav'
        with open(output_file, 'wb') as f:
            f.write(audio_data)
        print(f"✓ TTS: Saved to {output_file} ({len(audio_data)} bytes)")
        print(f"\n{'='*60}")
        print("✓ Full audio pipeline test PASSED")
        print(f"{'='*60}")
        return True
    else:
        print("✗ TTS failed")
        return False


def main():
    """Run all pipeline tests"""
    parser = argparse.ArgumentParser(description='Test pipeline components')
    parser.add_argument('--audio', type=str, help='Path to audio file for testing')
    parser.add_argument('--test', type=str, choices=['stt', 'text', 'voice', 'storage', 'full', 'all'], 
                       default='all', help='Which test to run')
    
    args = parser.parse_args()
    
    print("="*60)
    print("Talk With Zeno - Pipeline Test Suite")
    print("="*60)
    
    results = {}
    
    if args.test in ['storage', 'all']:
        results['storage'] = test_storage()
    
    if args.test in ['text', 'all']:
        results['text'] = test_text_pipeline()
    
    if args.test in ['voice', 'all']:
        results['voice'] = test_voice_pipeline()
    
    if args.test == 'stt' and args.audio:
        results['stt'] = test_stt_with_file(args.audio)
    elif args.test == 'full' and args.audio:
        results['full_audio'] = test_full_audio_pipeline(args.audio)
    elif args.test == 'all' and args.audio:
        results['stt'] = test_stt_with_file(args.audio)
        results['full_audio'] = test_full_audio_pipeline(args.audio)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "[OK]" if result else "[X]"
        print(f"{status} {test_name.upper()}")
    
    all_passed = all(results.values()) if results else False
    
    if all_passed:
        print("\n[OK] All pipeline tests passed!")
    else:
        print("\n[X] Some tests failed. Check logs above.")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

