"""
Test Voice Mode Pipeline
Tests the complete voice processing pipeline: STT -> LLM -> TTS
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Load environment variables
env_path = parent_dir / '.env.local'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv('.env.local')

from backend.services.stt_service import get_stt_service
from backend.services.llm_service import get_llm_service
from backend.services.tts_service import get_tts_service

def test_voice_pipeline():
    """Test the complete voice processing pipeline"""
    print("\n" + "="*60)
    print("VOICE MODE PIPELINE TEST")
    print("="*60 + "\n")
    
    # Test 1: STT Service
    print("[1/3] Testing Speech-to-Text (STT)...")
    stt_service = get_stt_service()
    if not stt_service.client:
        print("  [X] STT client not initialized")
        print("      Check GOOGLE_APPLICATION_CREDENTIALS in .env.local")
        return False
    print("  [OK] STT client initialized")
    
    # Test 2: LLM Service
    print("\n[2/3] Testing Large Language Model (LLM)...")
    llm_service = get_llm_service()
    gemini_key = os.getenv('GEMINI_API_KEY')
    if not gemini_key or gemini_key == 'your_gemini_api_key_here':
        print("  [X] GEMINI_API_KEY not set in .env.local")
        return False
    print("  [OK] GEMINI_API_KEY found")
    
    # Test LLM with a simple message
    test_message = "Hello, how are you?"
    print(f"  Testing LLM with message: '{test_message}'")
    try:
        result = llm_service.generate_response(
            user_id="test_user",
            user_message=test_message,
            conversation_history=[]
        )
        if result and result.get("response"):
            print(f"  [OK] LLM response: {result['response'][:100]}...")
        else:
            print("  [X] LLM returned no response")
            return False
    except Exception as e:
        print(f"  [X] LLM error: {e}")
        return False
    
    # Test 3: TTS Service
    print("\n[3/3] Testing Text-to-Speech (TTS)...")
    tts_service = get_tts_service()
    
    # Check Groq API key
    groq_key = os.getenv('GROQ_API_KEY')
    if not groq_key or groq_key == 'your_groq_api_key_here':
        print("  [X] GROQ_API_KEY not set in .env.local")
        print("      TTS will not work without this")
        return False
    print("  [OK] GROQ_API_KEY found")
    
    # Test TTS with a short text
    test_text = "Hello, this is a test."
    print(f"  Testing TTS with text: '{test_text}'")
    try:
        audio = tts_service.synthesize_speech(text=test_text)
        if audio and len(audio) > 0:
            print(f"  [OK] TTS generated audio: {len(audio)} bytes")
        else:
            print("  [X] TTS returned no audio")
            return False
    except Exception as e:
        print(f"  [X] TTS error: {e}")
        return False
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED!")
    print("="*60)
    print("\nVoice mode should work. If it doesn't, check:")
    print("  1. Browser console for frontend errors")
    print("  2. Backend terminal for processing errors")
    print("  3. Microphone permissions in browser")
    print("  4. Network tab in browser DevTools for API calls\n")
    
    return True

if __name__ == '__main__':
    success = test_voice_pipeline()
    sys.exit(0 if success else 1)

