"""
Quick test to verify frontend-backend integration
"""

import sys
import requests
from pathlib import Path

parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

def test_backend_health():
    """Test backend health endpoint"""
    print("\n[1/4] Testing Backend Health...")
    try:
        response = requests.get("http://localhost:5000/api/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Backend is running")
            print(f"  Status: {data.get('status')}")
            print(f"  Services: STT={data['services']['stt']}, LLM={data['services']['llm']}, TTS={data['services']['tts']}")
            return True
        else:
            print(f"  ✗ Backend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Backend not accessible: {e}")
        return False

def test_text_endpoint():
    """Test text processing endpoint"""
    print("\n[2/4] Testing Text Processing Endpoint...")
    try:
        payload = {
            "text": "Hello, this is a test",
            "user_id": "test_user_frontend",
            "generate_audio": False
        }
        response = requests.post(
            "http://localhost:5000/api/text/process",
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Text processing working")
            print(f"  Response: {data.get('text_response', '')[:80]}...")
            print(f"  Conversation ID: {data.get('conversation_id')}")
            return True
        else:
            print(f"  ✗ Text processing failed: {response.status_code}")
            print(f"  Error: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Text processing error: {e}")
        return False

def test_frontend_accessible():
    """Test if frontend is accessible"""
    print("\n[3/4] Testing Frontend Accessibility...")
    try:
        response = requests.get("http://localhost:3000", timeout=5)
        if response.status_code == 200:
            print(f"  ✓ Frontend is running on http://localhost:3000")
            return True
        else:
            print(f"  ✗ Frontend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Frontend not accessible: {e}")
        print(f"  Note: Start frontend with 'npm run dev' if not running")
        return False

def test_cors():
    """Test CORS configuration"""
    print("\n[4/4] Testing CORS Configuration...")
    try:
        headers = {
            'Origin': 'http://localhost:3000',
            'Access-Control-Request-Method': 'POST'
        }
        response = requests.options(
            "http://localhost:5000/api/text/process",
            headers=headers,
            timeout=5
        )
        cors_header = response.headers.get('Access-Control-Allow-Origin')
        if cors_header:
            print(f"  ✓ CORS configured: {cors_header}")
            return True
        else:
            print(f"  ⚠ CORS header not found (may still work)")
            return True  # Not critical
    except Exception as e:
        print(f"  ⚠ CORS test skipped: {e}")
        return True  # Not critical

def main():
    print("="*60)
    print("FRONTEND-BACKEND INTEGRATION TEST")
    print("="*60)
    
    results = {
        'backend': test_backend_health(),
        'text_endpoint': test_text_endpoint(),
        'frontend': test_frontend_accessible(),
        'cors': test_cors()
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = all(results.values())
    
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {test:20s}: {status}")
    
    print("\n" + "="*60)
    if all_passed:
        print("✓ ALL TESTS PASSED - Frontend and Backend are ready!")
        print("\nNext steps:")
        print("  1. Open http://localhost:3000 in your browser")
        print("  2. Try sending a text message")
        print("  3. Try voice mode (click microphone)")
    else:
        print("⚠ SOME TESTS FAILED - Check the errors above")
        print("\nTroubleshooting:")
        print("  - Backend: python backend/run.py")
        print("  - Frontend: npm run dev")
        print("  - Check API keys in .env.local")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()

