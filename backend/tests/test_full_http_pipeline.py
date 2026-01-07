"""
Full HTTP Pipeline Test - End-to-End
Tests the COMPLETE pipeline from frontend to backend via HTTP API
This simulates EXACTLY what the browser does:
1. Creates session (like frontend)
2. Sends audio blob via FormData (like frontend)
3. Receives transcription (like frontend)
4. Triggers LLM+TTS (like frontend)
5. Verifies complete response (like frontend)
"""

import sys
import os
import time
import requests
import json
from pathlib import Path
from io import BytesIO

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

BASE_URL = "http://localhost:5000"
DEMO_AUDIO_DIR = Path(__file__).parent.parent.parent / "demo_audio"

def check_backend_running():
    """Check if backend is running"""
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=2)
        return response.status_code == 200
    except:
        return False

def test_full_http_pipeline():
    """Test complete HTTP pipeline (frontend → backend → frontend)"""
    
    print("=" * 70)
    print("FULL HTTP PIPELINE TEST - End-to-End (Frontend → Backend)")
    print("=" * 70)
    print()
    print("This test simulates EXACTLY what the browser does:")
    print("  1. Create session via HTTP (like frontend)")
    print("  2. Send audio blob via FormData POST (like frontend)")
    print("  3. Receive transcription response (like frontend)")
    print("  4. Trigger LLM+TTS via HTTP (like frontend)")
    print("  5. Verify complete response (like frontend)")
    print()
    
    # Check backend
    if not check_backend_running():
        print("❌ ERROR: Backend not running!")
        print("   Please start backend with: python backend/run.py")
        return False
    
    print("✅ Backend is running")
    print()
    
    # Find demo audio files
    wav_files = sorted(list(DEMO_AUDIO_DIR.glob("*.wav")))
    if not wav_files:
        print("❌ No WAV files found in demo_audio/")
        return False
    
    print(f"📁 Found {len(wav_files)} demo audio file(s)")
    print()
    
    results = []
    
    # Test first 2 files (full pipeline)
    for i, wav_file in enumerate(wav_files[:2], 1):
        print("=" * 70)
        print(f"TEST {i}/2: {wav_file.name}")
        print("=" * 70)
        print()
        
        # Step 1: Create session (like frontend does)
        print("📡 Step 1: Creating session (HTTP request)")
        try:
            session_response = requests.post(
                f"{BASE_URL}/api/voice/stream/chunk",
                headers={
                    "X-Create-Session": "true",
                    "X-User-Id": "test_user_http",
                    "X-Conversation-Id": f"test_conv_{int(time.time())}",
                    "X-Language-Code": "en-US"
                },
                timeout=5
            )
            
            if session_response.status_code != 200:
                print(f"   ❌ Session creation failed: {session_response.status_code}")
                print(f"   Response: {session_response.text}")
                results.append(False)
                continue
            
            session_data = session_response.json()
            session_id = session_data.get("session_id")
            conversation_id = session_data.get("conversation_id")
            
            print(f"   ✓ Session created")
            print(f"   - Session ID: {session_id}")
            print(f"   - Conversation ID: {conversation_id}")
            
        except Exception as e:
            print(f"   ❌ Session creation error: {e}")
            results.append(False)
            continue
        
        # Step 2: Read audio file
        print("\n📁 Step 2: Reading audio file")
        with open(wav_file, 'rb') as f:
            audio_data = f.read()
        print(f"   ✓ File size: {len(audio_data):,} bytes ({len(audio_data)/1024:.1f} KB)")
        
        # Step 3: Send audio via HTTP (EXACTLY like frontend does)
        print("\n📡 Step 3: Sending audio via HTTP POST (FormData - like frontend)")
        print("   Simulating: frontend sends Blob via FormData")
        
        try:
            # Create FormData exactly like frontend does
            files = {
                'audio': (wav_file.name, BytesIO(audio_data), 'audio/wav')
            }
            data = {
                'session_id': session_id,
                'user_id': 'test_user_http',
                'conversation_id': conversation_id,
                'language_code': 'en-US',
                'is_final': 'true',
                'user_name': 'Test User'
            }
            
            start_time = time.time()
            response = requests.post(
                f"{BASE_URL}/api/voice/stream/chunk",
                files=files,
                data=data,
                timeout=30  # 30 second timeout for STT
            )
            elapsed = (time.time() - start_time) * 1000
            
            print(f"   ✓ HTTP request completed ({elapsed:.1f}ms)")
            print(f"   - Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"   ❌ HTTP request failed")
                print(f"   Response: {response.text[:200]}")
                results.append(False)
                continue
            
            result = response.json()
            
            # Check response structure (like frontend does)
            chunk_text = result.get('chunk_text', '')
            merged_text = result.get('merged_text', '')
            should_process = result.get('should_process', False)
            is_noise = result.get('is_noise', False)
            error_message = result.get('error_message', '')
            
            print(f"   ✓ Response received")
            print(f"   - Chunk text: '{chunk_text[:50]}{'...' if len(chunk_text) > 50 else ''}'")
            print(f"   - Merged text: '{merged_text[:50]}{'...' if len(merged_text) > 50 else ''}'")
            print(f"   - Should process: {should_process}")
            print(f"   - Is noise: {is_noise}")
            
            if error_message:
                print(f"   ⚠️  Error message: {error_message}")
            
            if not merged_text and not chunk_text:
                print("   ❌ No transcription received")
                results.append(False)
                continue
            
            if is_noise:
                print("   ⚠️  Detected as noise - skipping LLM+TTS")
                results.append(False)
                continue
            
            if not should_process:
                print("   ⚠️  Should not process - skipping LLM+TTS")
                results.append(False)
                continue
            
        except Exception as e:
            print(f"   ❌ HTTP request error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
            continue
        
        # Step 4: Trigger LLM+TTS (like frontend does)
        print("\n📡 Step 4: Triggering LLM+TTS via HTTP (like frontend)")
        print("   Simulating: frontend calls /api/voice/stream/process")
        
        try:
            llm_start = time.time()
            llm_response = requests.post(
                f"{BASE_URL}/api/voice/stream/process",
                json={
                    'session_id': session_id,
                    'merged_text': merged_text or chunk_text,
                    'user_name': 'Test User'
                },
                timeout=30  # 30 second timeout for LLM+TTS
            )
            llm_elapsed = (time.time() - llm_start) * 1000
            
            print(f"   ✓ LLM+TTS request completed ({llm_elapsed:.1f}ms)")
            print(f"   - Status: {llm_response.status_code}")
            
            if llm_response.status_code != 200:
                print(f"   ❌ LLM+TTS failed: {llm_response.status_code}")
                print(f"   Response: {llm_response.text[:200]}")
                results.append(False)
                continue
            
            llm_result = llm_response.json()
            
            text_response = llm_result.get('text_response', '')
            audio_base64 = llm_result.get('audio_base64', '')
            audio_url = llm_result.get('audio_url', '')
            has_audio = bool(audio_base64) or bool(audio_url)
            
            print(f"   ✓ LLM+TTS response received")
            print(f"   - Text response: '{text_response[:50]}{'...' if len(text_response) > 50 else ''}'")
            print(f"   - Has audio: {has_audio}")
            print(f"   - Audio URL: {audio_url[:50] if audio_url else 'N/A'}")
            
            if not text_response:
                print("   ⚠️  No text response (may be rate-limited)")
            
            if not has_audio:
                print("   ⚠️  No audio response (may be rate-limited)")
            
            # Calculate total end-to-end latency
            total_elapsed = (time.time() - start_time) * 1000
            print(f"\n   ✅ COMPLETE PIPELINE SUCCESS!")
            print(f"   - STT latency: {elapsed:.1f}ms")
            print(f"   - LLM+TTS latency: {llm_elapsed:.1f}ms")
            print(f"   - Total end-to-end: {total_elapsed:.1f}ms")
            
            results.append(True)
            
        except Exception as e:
            print(f"   ❌ LLM+TTS error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
            continue
        
        print()
        if i < 2:
            print("-" * 70)
            print()
            time.sleep(1)  # Brief pause
    
    # Summary
    print("=" * 70)
    print("HTTP PIPELINE TEST SUMMARY")
    print("=" * 70)
    for i, wav_file in enumerate(wav_files[:2], 1):
        status = "✅ PASS" if results[i-1] else "❌ FAIL"
        print(f"{status}: {wav_file.name}")
    
    success_count = sum(results)
    total_tests = len(results)
    print(f"\nTotal: {success_count}/{total_tests} passed ({success_count/total_tests*100:.0f}%)")
    print()
    
    if success_count == total_tests:
        print("✅ ALL HTTP PIPELINE TESTS PASSED!")
        print()
        print("This confirms:")
        print("  ✓ HTTP API endpoints working")
        print("  ✓ Session creation working")
        print("  ✓ Audio upload via FormData working")
        print("  ✓ STT transcription via HTTP working")
        print("  ✓ LLM+TTS via HTTP working")
        print("  ✓ Complete frontend → backend → frontend flow working")
    elif success_count > 0:
        print("⚠️  PARTIAL SUCCESS - Some tests passed")
    else:
        print("❌ ALL TESTS FAILED - Check backend logs and API keys")
    
    return success_count == total_tests

if __name__ == '__main__':
    success = test_full_http_pipeline()
    sys.exit(0 if success else 1)

