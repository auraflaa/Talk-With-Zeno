"""
Test script to verify STT, LLM, and TTS services are working
Run this to diagnose issues with the voice pipeline
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

def test_stt():
    """Test STT service"""
    print("\n" + "="*50)
    print("Testing STT Service")
    print("="*50)
    
    stt_service = get_stt_service()
    
    if not stt_service.client:
        print("[X] STT: Client not initialized")
        print("   Check GOOGLE_APPLICATION_CREDENTIALS in .env.local")
        return False
    
    print("[OK] STT: Client initialized")
    
    # Test with a dummy audio file (you would need real audio for full test)
    print("[INFO] STT: Full test requires actual audio file")
    print("   STT service appears to be configured correctly")
    return True

def test_llm():
    """Test LLM service"""
    print("\n" + "="*50)
    print("Testing LLM Service")
    print("="*50)
    
    llm_service = get_llm_service()
    
    if not llm_service.model:
        print("[X] LLM: Model not initialized")
        print("   Check GEMINI_API_KEY in .env.local")
        return False
    
    print("[OK] LLM: Model initialized")
    print(f"   Current model: {llm_service.model._model_name if hasattr(llm_service.model, '_model_name') else 'gemini'}")
    
    # Test with a simple message
    print("\nTesting LLM with sample message...")
    try:
        result = llm_service.generate_response(
            user_id="test_user",
            user_message="Hello, this is a test. Please respond briefly.",
            conversation_history=[]
        )
        
        if result.get("response"):
            print(f"[OK] LLM: Response received: {result['response'][:100]}...")
            return True
        else:
            print("[X] LLM: No response received")
            print(f"   Error: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"[X] LLM: Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tts():
    """Test TTS service"""
    print("\n" + "="*50)
    print("Testing TTS Service")
    print("="*50)
    
    tts_service = get_tts_service()
    
    if not tts_service.providers:
        print("[X] TTS: No providers available")
        print("   Check GROQ_API_KEY or GEMINI_API_KEY in .env.local")
        return False
    
    print(f"[OK] TTS: Providers available: {tts_service.providers}")
    
    # Test with a simple text
    test_text = "Hello, this is a test of the text to speech service."
    print(f"\nTesting TTS with text: '{test_text}'")
    
    try:
        audio_data = tts_service.synthesize_speech(text=test_text)
        
        if audio_data:
            print(f"[OK] TTS: Audio generated successfully")
            print(f"   Audio size: {len(audio_data)} bytes")
            print(f"   Audio type: bytes")
            return True
        else:
            print("[X] TTS: Failed to generate audio")
            print("   Check API keys and provider availability")
            return False
    except Exception as e:
        print(f"[X] TTS: Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_environment():
    """Check environment variables"""
    print("\n" + "="*50)
    print("Checking Environment Variables")
    print("="*50)
    
    required_vars = {
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY"),
        "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    }
    
    all_ok = True
    for var_name, var_value in required_vars.items():
        if var_value:
            # Don't print full value for security
            masked = var_value[:10] + "..." if len(var_value) > 10 else "***"
            print(f"[OK] {var_name}: {masked}")
        else:
            print(f"[X] {var_name}: Not set")
            all_ok = False
    
    # Check if credentials file exists
    creds_path = required_vars["GOOGLE_APPLICATION_CREDENTIALS"]
    if creds_path:
        if os.path.exists(creds_path):
            print(f"[OK] Credentials file exists: {creds_path}")
        else:
            print(f"[X] Credentials file not found: {creds_path}")
            all_ok = False
    
    return all_ok

def main():
    print("\n" + "="*50)
    print("Talk With Zeno - Service Health Check")
    print("="*50)
    
    # Check environment
    env_ok = test_environment()
    
    # Test services
    stt_ok = test_stt()
    llm_ok = test_llm()
    tts_ok = test_tts()
    
    # Summary
    print("\n" + "="*50)
    print("Summary")
    print("="*50)
    print(f"Environment: {'[OK]' if env_ok else '[X] Issues'}")
    print(f"STT Service: {'[OK]' if stt_ok else '[X] Failed'}")
    print(f"LLM Service: {'[OK]' if llm_ok else '[X] Failed'}")
    print(f"TTS Service: {'[OK]' if tts_ok else '[X] Failed'}")
    
    if all([env_ok, stt_ok, llm_ok, tts_ok]):
        print("\n[OK] All services are working!")
    else:
        print("\n[X] Some services have issues. Check the errors above.")
    
    print("\n")

if __name__ == "__main__":
    main()

