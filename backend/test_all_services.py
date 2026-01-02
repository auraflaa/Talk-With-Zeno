"""
Comprehensive test suite for all services
Tests STT, LLM, TTS, Storage, Database, and API endpoints
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
from backend.services.storage_service import get_storage_service
from backend.services.database import get_database


def test_stt_service():
    """Test Speech-to-Text service"""
    print("\n" + "="*60)
    print("TESTING STT SERVICE")
    print("="*60)
    
    stt = get_stt_service()
    
    # Check initialization
    if not stt.client:
        print("[X] STT: Client not initialized")
        print("    Issue: GOOGLE_APPLICATION_CREDENTIALS not set or invalid")
        return False
    
    print("[OK] STT: Client initialized")
    print(f"    Service: Google Cloud Speech-to-Text")
    
    # Note: Full test requires actual audio file
    print("[INFO] STT: Ready for audio transcription")
    print("    Note: Full test requires actual audio input")
    
    return True


def test_llm_service():
    """Test Large Language Model service"""
    print("\n" + "="*60)
    print("TESTING LLM SERVICE")
    print("="*60)
    
    llm = get_llm_service()
    
    # Check initialization
    if not llm.model:
        print("[X] LLM: Model not initialized")
        print("    Issue: GEMINI_API_KEY not set or invalid")
        return False
    
    print("[OK] LLM: Model initialized")
    print(f"    Model: {llm.current_model_name}")
    
    # Test generation
    print("\n[TEST] Generating test response...")
    try:
        result = llm.generate_response(
            user_id="test_user",
            user_message="Hello, this is a test message.",
            conversation_history=[]
        )
        
        if result and result.get("response"):
            response = result["response"]
            print(f"[OK] LLM: Response generated ({len(response)} chars)")
            print(f"    Preview: {response[:80]}...")
            return True
        else:
            print("[X] LLM: No response generated")
            return False
    except Exception as e:
        print(f"[X] LLM: Error during generation: {e}")
        return False


def test_tts_service():
    """Test Text-to-Speech service"""
    print("\n" + "="*60)
    print("TESTING TTS SERVICE")
    print("="*60)
    
    tts = get_tts_service()
    
    # Check providers
    if not tts.providers:
        print("[X] TTS: No providers available")
        print("    Issue: GROQ_API_KEY or GEMINI_API_KEY not set")
        return False
    
    print("[OK] TTS: Providers available")
    print(f"    Providers: {', '.join(tts.providers)}")
    
    # Test synthesis
    test_text = "Hello, this is a test of the text to speech service."
    print(f"\n[TEST] Synthesizing speech for: '{test_text}'")
    
    try:
        audio = tts.synthesize_speech(text=test_text)
        
        if audio:
            print(f"[OK] TTS: Audio generated ({len(audio)} bytes)")
            print(f"    Format: WAV")
            return True
        else:
            print("[X] TTS: Audio generation failed")
            return False
    except Exception as e:
        print(f"[X] TTS: Error during synthesis: {e}")
        return False


def test_storage_service():
    """Test Storage service"""
    print("\n" + "="*60)
    print("TESTING STORAGE SERVICE")
    print("="*60)
    
    storage = get_storage_service()
    user_id = "test_user_storage"
    conversation_id = "test_conv_storage"
    
    # Test conversation storage
    print("\n[TEST] Conversation storage...")
    test_messages = [
        {"role": "user", "content": "Test message", "timestamp": "2024-01-01T00:00:00"},
        {"role": "assistant", "content": "Test response", "timestamp": "2024-01-01T00:00:01"}
    ]
    
    saved = storage.save_conversation(user_id, conversation_id, test_messages)
    if not saved:
        print("[X] Storage: Failed to save conversation")
        return False
    
    print("[OK] Storage: Conversation saved")
    
    loaded = storage.load_conversation(user_id, conversation_id)
    if not loaded or len(loaded.get("messages", [])) != 2:
        print("[X] Storage: Failed to load conversation")
        return False
    
    print("[OK] Storage: Conversation loaded")
    
    # Test personalization storage
    print("\n[TEST] Personalization storage...")
    test_personalization = {
        "tonePreference": "supportive",
        "depthTolerance": "moderate"
    }
    
    saved = storage.save_personalization(user_id, test_personalization)
    if not saved:
        print("[X] Storage: Failed to save personalization")
        return False
    
    print("[OK] Storage: Personalization saved")
    
    loaded = storage.load_personalization(user_id)
    if not loaded or loaded.get("tonePreference") != "supportive":
        print("[X] Storage: Failed to load personalization")
        return False
    
    print("[OK] Storage: Personalization loaded")
    
    return True


def test_database_service():
    """Test Database service"""
    print("\n" + "="*60)
    print("TESTING DATABASE SERVICE")
    print("="*60)
    
    db = get_database()
    test_user_id = "test_user_db"
    test_email = "test@example.com"
    
    # Test user creation
    print("\n[TEST] User creation...")
    # Delete if exists first
    db.delete_user(test_user_id)
    
    created = db.create_user(
        user_id=test_user_id,
        name="Test User",
        email=test_email,
        avatar_color="bg-primary"
    )
    
    if not created:
        print("[X] Database: Failed to create user")
        return False
    
    print("[OK] Database: User created")
    
    # Test user retrieval
    print("\n[TEST] User retrieval...")
    user = db.get_user(test_user_id)
    if not user or user["email"] != test_email:
        print("[X] Database: Failed to retrieve user")
        return False
    
    print("[OK] Database: User retrieved")
    print(f"    User: {user['name']} ({user['email']})")
    
    # Test user update
    print("\n[TEST] User update...")
    updated = db.update_user(test_user_id, name="Updated Test User")
    if not updated:
        print("[X] Database: Failed to update user")
        return False
    
    user = db.get_user(test_user_id)
    if user["name"] != "Updated Test User":
        print("[X] Database: Update not reflected")
        return False
    
    print("[OK] Database: User updated")
    
    # Cleanup
    db.delete_user(test_user_id)
    print("[OK] Database: Test user cleaned up")
    
    return True


def test_api_endpoints():
    """Test API endpoints availability"""
    print("\n" + "="*60)
    print("TESTING API ENDPOINTS")
    print("="*60)
    
    # Import app to check routes
    try:
        from backend.app import app
        
        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static':
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
                    'path': rule.rule
                })
        
        print(f"\n[OK] API: {len(routes)} endpoints available")
        print("\nAvailable endpoints:")
        for route in sorted(routes, key=lambda x: x['path']):
            methods = ', '.join(route['methods'])
            print(f"    {methods:15} {route['path']}")
        
        # Check critical endpoints
        critical_endpoints = [
            '/api/health',
            '/api/voice/process',
            '/api/text/process'
        ]
        
        found_critical = all(
            any(r['path'] == ep for r in routes)
            for ep in critical_endpoints
        )
        
        if found_critical:
            print("\n[OK] API: All critical endpoints available")
            return True
        else:
            print("\n[X] API: Some critical endpoints missing")
            return False
            
    except Exception as e:
        print(f"[X] API: Error checking endpoints: {e}")
        return False


def main():
    """Run all service tests"""
    print("="*60)
    print("COMPREHENSIVE SERVICE TEST SUITE")
    print("="*60)
    
    results = {
        'STT': test_stt_service(),
        'LLM': test_llm_service(),
        'TTS': test_tts_service(),
        'Storage': test_storage_service(),
        'Database': test_database_service(),
        'API': test_api_endpoints()
    }
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for service, result in results.items():
        status = "[OK]" if result else "[X]"
        print(f"{status} {service} Service")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("[SUCCESS] All services are working correctly!")
    else:
        print("[WARNING] Some services have issues. Check logs above.")
    print("="*60)
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

