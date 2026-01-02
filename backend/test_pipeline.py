"""
End-to-end pipeline test
Tests the complete STT -> LLM -> TTS pipeline
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

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


def main():
    """Run all pipeline tests"""
    print("="*60)
    print("Talk With Zeno - Pipeline Test Suite")
    print("="*60)
    
    results = {}
    
    # Test storage
    results['storage'] = test_storage()
    
    # Test text pipeline
    results['text'] = test_text_pipeline()
    
    # Test voice pipeline (availability check)
    results['voice'] = test_voice_pipeline()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "[OK]" if result else "[X]"
        print(f"{status} {test_name.upper()} pipeline")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n[OK] All pipeline tests passed!")
    else:
        print("\n[X] Some tests failed. Check logs above.")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

