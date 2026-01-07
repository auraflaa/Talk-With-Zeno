"""
Main Flask API for Talk With Zeno
Handles voice input pipeline: STT -> LLM -> TTS
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import io
import uuid
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
import threading

# Initialize logger
from backend.services.logger_service import get_logger
logger = get_logger()

app = Flask(__name__)

# Increase request timeout for long audio processing
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# CORS configuration - allow all origins for development, restrict in production
allowed_origins = os.getenv('ALLOWED_ORIGINS', '*').split(',')
CORS(app, origins=allowed_origins, supports_credentials=True)

# Rate limiting configuration
# Use in-memory storage for prototype (use Redis for production)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# Global thread pool for background STT processing (shared across all requests)
# This allows STT processing to happen in parallel without blocking other requests
STT_PROCESSOR_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="stt_processor")

# Lazy-load services to ensure env vars are loaded first
# Services will be initialized on first use
def get_services():
    """Get service instances (lazy loading)"""
    # Ensure environment variables are loaded
    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).parent.parent / '.env.local'
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        load_dotenv('.env.local', override=True)
    
    from backend.services.stt_service import get_stt_service
    from backend.services.llm_service import get_llm_service
    from backend.services.tts_service import get_tts_service
    from backend.services.storage_service import get_storage_service
    from backend.services.metrics_service import get_metrics_service
    return {
        'stt': get_stt_service(),
        'llm': get_llm_service(),
        'tts': get_tts_service(),
        'storage': get_storage_service(),
        'metrics': get_metrics_service()
    }

# Cache services after first load
_services_cache = None

def services():
    """Get cached services or initialize them"""
    global _services_cache
    if _services_cache is None:
        _services_cache = get_services()
    return _services_cache


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    svcs = services()
    # Check if STT service has either Groq or Google client available
    stt_available = False
    if svcs['stt']:
        stt_available = (svcs['stt'].groq_client is not None) or (svcs['stt'].google_client is not None)
    llm_available = svcs['llm'].model is not None if svcs['llm'] else False
    tts_available = len(svcs['tts'].providers) > 0 if svcs['tts'] else False
    
    return jsonify({
        "status": "healthy",
        "services": {
            "stt": stt_available,
            "llm": llm_available,
            "tts": tts_available,
            "storage": svcs['storage'] is not None
        },
        "warnings": []
    }), 200


@app.route('/api/user/personalization', methods=['GET', 'PUT'])
def user_personalization():
    """
    Get or update user personalization data.
    
    GET:
      - query params: user_id (required)
      - returns: full personalization JSON for that user
    
    PUT:
      - JSON body: { "user_id": "...", "personalization": { ...partial or full... } }
      - merges provided personalization over existing and persists it
    """
    from backend.services.storage_service import get_storage_service
    storage = get_storage_service()

    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        data = storage.load_personalization(user_id)
        return jsonify(data), 200

    # PUT
    try:
        payload = request.json or {}
    except Exception:
        payload = {}

    user_id = payload.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    existing = storage.load_personalization(user_id)
    updates = payload.get('personalization') or {}

    # Shallow merge top-level, but preserve nested structures like preferences
    merged = {**existing, **{k: v for k, v in updates.items() if k != "preferences"}}
    if "preferences" in updates:
        merged_prefs = {**existing.get("preferences", {}), **updates["preferences"]}
        merged["preferences"] = merged_prefs

    if storage.save_personalization(user_id, merged):
        return jsonify(merged), 200
    return jsonify({"error": "Failed to save personalization"}), 500

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """Get metrics summary for monitoring"""
    try:
        from backend.services.metrics_service import get_metrics_service
        metrics = get_metrics_service()
        summary = metrics.get_metrics_summary()
        
        # Add system info
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            
            summary['system'] = {
                'cpu_percent': cpu_percent,
                'memory_mb': memory_info.rss / 1024 / 1024,
                'memory_percent': process.memory_percent()
            }
        except ImportError:
            summary['system'] = {'error': 'psutil not available'}
        except Exception as e:
            summary['system'] = {'error': str(e)}
        
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/voice/process', methods=['POST'])
@limiter.limit("10 per minute")  # Limit voice processing to 10 requests per minute
def process_voice():
    """
    Main voice processing endpoint
    Pipeline: STT -> LLM -> TTS
    
    Request:
        - audio: Audio file (multipart/form-data)
        - user_id: User identifier
        - conversation_id: Optional conversation ID (creates new if not provided)
        - language_code: Optional language code (default: en-US)
    
    Returns:
        - text_response: LLM text response
        - audio_response: Audio file (MP3)
        - conversation_id: Conversation ID
        - updates_applied: Any personalization updates applied
    """
    try:
        # Get request data
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        # Validate user_id (prevent injection)
        if not isinstance(user_id, str) or len(user_id) > 100 or not user_id.strip():
            return jsonify({"error": "Invalid user_id format"}), 400
        user_id = user_id.strip()
        
        user_name = request.form.get('user_name')  # Optional user name
        if user_name and (not isinstance(user_name, str) or len(user_name) > 100):
            user_name = None  # Ignore invalid user_name
        
        conversation_id = request.form.get('conversation_id')
        if conversation_id:
            # Validate conversation_id
            if not isinstance(conversation_id, str) or len(conversation_id) > 100:
                conversation_id = None  # Ignore invalid conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        language_code = request.form.get('language_code', 'en-US')
        if not isinstance(language_code, str) or len(language_code) > 10:
            language_code = 'en-US'  # Default to en-US if invalid
        
        # Get audio file
        if 'audio' not in request.files:
            return jsonify({"error": "audio file is required"}), 400
        
        audio_file = request.files['audio']
        audio_data = audio_file.read()
        
        # Check audio size and validate
        if len(audio_data) < 500:
            return jsonify({"error": "Audio file too short. Please record for at least 1 second and speak clearly."}), 400
        
        # Validate audio data integrity
        if len(audio_data) > 10 * 1024 * 1024:  # 10MB limit
            return jsonify({"error": "Audio file too large (max 10MB). Please record a shorter message."}), 400
        
        # Detect audio format from filename or content type
        filename = audio_file.filename or 'audio.webm'
        audio_format = 'webm'  # Default
        if filename.endswith('.wav'):
            audio_format = 'wav'
        elif filename.endswith('.webm') or filename.endswith('.opus'):
            audio_format = 'webm'
        
        print(f"Audio validation: size={len(audio_data)} bytes, format={audio_format}, valid=True")
        print(f"Received audio file: {filename}, size: {len(audio_data)} bytes, format: {audio_format}")
        
        # Get services
        svcs = services()
        
        # Step 1: STT - Convert speech to text using chunk-wise processing
        if not svcs['stt'].groq_client and not svcs['stt'].google_client:
            print("ERROR: STT client not initialized")
            return jsonify({
                "error": "Speech-to-Text service not available. Please check GROQ_API_KEY (primary) or GOOGLE_APPLICATION_CREDENTIALS (fallback) in .env.local"
            }), 500
        
        print(f"STT: Starting chunk-wise transcription (format: {audio_format}, size: {len(audio_data)} bytes)")
        print(f"STT: Language code: {language_code}")
        
        # Split audio into chunks for better transcription accuracy
        # Each chunk should be 2-3 seconds of audio
        # For WebM/Opus at ~48kbps, 2 seconds ≈ 12KB, 3 seconds ≈ 18KB
        chunk_size_bytes = 15000  # ~2.5 seconds of audio
        audio_chunks = []
        
        if len(audio_data) > chunk_size_bytes:
            # Split into chunks
            for i in range(0, len(audio_data), chunk_size_bytes):
                chunk = audio_data[i:i + chunk_size_bytes]
                if len(chunk) >= 500:  # Only include chunks with minimum size
                    audio_chunks.append(chunk)
            print(f"STT: Split audio into {len(audio_chunks)} chunks for processing")
        else:
            # Audio is short enough, process as single chunk
            audio_chunks = [audio_data]
            print(f"STT: Audio is short, processing as single chunk")
        
        # Process chunks and merge
        user_text = None
        if len(audio_chunks) > 1:
            # Use chunk-wise processing
            user_text = svcs['stt'].transcribe_chunks(
                audio_chunks,
                language_code=language_code,
                audio_format=audio_format
            )
        else:
            # Single chunk - use regular transcription
            user_text = svcs['stt'].transcribe_audio(
                audio_data,
                language_code=language_code,
                audio_format=audio_format
            )
        
        if not user_text:
            print("ERROR: STT failed - no transcription returned")
            print(f"  Audio size: {len(audio_data)} bytes")
            print(f"  Audio format: {audio_format}")
            print(f"  Language code: {language_code}")
            print(f"  Number of chunks processed: {len(audio_chunks)}")
            return jsonify({
                "error": "Could not transcribe audio. Possible reasons: 1) Audio too short or silent, 2) STT service error, 3) Check backend logs for details"
            }), 400
        
        # Clean and validate transcription
        user_text = user_text.strip()
        
        # Check for very short or meaningless transcriptions (likely noise or silence)
        if len(user_text) < 2:
            print(f"ERROR: Transcription too short ({len(user_text)} chars): '{user_text}' - likely silence or noise")
            return jsonify({
                "error": "No speech detected. Please speak clearly."
            }), 400
        
        # Check for common noise patterns that STT might transcribe
        noise_patterns = ['hmm', 'uh', 'um', 'ah', 'eh', 'oh']
        if user_text.lower() in noise_patterns and len(user_text) <= 3:
            print(f"ERROR: Transcription appears to be noise: '{user_text}'")
            return jsonify({
                "error": "No clear speech detected. Please speak a complete sentence."
            }), 400
        
        print(f"STT: Successfully transcribed: '{user_text}'")
        print(f"STT: Transcription length: {len(user_text)} characters")
        print(f"STT: Transcription will be sent to LLM as user message")
        
        # Step 2: Load conversation history
        conversation = svcs['storage'].load_conversation(user_id, conversation_id)
        conversation_history = conversation.get("messages", []) if conversation else []
        
        # Add user message to history
        user_message = {
            "role": "user",
            "content": user_text,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(user_message)
        
        # Step 3: LLM - Generate response with personalization
        print(f"LLM: Processing voice input for user {user_id}, conversation {conversation_id}")
        print(f"LLM: Transcribed user text: '{user_text}'")
        print(f"LLM: Transcribed text length: {len(user_text)} characters")
        print(f"LLM: Conversation history length: {len(conversation_history)} messages")
        
        # Verify the transcribed text is being passed correctly
        if not user_text or len(user_text.strip()) == 0:
            print("ERROR: Transcribed text is empty - cannot generate LLM response")
            return jsonify({
                "error": "Transcribed text is empty. Please speak clearly and try again."
            }), 400
        
        llm_result = svcs['llm'].generate_response(
            user_id=user_id,
            user_message=user_text,
            conversation_history=conversation_history,
            user_name=user_name
        )
        
        print(f"LLM: Generated response length: {len(llm_result.get('response', ''))} characters")
        
        assistant_response = llm_result["response"]
        updates_applied = llm_result.get("updates_applied", [])
        
        if updates_applied:
            print(f"Applied {len(updates_applied)} personalization updates from voice input")
        else:
            print("No personalization updates in this response")
        
        # Add assistant message to history
        assistant_message = {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(assistant_message)
        
        # Save conversation
        svcs['storage'].save_conversation(user_id, conversation_id, conversation_history)
        
        # Step 4: TTS - Convert text to speech (for voice mode, always generate audio)
        # Split long responses into chunks (Groq TTS has 200 char limit)
        print(f"TTS: Generating audio for response (length: {len(assistant_response)} chars)")
        print(f"TTS: Response text: {assistant_response[:100]}...")
        
        # Handle long responses by splitting into chunks
        max_chunk_size = 200  # Groq TTS limit
        if len(assistant_response) > max_chunk_size:
            # Split by sentences if possible, otherwise by chunks
            import re
            sentences = re.split(r'([.!?]\s+)', assistant_response)
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) <= max_chunk_size:
                    current_chunk += sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        else:
            chunks = [assistant_response]
        
        # Generate audio for each chunk and combine
        audio_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"TTS: Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
            print(f"TTS: Chunk text: {chunk[:50]}...")
            try:
                chunk_audio = svcs['tts'].synthesize_speech(text=chunk)
                if chunk_audio:
                    print(f"TTS: Chunk {i+1} audio generated: {len(chunk_audio)} bytes")
                    audio_chunks.append(chunk_audio)
                else:
                    print(f"TTS: Chunk {i+1} failed - no audio returned")
            except Exception as e:
                print(f"TTS: Error generating audio for chunk {i+1}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Combine audio chunks (simple concatenation for WAV)
        if audio_chunks:
            audio_response = b''.join(audio_chunks)
            print(f"TTS: Combined {len(audio_chunks)} audio chunks into {len(audio_response)} bytes")
        else:
            audio_response = None
        
        print(f"TTS: Audio generation result: {'Success' if audio_response else 'Failed'}")
        if audio_response:
            print(f"TTS: Generated audio size: {len(audio_response)} bytes")
        
        # Return response with audio as base64 if available
        response_data = {
            "text_response": assistant_response,
            "conversation_id": conversation_id,
            "updates_applied": updates_applied,
            "user_text": user_text,
        }
        
        if audio_response:
            import base64
            try:
                audio_base64 = base64.b64encode(audio_response).decode('utf-8')
                print(f"TTS: Base64 encoded audio (length: {len(audio_base64)} chars)")
                response_data["audio_base64"] = audio_base64
                response_data["audio_url"] = f"/api/voice/audio/{conversation_id}/latest?user_id={user_id}"
            except Exception as e:
                print(f"TTS: Error encoding audio to base64: {e}")
                response_data["audio_url"] = None
        else:
            # TTS failed for voice mode - still return text response
            print("⚠️  WARNING: TTS failed to generate audio for voice mode")
            print("   This means users won't hear the response")
            print("   Check:")
            print("   1. GROQ_API_KEY is set in .env.local")
            print("   2. Groq API key is valid")
            print("   3. Check backend logs above for TTS errors")
            response_data["audio_url"] = None
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error processing voice: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/voice/stream/chunk', methods=['POST'])
@limiter.limit("30 per minute")  # Reduced for turn-based STT (one request per utterance)
def process_stream_chunk():
    """
    Turn-based STT endpoint - processes complete utterances (not continuous chunks)
    
    Architecture: Frontend buffers audio until VAD detects speech end, then sends
    ONE complete utterance for transcription. This reduces API calls and server load.
    
    Request:
        - audio: Complete audio utterance (multipart/form-data)
        - session_id: Streaming session ID (required)
        - user_id: User identifier (required)
        - conversation_id: Optional conversation ID
        - language_code: Optional language code (default: en-US)
        - is_final: Should always be true for turn-based STT (default: false for backward compat)
    
    Returns:
        - chunk_text: Transcribed text for the utterance
        - is_noise: True if utterance contains only noise
        - merged_text: Same as chunk_text (for backward compatibility)
        - should_process: True if should send to LLM
        - session_id: Session ID
    """
    try:
        from backend.services.streaming_service import get_streaming_service
        streaming_service = get_streaming_service()
        
        # Get request data - support both form data and headers (for session creation)
        session_id = request.form.get('session_id') or request.headers.get('X-Session-Id') or ''
        user_id = request.form.get('user_id') or request.headers.get('X-User-Id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        user_name = request.form.get('user_name') or request.headers.get('X-User-Name')
        conversation_id = request.form.get('conversation_id') or request.headers.get('X-Conversation-Id')
        language_code = request.form.get('language_code') or request.headers.get('X-Language-Code', 'en-US')
        is_final = request.form.get('is_final', 'false').lower() == 'true'
        
        # Check if this is a session creation request (empty body with X-Create-Session header)
        is_create_session = request.headers.get('X-Create-Session', 'false').lower() == 'true'
        
        # Get or create session
        session = streaming_service.get_session(session_id)
        if not session or is_create_session:
            # Create new session
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            session_id = streaming_service.create_session(user_id, conversation_id, language_code)
            session = streaming_service.get_session(session_id)
            if not session:
                return jsonify({"error": "Failed to create session"}), 500
        
            # If this was a session creation request, return early with just the session_id
            if is_create_session:
                return jsonify({
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "chunk_text": "",
                    "is_noise": False,
                    "merged_text": "",
                    "should_process": False
                }), 200
        
        # Get audio chunk (not required for session creation)
        if 'audio' not in request.files:
            # If no audio but we have a session, return empty response (session is ready)
            if session:
                return jsonify({
                    "session_id": session_id,
                    "conversation_id": session.conversation_id,
                    "chunk_text": "",
                    "is_noise": False,
                    "merged_text": "",
                    "should_process": False
                }), 200
            return jsonify({"error": "audio chunk is required"}), 400
        
        audio_file = request.files['audio']
        audio_data = audio_file.read()
        
        # Handle empty or very small chunks (for noise detection)
        if len(audio_data) < 100:  # Too small to be valid audio
            logger.debug(f"Streaming: Received very small chunk ({len(audio_data)} bytes) - treating as noise/silence")
            # Check if we have previous text chunks to process
            merged_text = session.get_merged_text()
            if merged_text and len(merged_text.strip()) >= 2:
                # We have accumulated text, process it
                return jsonify({
                    "chunk_text": "",
                    "is_noise": True,
                    "merged_text": merged_text,
                    "should_process": True,
                    "session_id": session_id,
                    "conversation_id": session.conversation_id
                }), 200
            else:
                # No accumulated text yet, just mark as noise
                return jsonify({
                    "chunk_text": "",
                    "is_noise": True,
                    "should_process": False,
                    "session_id": session_id,
                    "conversation_id": session.conversation_id
                }), 200
        
        # Allow concurrent processing - don't block new chunks while processing
        # This enables recording while TTS is playing
        # Note: We still mark as processing, but we allow chunks to accumulate
        # The processing flag prevents duplicate processing of the same chunk set
        
        # Mark session as processing
        session.is_processing = True
        
        # Detect audio format
        filename = audio_file.filename or 'audio.webm'
        audio_format = 'webm'
        if filename.endswith('.wav'):
            audio_format = 'wav'
        
        # Get services
        svcs = services()
        
        if not svcs['stt'].groq_client and not svcs['stt'].google_client:
            return jsonify({"error": "STT service not available"}), 500
        
        # Backend VAD: Now supports WebM/Opus conversion to PCM
        # CRITICAL FIX: When is_final=True, frontend already did VAD and sent complete utterance
        # Trust frontend VAD for final chunks, only use backend VAD for intermediate chunks
        use_backend_vad = not is_final  # Only use backend VAD for non-final chunks
        vad_result = None
        
        # For final chunks, trust frontend VAD (frontend already filtered noise)
        # For non-final chunks, use backend VAD to filter noise early
        if use_backend_vad and len(audio_data) >= 1000:  # Lowered threshold from 2KB to 1KB for better detection
            try:
                from backend.services.vad_service import get_vad_service
                vad_service = get_vad_service()
                # VAD service will convert WebM to PCM automatically
                vad_result = vad_service.is_speech(audio_data, sample_rate=16000, audio_format=audio_format)
                logger.debug(f"VAD: Detected speech={vad_result} for {audio_format} chunk ({len(audio_data)} bytes, is_final={is_final})")
                
                # If VAD detects NO speech, treat as noise and skip STT processing
                # BUT: Only do this for non-final chunks (intermediate chunks)
                if not vad_result:
                    logger.info(f"VAD: No speech detected in intermediate chunk ({len(audio_data)} bytes) - treating as noise, skipping STT")
                    merged_text = session.get_merged_text()
                    if merged_text and len(merged_text.strip()) >= 2:
                        # We have accumulated text from previous chunks, process it
                        return jsonify({
                            "chunk_text": "",
                            "is_noise": True,
                            "merged_text": merged_text,
                            "should_process": True,
                            "session_id": session_id,
                            "conversation_id": session.conversation_id
                        }), 200
                    else:
                        # No accumulated text, just mark as noise and skip processing
                        return jsonify({
                            "chunk_text": "",
                            "is_noise": True,
                            "should_process": False,
                            "session_id": session_id,
                            "conversation_id": session.conversation_id
                        }), 200
            except Exception as e:
                logger.warning(f"VAD: Error during speech detection: {e}")
                vad_result = None  # Fall back to STT-based detection
        elif is_final:
            # For final chunks, assume speech (frontend VAD already filtered)
            vad_result = True
            logger.debug(f"VAD: Trusting frontend VAD for final chunk ({len(audio_data)} bytes) - assuming speech")
        
        # Add chunk to session for accumulation (only if valid size AND VAD detected speech)
        # CRITICAL FIX: For final chunks, always accumulate (frontend VAD already filtered)
        # For non-final chunks, use backend VAD to filter noise
        if audio_data and len(audio_data) >= 100:
            # For final chunks, always accumulate (trust frontend VAD)
            # For non-final chunks, only accumulate if VAD detected speech
            should_accumulate = False
            if is_final:
                # Final chunk - trust frontend VAD, always accumulate
                should_accumulate = True
                logger.debug(f"Streaming: Final chunk - trusting frontend VAD, accumulating ({len(audio_data)} bytes)")
            elif vad_result is None or vad_result:  # None = VAD not available, True = speech detected
                # Non-final chunk - use backend VAD result
                should_accumulate = True
                logger.debug(f"Streaming: Backend VAD detected speech, accumulating ({len(audio_data)} bytes)")
            
            if should_accumulate:
                session.add_chunk(audio_data)
            else:
                # VAD detected no speech in non-final chunk - don't accumulate, treat as noise
                logger.debug(f"Streaming: Backend VAD detected no speech in non-final chunk, skipping accumulation ({len(audio_data)} bytes)")
                merged_text = session.get_merged_text() if session.text_chunks else ""
                return jsonify({
                    "chunk_text": "",
                    "is_noise": True,
                    "should_process": bool(merged_text and len(merged_text.strip()) >= 2),
                    "merged_text": merged_text,
                    "session_id": session_id,
                    "conversation_id": session.conversation_id
                })
        else:
            # Empty or very small chunk - treat as noise, don't accumulate
            logger.debug(f"Streaming: Skipping empty/small chunk ({len(audio_data) if audio_data else 0} bytes)")
            merged_text = session.get_merged_text() if session.text_chunks else ""
            return jsonify({
                "chunk_text": "",
                "is_noise": True,
                "should_process": bool(merged_text and len(merged_text.strip()) >= 2),
                "merged_text": merged_text,
                "session_id": session_id,
                "conversation_id": session.conversation_id
            })
        
        # Accumulate chunks before processing - WebM needs larger segments for valid files
        # Balance between accuracy and speed: smaller chunks = faster response
        # 20KB ≈ 2-3 seconds of audio at typical WebM/Opus bitrates (~64kbps)
        # Reduced minimum for faster response while maintaining reasonable accuracy
        total_accumulated = sum(len(chunk) for chunk in session.audio_chunks)
        MIN_CHUNK_SIZE_FOR_STT = 15000  # 15KB minimum for 1.5-2 seconds of audio (faster response, prevent accumulation)
        MAX_CHUNK_SIZE_FOR_STT = 100000  # 100KB maximum per individual chunk (≈6 seconds) - prevent STT errors
        # Note: Total accumulated can be larger - we'll split large accumulated audio into segments
        
        chunk_text = None
        
        # PRIORITY FIX #1: Stop per-chunk STT calls - only process complete utterances
        # Process if:
        # 1. This is the final chunk (complete utterance from frontend VAD)
        # 2. Audio is getting very large (>200KB) - force processing to prevent memory issues
        # Note: We no longer process on MIN_CHUNK_SIZE threshold - frontend sends complete utterances
        should_process = is_final or total_accumulated >= 200000
        
        # If audio is very large, log it for debugging
        if total_accumulated > 200000:
            logger.warning(f"Streaming: Large accumulated audio detected ({total_accumulated} bytes, {total_accumulated/1024:.1f}KB) - will split into segments")
        
        if should_process:
            # IMPORTANT: WebM chunks cannot be simply concatenated - WebM has container format
            # Process individual valid chunks first (most recent first for better accuracy)
            # This avoids creating invalid WebM files from concatenation
            
            # METRICS & LOGGING: Start utterance tracking
            utterance_id = str(uuid.uuid4())
            utterance_start_time = time.time()
            speech_end_time = utterance_start_time  # Approximate - actual is when VAD detected end
            
            from backend.services.metrics_service import get_metrics_service
            metrics = get_metrics_service()
            metrics.start_utterance(utterance_id)
            
            # STRUCTURED LOGGING: Log utterance start
            logger.info(f"Streaming: [UTTERANCE] Start - id={utterance_id}, chunks={len(session.audio_chunks)}, "
                       f"total_bytes={total_accumulated}, is_final={is_final}")
            
            chunk_text = None
            
            try:
                if session.audio_chunks:
                    # DEMO MODE: When is_final=True, frontend sends a complete utterance
                    # The frontend creates a Blob from accumulated chunks and sends it
                    # The session.audio_chunks contains the chunks that were sent
                    # For demo reliability, process all chunks and let merging logic handle it
                    all_chunks = session.audio_chunks  # Use all chunks in order
                    total_size = sum(len(c) for c in all_chunks)
                    logger.info(f"Streaming: DEMO MODE - Processing final utterance ({len(all_chunks)} chunks, {total_size} bytes, {total_size/1024:.1f}KB, is_final={is_final})")
                    
                    logger.info(f"Streaming: Processing complete utterance ({len(all_chunks)} chunks, {total_size} bytes, {total_size/1024:.1f}KB)")
                    
                    # PRIORITY FIX #2: Convert WebM to WAV before STT processing
                    # Never send raw WebM chunks to STT - always convert to WAV first
                    from backend.services.audio_converter import convert_webm_to_wav, validate_audio
                    
                    # Merge all chunks into single audio blob
                    # CRITICAL: WebM chunks can't just be concatenated - they need proper merging
                    # Try pydub first (proper merging), fallback to simple join if pydub fails
                    merged_webm = None
                    try:
                        from pydub import AudioSegment
                        import io
                        
                        # Properly merge WebM chunks using pydub
                        audio_segments = []
                        for chunk_data in all_chunks:
                            if len(chunk_data) < 100:  # Skip very small chunks
                                continue
                            try:
                                chunk_audio = AudioSegment.from_file(io.BytesIO(chunk_data), format="webm")
                                audio_segments.append(chunk_audio)
                            except Exception as e:
                                logger.debug(f"Streaming: Failed to load chunk for merging: {e}")
                                continue
                        
                        if audio_segments:
                            # Concatenate all segments properly
                            merged_audio = sum(audio_segments)
                            # Convert to mono and 16kHz for STT
                            merged_audio = merged_audio.set_channels(1)
                            merged_audio = merged_audio.set_frame_rate(16000)
                            merged_audio = merged_audio.set_sample_width(2)  # 16-bit
                            
                            # Export as WAV (pydub can do this without ffmpeg for WAV)
                            wav_output = io.BytesIO()
                            merged_audio.export(wav_output, format="wav")
                            wav_data = wav_output.getvalue()
                            
                            # Use WAV directly (skip WebM conversion step)
                            logger.info(f"Streaming: Properly merged {len(audio_segments)} WebM chunks using pydub, converted to WAV ({len(wav_data)} bytes)")
                            # Set wav_audio directly and skip conversion
                            wav_audio = wav_data
                            conversion_time = 0  # Already converted
                            merged_webm = None  # Not needed since we have WAV
                        else:
                            # Fallback to simple join if pydub merging fails
                            merged_webm = b''.join(all_chunks)
                            logger.warning(f"Streaming: pydub merging failed, using simple join ({len(merged_webm)} bytes)")
                            wav_audio = None
                    except Exception as e:
                        # If pydub not available or fails, try processing chunks individually
                        logger.warning(f"Streaming: pydub not available for WebM merging: {e}")
                        
                        # DEMO MODE FIX: For demo reliability, use single-chunk approach
                        # When frontend sends a Blob created from multiple chunks, it's already concatenated
                        # Try to use it directly - Groq STT can sometimes handle concatenated WebM
                        # If that fails, fall back to largest chunk
                        if len(all_chunks) == 1:
                            # Single chunk - use it directly (best case)
                            merged_webm = all_chunks[0]
                            logger.info(f"Streaming: Using single WebM chunk ({len(merged_webm)} bytes)")
                            wav_audio = None
                        else:
                            # Multiple chunks - frontend sent a Blob which is already concatenated
                            # CRITICAL: WebM chunks cannot be simply concatenated - they need proper merging
                            # The frontend's Blob() constructor just concatenates bytes, creating invalid WebM
                            # Solution: Use the largest single chunk (most likely to be valid)
                            try:
                                # Find the largest chunk (most likely to contain complete audio data)
                                largest_chunk = max(all_chunks, key=len)
                                total_size = sum(len(c) for c in all_chunks)
                                
                                if len(largest_chunk) > 1000:  # At least 1KB
                                    # Validate the largest chunk has valid WebM header
                                    if len(largest_chunk) >= 4 and largest_chunk[:4] == b'\x1a\x45\xdf\xa3':
                                        merged_webm = largest_chunk
                                        logger.info(f"Streaming: Using largest valid WebM chunk ({len(merged_webm)} bytes from {len(all_chunks)} chunks, total: {total_size} bytes)")
                                        wav_audio = None
                                    else:
                                        # Largest chunk also invalid - try concatenated version as last resort
                                        concatenated = b''.join(all_chunks)
                                        if len(concatenated) >= 4 and concatenated[:4] == b'\x1a\x45\xdf\xa3':
                                            merged_webm = concatenated
                                            logger.warning(f"Streaming: Largest chunk invalid, trying concatenated version ({len(merged_webm)} bytes)")
                                            wav_audio = None
                                        else:
                                            # Both invalid - use largest anyway (might work with STT)
                                            merged_webm = largest_chunk
                                            logger.warning(f"Streaming: Both chunks invalid, using largest anyway ({len(merged_webm)} bytes) - STT may fail")
                                            wav_audio = None
                                else:
                                    logger.error(f"Streaming: All chunks too small (largest: {len(largest_chunk)} bytes)")
                                    merged_webm = None
                                    wav_audio = None
                            except Exception as merge_error:
                                # Fallback: use first chunk if available
                                if all_chunks and len(all_chunks[0]) > 1000:
                                    merged_webm = all_chunks[0]
                                    logger.warning(f"Streaming: Merge failed, using first chunk ({len(merged_webm)} bytes): {merge_error}")
                                    wav_audio = None
                                else:
                                    logger.error(f"Streaming: All merge attempts failed: {merge_error}")
                                    merged_webm = None
                                    wav_audio = None
                    
                    # If we don't have WAV from pydub, try converting WebM to WAV
                    if wav_audio is None:
                        if not merged_webm or len(merged_webm) < 100:
                            logger.error(f"Streaming: [UTTERANCE] {utterance_id} - Failed to merge audio chunks")
                            metrics.record_error('merge_fail')
                            chunk_text = None
                            merged_text = ""
                            is_noise = True
                            should_process = False
                        else:
                            # Convert WebM to WAV (16kHz mono)
                            conversion_start = time.time()
                            logger.info(f"Streaming: Converting WebM to WAV ({len(merged_webm)} bytes)")
                            wav_audio = convert_webm_to_wav(merged_webm, target_sample_rate=16000, target_channels=1)
                            conversion_time = (time.time() - conversion_start) * 1000
                    
                    # If conversion fails, try using WebM directly (STT services can handle WebM)
                    use_webm_directly = False
                    if not wav_audio:
                        logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - WebM to WAV conversion failed, trying WebM directly")
                        # CRITICAL: Validate WebM before using directly
                        # Simple concatenation creates invalid WebM files that STT can't process
                        if merged_webm and len(merged_webm) > 1000:  # At least 1KB
                            # Validate WebM header (EBML header: 0x1A 0x45 0xDF 0xA3)
                            if len(merged_webm) >= 4 and merged_webm[:4] == b'\x1a\x45\xdf\xa3':
                                use_webm_directly = True
                                logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Using WebM directly for STT (size: {len(merged_webm)} bytes, valid header)")
                            else:
                                # Invalid WebM header - but try STT anyway (some services are lenient)
                                logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - Invalid WebM header (Header: {merged_webm[:4].hex() if merged_webm else 'none'}), but trying STT anyway")
                                # Attempt STT with invalid WebM - some services might still work
                                use_webm_directly = True
                                logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Attempting STT with potentially invalid WebM (size: {len(merged_webm)} bytes)")
                        else:
                            logger.error(f"Streaming: [UTTERANCE] {utterance_id} - Audio too small or invalid ({len(merged_webm) if merged_webm else 0} bytes)")
                            metrics.record_error('conversion_fail')
                            chunk_text = None
                            merged_text = ""
                            is_noise = True
                            should_process = False
                    
                    if wav_audio or use_webm_directly:
                        # PRIORITY FIX #6: Validate audio before STT
                        validation_start = time.time()
                        if wav_audio:
                            is_valid, audio_metadata = validate_audio(wav_audio, audio_format='wav')
                        else:
                            # For WebM, do basic validation (size check)
                            is_valid = len(merged_webm) > 1000
                            audio_metadata = {'file_size': len(merged_webm), 'format': 'webm'} if merged_webm else None
                        validation_time = (time.time() - validation_start) * 1000
                        
                        # METRICS: Record validation
                        metrics.record_validation(is_valid)
                        
                        # STRUCTURED LOGGING: Log audio metadata
                        if audio_metadata:
                            logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Audio metadata: "
                                       f"sample_rate={audio_metadata.get('sample_rate', 'unknown')}, "
                                       f"channels={audio_metadata.get('channels', 'unknown')}, "
                                       f"duration_ms={audio_metadata.get('duration_ms', 'unknown')}, "
                                       f"file_size={audio_metadata.get('file_size', 'unknown')}, "
                                       f"valid={is_valid}, conversion_time_ms={conversion_time:.1f}, "
                                       f"validation_time_ms={validation_time:.1f}")
                        
                        # FAILURE HANDLING RULE #1: If validation fails, attempt reconversion once
                        if not is_valid:
                            logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - Audio validation failed, attempting reconversion")
                            # Attempt reconversion once
                            wav_audio = convert_webm_to_wav(merged_webm, target_sample_rate=16000, target_channels=1)
                            if wav_audio:
                                is_valid, audio_metadata = validate_audio(wav_audio, audio_format='wav')
                                metrics.record_validation(is_valid)
                                if not is_valid:
                                    logger.error(f"Streaming: [UTTERANCE] {utterance_id} - Validation failed after reconversion")
                                    metrics.record_error('validation_fail')
                                    # Don't proceed - will return user-friendly message
                                    chunk_text = None
                            else:
                                logger.error(f"Streaming: [UTTERANCE] {utterance_id} - Reconversion also failed")
                                metrics.record_error('conversion_fail')
                                chunk_text = None
                        
                        # DEMO MODE: Disable retry logic for reliability (single attempt only)
                        if wav_audio or use_webm_directly:  # Only proceed if we have valid audio
                            chunk_text = None
                            max_retries = 0  # DEMO: No retries (single attempt only)
                            stt_start_time = time.time()
                            
                            # FAILURE HANDLING RULE #4: STT latency timeout (8 seconds)
                            STT_TIMEOUT_MS = 8000
                            
                            # Determine which audio to use
                            audio_for_stt = wav_audio if wav_audio else merged_webm
                            audio_format_for_stt = 'wav' if wav_audio else 'webm'
                            
                            for retry_attempt in range(max_retries + 1):
                                try:
                                    attempt_start = time.time()
                                    logger.info(f"Streaming: [UTTERANCE] {utterance_id} - STT attempt {retry_attempt + 1}/{max_retries + 1} (format: {audio_format_for_stt})")
                                    
                                    # Check if we've exceeded timeout
                                    elapsed_ms = (time.time() - stt_start_time) * 1000
                                    if elapsed_ms > STT_TIMEOUT_MS:
                                        logger.error(f"Streaming: [UTTERANCE] {utterance_id} - STT timeout ({elapsed_ms:.0f}ms > {STT_TIMEOUT_MS}ms)")
                                        metrics.record_error('stt_timeout')
                                        break
                                    
                                    chunk_text = svcs['stt'].transcribe_audio(
                                        audio_for_stt,
                                        language_code=language_code,
                                        audio_format=audio_format_for_stt
                                    )
                                    
                                    attempt_latency = (time.time() - attempt_start) * 1000
                                    metrics.record_stt_latency(attempt_latency)
                                    
                                    if chunk_text and chunk_text.strip():
                                        logger.info(f"Streaming: [UTTERANCE] {utterance_id} - STT succeeded on attempt {retry_attempt + 1} "
                                                   f"({attempt_latency:.1f}ms): '{chunk_text[:50]}...'")
                                        metrics.record_transcription_success(True)
                                        break
                                    else:
                                        logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - STT attempt {retry_attempt + 1} returned empty")
                                        if retry_attempt < max_retries:
                                            metrics.record_stt_retry()
                                        
                                except Exception as e:
                                    attempt_latency = (time.time() - attempt_start) * 1000
                                    logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - STT attempt {retry_attempt + 1} failed ({attempt_latency:.1f}ms): {e}")
                                    metrics.record_error('stt_error')
                                    if retry_attempt < max_retries:
                                        metrics.record_stt_retry()
                                    
                                # Retry strategy: On failure, try re-converting or splitting
                                if retry_attempt < max_retries and not chunk_text:
                                    if retry_attempt == 0:
                                        # First retry: Re-convert audio (may fix corruption) or try WebM directly
                                        if use_webm_directly:
                                            # Already using WebM directly, try WAV conversion instead
                                            logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Retry 1: trying WAV conversion")
                                            wav_audio = convert_webm_to_wav(merged_webm, target_sample_rate=16000, target_channels=1)
                                            if wav_audio:
                                                audio_for_stt = wav_audio
                                                audio_format_for_stt = 'wav'
                                                use_webm_directly = False
                                            else:
                                                logger.warning(f"Streaming: [UTTERANCE] {utterance_id} - WAV conversion still failed, keeping WebM")
                                        else:
                                            # Try re-converting
                                            logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Retry 1: re-converting audio")
                                            wav_audio = convert_webm_to_wav(merged_webm, target_sample_rate=16000, target_channels=1)
                                            if wav_audio:
                                                audio_for_stt = wav_audio
                                                audio_format_for_stt = 'wav'
                                            else:
                                                # Conversion failed, try WebM directly
                                                logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Re-conversion failed, trying WebM directly")
                                                audio_for_stt = merged_webm
                                                audio_format_for_stt = 'webm'
                                                use_webm_directly = True
                                    elif retry_attempt == 1:
                                        # Second retry: Split into smaller segments
                                        logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Retry 2: splitting into smaller segments")
                                        # TODO: Implement segment splitting for retry
                                        metrics.record_error('stt_empty_after_retries')
                                        break
                            
                            if not chunk_text:
                                logger.error(f"Streaming: [UTTERANCE] {utterance_id} - All STT attempts failed")
                                metrics.record_transcription_success(False)
                                metrics.record_error('stt_empty')
                    
                    # PRIORITY FIX #1: Old parallel chunk processing removed
                    # We now process complete utterances as single WAV files (converted from WebM)
                    # This eliminates per-chunk STT calls and format issues
                    
                    # Fallback: If primary WebM→WAV conversion/STT failed, try pydub merging approach
                    if not chunk_text and len(session.audio_chunks) > 1:
                        logger.info("Streaming: Primary WebM→WAV conversion failed, trying pydub fallback")
                        logger.debug("Streaming: Individual chunks failed, trying merged audio as fallback")
                        
                        # Try to properly merge WebM chunks using pydub (creates valid WebM file)
                        accumulated_audio = None
                        try:
                            # Import pydub for proper audio merging
                            try:
                                from pydub import AudioSegment
                                import io
                                
                                # Convert each chunk to AudioSegment and concatenate properly
                                audio_segments = []
                                # Use all chunks, not just last 5, to maximize chances
                                chunks_to_merge = session.audio_chunks
                                
                                for chunk_idx, chunk_data in enumerate(chunks_to_merge):
                                    if len(chunk_data) < 100:  # Skip very small chunks
                                        continue
                                    try:
                                        # Load WebM chunk as AudioSegment
                                        chunk_audio = AudioSegment.from_file(io.BytesIO(chunk_data), format="webm")
                                        audio_segments.append(chunk_audio)
                                        logger.debug(f"Streaming: Loaded chunk {chunk_idx+1} for merging ({len(chunk_data)} bytes, {len(chunk_audio)}ms)")
                                    except Exception as e:
                                        logger.debug(f"Streaming: Failed to load chunk {chunk_idx+1} for merging: {e}")
                                        continue
                                
                                if audio_segments:
                                    # Concatenate all segments properly
                                    merged_audio = sum(audio_segments)
                                    total_duration_ms = len(merged_audio)
                                    logger.debug(f"Streaming: Merged {len(audio_segments)} chunks into {total_duration_ms}ms audio")
                                    
                                    # For large audio, split into smaller segments before exporting
                                    # Large WebM files can cause issues - split if > 20 seconds (reduced from 30s for better reliability)
                                    MAX_SEGMENT_DURATION_MS = 10000  # 10 seconds (reduced for better STT reliability and faster response)
                                    if total_duration_ms > MAX_SEGMENT_DURATION_MS:
                                        logger.info(f"Streaming: [LARGE_AUDIO] Large audio ({total_duration_ms}ms, {total_duration_ms/1000:.1f}s), splitting into segments")
                                        # Split into segments and try each (process in parallel for speed)
                                        num_segments = (total_duration_ms // MAX_SEGMENT_DURATION_MS) + 1
                                        segment_duration = total_duration_ms // num_segments
                                        
                                        logger.info(f"Streaming: [LARGE_AUDIO] Splitting into {num_segments} segments of ~{segment_duration}ms each")
                                        
                                        # Process segments in parallel for faster transcription
                                        segment_texts = []
                                        segment_start_time = time.time()
                                        
                                        def transcribe_segment(seg_idx, start_ms, end_ms):
                                            """Transcribe a single segment"""
                                            try:
                                                segment = merged_audio[start_ms:end_ms]
                                                wav_output = io.BytesIO()
                                                segment.export(wav_output, format="wav")
                                                segment_audio = wav_output.getvalue()
                                                
                                                logger.info(f"Streaming: [LARGE_AUDIO] Processing segment {seg_idx+1}/{num_segments} ({len(segment_audio)} bytes, {len(segment)}ms)")
                                                result = svcs['stt'].transcribe_audio(
                                                    segment_audio,
                                                    language_code=language_code,
                                                    audio_format='wav'
                                                )
                                                if result and result.strip():
                                                    logger.info(f"Streaming: [LARGE_AUDIO] Segment {seg_idx+1} transcribed: '{result.strip()}'")
                                                    return (seg_idx, result.strip())
                                                else:
                                                    logger.debug(f"Streaming: [LARGE_AUDIO] Segment {seg_idx+1} returned empty")
                                                    return (seg_idx, None)
                                            except Exception as e:
                                                logger.warning(f"Streaming: [LARGE_AUDIO] Segment {seg_idx+1} transcription failed: {e}")
                                                return (seg_idx, None)
                                        
                                        # Process segments in parallel (max 4 at a time to avoid overwhelming STT)
                                        with ThreadPoolExecutor(max_workers=min(4, num_segments)) as segment_executor:
                                            futures = {
                                                segment_executor.submit(transcribe_segment, seg_idx, 
                                                    seg_idx * segment_duration, 
                                                    min((seg_idx + 1) * segment_duration, total_duration_ms)): seg_idx
                                                for seg_idx in range(num_segments)
                                            }
                                            
                                            # Collect results in order
                                            segment_results = {}
                                            for future in as_completed(futures):
                                                seg_idx, text = future.result()
                                                if text:
                                                    segment_results[seg_idx] = text
                                            
                                            # Merge segments in order
                                            for seg_idx in sorted(segment_results.keys()):
                                                if not chunk_text:
                                                    chunk_text = segment_results[seg_idx]
                                                else:
                                                    chunk_text += " " + segment_results[seg_idx]
                                        
                                        segment_elapsed = time.time() - segment_start_time
                                        if chunk_text:
                                            logger.info(f"Streaming: [LARGE_AUDIO] Successfully transcribed large audio in {num_segments} segments ({segment_elapsed:.3f}s): '{chunk_text}'")
                                        else:
                                            logger.warning(f"Streaming: [LARGE_AUDIO] Failed to transcribe any segments from large audio ({num_segments} segments, {segment_elapsed:.3f}s)")
                                    else:
                                        # Small enough - export as WAV directly (more reliable than WebM)
                                        wav_output = io.BytesIO()
                                        merged_audio.export(wav_output, format="wav")
                                        accumulated_audio = wav_output.getvalue()
                                        logger.debug(f"Streaming: Exported merged audio as WAV ({len(accumulated_audio)} bytes)")
                                        
                                        # Try transcription with WAV
                                        try:
                                            chunk_text = svcs['stt'].transcribe_audio(
                                                accumulated_audio,
                                                language_code=language_code,
                                                audio_format='wav'
                                            )
                                            if chunk_text and chunk_text.strip():
                                                logger.info(f"Streaming: Successfully transcribed merged audio (WAV): '{chunk_text.strip()}'")
                                        except Exception as e:
                                            logger.debug(f"Streaming: Merged WAV transcription failed: {e}")
                                            chunk_text = None
                                    
                            except ImportError:
                                logger.debug("Streaming: pydub not available, cannot merge chunks properly")
                                accumulated_audio = None
                            except Exception as e:
                                logger.debug(f"Streaming: Failed to merge chunks with pydub: {e}")
                                accumulated_audio = None
                        except Exception as e:
                            logger.debug(f"Streaming: Error preparing merged audio: {e}")
                            accumulated_audio = None
                
                if chunk_text and chunk_text.strip():
                    chunk_text = chunk_text.strip()
                    
                    # Filter out transcription artifacts and noise
                    # Remove very short transcriptions that are likely noise
                    if len(chunk_text) < 2:
                        logger.debug(f"Streaming: STT returned very short text '{chunk_text}' - treating as noise")
                        chunk_text = None
                    # Filter out common transcription artifacts - only reject exact matches
                    # Don't reject common words like "hello" that are legitimate speech
                    elif chunk_text.lower() in ['transcribe accurately', 'transcriber\'s name', 'transcriber name']:
                        logger.warning(f"Streaming: STT returned transcription artifact '{chunk_text}' - rejecting")
                        chunk_text = None
                    else:
                        logger.info(f"Streaming: STT transcribed successfully: '{chunk_text}' (length: {len(chunk_text)} chars)")
                    # Add transcribed text to session (will prevent duplicates)
                    session.add_text_chunk(chunk_text)
                else:
                    logger.debug(f"Streaming: STT returned empty/None (likely noise/silence or STT error)")
                    chunk_text = None
                
                # CRITICAL: Only clear chunks if transcription succeeded
                # If transcription failed, keep chunks for retry with different approach
                if chunk_text and chunk_text.strip():
                    chunks_cleared = len(session.audio_chunks)
                    chunks_size_before = sum(len(c) for c in session.audio_chunks)
                    session.audio_chunks.clear()
                    
                    # STRUCTURED LOGGING: Log chunk clearing
                    logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Cleared {chunks_cleared} chunks "
                               f"({chunks_size_before} bytes) after successful transcription")
                    
                    # METRICS: Log utterance completion
                    utterance_duration = (time.time() - utterance_start_time) * 1000
                    logger.info(f"Streaming: [UTTERANCE] {utterance_id} - Complete: duration={utterance_duration:.1f}ms, "
                               f"transcript_length={len(chunk_text)}, success=true")
                else:
                    # STRUCTURED LOGGING: Log failure
                    utterance_duration = (time.time() - utterance_start_time) * 1000
                    logger.error(f"Streaming: [UTTERANCE] {utterance_id} - Failed: duration={utterance_duration:.1f}ms, "
                                f"reason=no_transcription")
                    # Keep chunks for retry - don't clear on failure
                    logger.debug(f"Streaming: Keeping {len(session.audio_chunks)} chunks for retry (transcription failed)")
            except Exception as e:
                logger.error(f"Streaming: STT error: {e}", exc_info=True)
                chunk_text = None
                # Don't clear chunks on error - keep them for retry
                logger.debug(f"Streaming: Keeping {len(session.audio_chunks)} chunks after error (will retry)")
            finally:
                # Always reset processing flag
                session.is_processing = False
        else:
            # Not enough audio yet, wait for more chunks
            if total_accumulated > 0:
                print(f"Streaming: Accumulating audio (current: {total_accumulated} bytes, need: {MIN_CHUNK_SIZE_FOR_STT} bytes, max: {MAX_CHUNK_SIZE_FOR_STT} bytes)")
        
        # Check if chunk is noise (empty or very short)
        # CRITICAL FIX: Better noise detection - check multiple factors
        is_noise = False
        should_process = False
        merged_text = ""
        
        # Determine if this is noise based on:
        # 1. No transcription (STT returned empty/None)
        # 2. Very short transcription (< 2 chars) - likely noise artifacts
        # 3. Audio size vs transcription length (very large audio with tiny text = likely noise)
        audio_size = sum(len(c) for c in session.audio_chunks)
        estimated_duration_ms = (audio_size / 8000) * 1000  # ~8KB per second for WebM/Opus
        
        if not chunk_text or len(chunk_text.strip()) < 2:
            # No transcription or very short - likely noise
            is_noise = True
            logger.warning(f"Streaming: No transcription obtained - audio may be too short, corrupted, or STT failed. "
                          f"Chunks: {len(session.audio_chunks)}, Total size: {audio_size} bytes, "
                          f"Estimated duration: {estimated_duration_ms:.0f}ms")
            logger.debug(f"Streaming: Accumulated audio is noise (no text detected, {len(session.audio_chunks)} chunks)")
        elif len(chunk_text.strip()) < 3 and estimated_duration_ms > 2000:
            # Very short transcription (< 3 chars) but long audio (> 2 seconds) = likely noise
            is_noise = True
            logger.warning(f"Streaming: Suspicious transcription - very short text '{chunk_text}' for long audio "
                          f"({estimated_duration_ms:.0f}ms) - treating as noise")
            chunk_text = None  # Clear the suspicious transcription
            
            # If we have previous text chunks, merge and trigger processing
            merged_text = session.get_merged_text()
            if merged_text and len(merged_text.strip()) >= 2:
                should_process = True
                logger.info(f"Streaming: Noise detected, merging {len(session.text_chunks)} text chunks: '{merged_text[:50]}...'")
            
            # Only clear accumulated audio chunks if we successfully processed them
            # If transcription failed, keep chunks for retry
            if chunk_text and chunk_text.strip():
                chunks_cleared = len(session.audio_chunks)
                session.audio_chunks = []  # Clear processed chunks
                logger.info(f"Streaming: Cleared {chunks_cleared} chunks after successful transcription")
            else:
                # Transcription failed - keep chunks for potential retry
                logger.debug(f"Streaming: Keeping {len(session.audio_chunks)} chunks (transcription failed, may retry with next chunk)")
        else:
            # Chunk has text - it was already added to session in the try block above
            chunk_text = chunk_text.strip()
            logger.debug(f"Streaming: Accumulated audio transcribed: '{chunk_text[:50]}...' (already added to session)")
            
            # Clear accumulated audio chunks after successful transcription
            session.audio_chunks = []  # Clear processed chunks
        
        # Force processing if is_final flag is set
        if is_final:
            merged_text = session.get_merged_text()
            if merged_text and len(merged_text.strip()) >= 2:
                should_process = True
                logger.info(f"Streaming: Final chunk, processing merged text: '{merged_text[:50]}...'")
            # Clear all accumulated chunks on final
            session.audio_chunks = []
        
        # Reset processing flag before returning
        session.is_processing = False
        
        # FAILURE HANDLING RULE #2: If STT returns empty, provide user-friendly message
        response_data = {
            "chunk_text": chunk_text or "",
            "is_noise": is_noise,
            "merged_text": merged_text,
            "should_process": should_process,
            "session_id": session_id,
            "conversation_id": session.conversation_id
        }
        
        # Add user-friendly error messages if transcription failed
        if not chunk_text and is_final:
            # Check error type from metrics
            from backend.services.metrics_service import get_metrics_service
            metrics = get_metrics_service()
            error_counts = metrics.error_counts
            
            if error_counts.get('validation_fail', 0) > 0:
                response_data["error_message"] = "I couldn't process the audio, please repeat."
            elif error_counts.get('conversion_fail', 0) > 0:
                response_data["error_message"] = "I couldn't process the audio, please repeat."
            elif error_counts.get('stt_timeout', 0) > 0:
                response_data["error_message"] = "Processing took too long. Please try again."
            else:
                response_data["error_message"] = "I couldn't quite hear that — would you like to repeat?"
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error processing stream chunk: {e}", exc_info=True)
        # Enhanced error recovery: return helpful error message
        error_message = str(e)
        if "timeout" in error_message.lower():
            error_message = "Request timeout - audio processing took too long. Please try again."
        elif "rate limit" in error_message.lower():
            error_message = "Rate limit exceeded - too many requests. Please wait a moment."
        elif "session" in error_message.lower():
            error_message = "Session error - please restart the conversation."
        else:
            error_message = "Error processing audio chunk. Please try again."
        
        return jsonify({
            "error": error_message,
            "chunk_text": "",
            "is_noise": False,
            "should_process": False,
            "session_id": session_id if 'session_id' in locals() else None
        }), 500


@app.route('/api/voice/stream/process', methods=['POST'])
@limiter.limit("20 per minute")  # Limit LLM processing from streaming
def process_streamed_text():
    """
    Process merged text from streaming session with LLM
    Called when noise is detected or final chunk is received
    
    Request:
        - session_id: Streaming session ID (required)
        - merged_text: Merged text from chunks (required)
    
    Returns:
        - text_response: LLM response
        - audio_base64: TTS audio
        - conversation_id: Conversation ID
        - updates_applied: Personalization updates
    """
    try:
        from backend.services.streaming_service import get_streaming_service
        streaming_service = get_streaming_service()
        
        data = request.json
        session_id = data.get('session_id')
        merged_text = data.get('merged_text')
        
        if not session_id or not merged_text:
            return jsonify({"error": "session_id and merged_text are required"}), 400
        
        session = streaming_service.get_session(session_id)
        if not session:
            return jsonify({"error": "Session not found"}), 404
        
        user_id = session.user_id
        conversation_id = session.conversation_id
        user_name = data.get('user_name')  # Optional
        
        # Get services
        svcs = services()
        
        # Load conversation history
        conversation = svcs['storage'].load_conversation(user_id, conversation_id)
        conversation_history = conversation.get("messages", []) if conversation else []
        
        # Add user message
        user_message = {
            "role": "user",
            "content": merged_text,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(user_message)
        
        # Generate LLM response
        print(f"Streaming LLM: Processing merged text: '{merged_text}'")
        llm_start_time = time.time()  # Track LLM start time for metrics
        llm_result = svcs['llm'].generate_response(
            user_id=user_id,
            user_message=merged_text,
            conversation_history=conversation_history,
            user_name=user_name
        )
        
        assistant_response = llm_result["response"]
        updates_applied = llm_result.get("updates_applied", [])
        
        # Add assistant message
        assistant_message = {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(assistant_message)
        
        # Save conversation
        svcs['storage'].save_conversation(user_id, conversation_id, conversation_history)
        
        # Generate TTS
        audio_response = None
        if assistant_response:
            try:
                # Truncate long text for TTS (Groq has 200 char limit)
                tts_text = assistant_response
                if len(tts_text) > 200:
                    # Try to find first sentence
                    sentence_end = tts_text.find('.')
                    if sentence_end > 0 and sentence_end < 200:
                        tts_text = tts_text[:sentence_end + 1]
                    else:
                        # Just truncate to 200 chars
                        tts_text = tts_text[:197] + "..."
                    print(f"Streaming TTS: Text truncated to {len(tts_text)} chars for TTS")
                
                print(f"Streaming TTS: Generating audio for text (length: {len(tts_text)} chars)")
                audio_response = svcs['tts'].synthesize_speech(text=tts_text)
                if audio_response:
                    print(f"Streaming TTS: Audio generated successfully: {len(audio_response)} bytes")
                else:
                    print("Streaming TTS: WARNING - Audio generation returned None")
            except Exception as e:
                print(f"Streaming TTS: Error generating audio: {e}")
                import traceback
                traceback.print_exc()
        
        # METRICS: Calculate end-to-end latency (LLM start → TTS ready)
        tts_ready_time = time.time()
        end_to_end_latency = (tts_ready_time - llm_start_time) * 1000
        
        from backend.services.metrics_service import get_metrics_service
        metrics = get_metrics_service()
        metrics.record_end_to_end_latency(end_to_end_latency)
        
        logger.info(f"Streaming: [METRICS] End-to-end latency: {end_to_end_latency:.1f}ms (LLM+TTS processing)")
        
        logger.info(f"Streaming: [METRICS] End-to-end latency: {end_to_end_latency:.1f}ms (LLM+TTS processing)")
        
        # CRITICAL: Clear ALL accumulated chunks from session after TTS response is ready
        # This prevents old chunks from accumulating and causing large file issues
        # Discard unnecessary chunks after response is ready (as user suggested)
        chunks_before_clear = len(session.audio_chunks)
        total_size_before_clear = sum(len(c) for c in session.audio_chunks) if session.audio_chunks else 0
        session.clear_text_chunks()  # This also clears audio_chunks
        logger.info(f"Streaming: [CLEANUP] Cleared {chunks_before_clear} accumulated audio chunks ({total_size_before_clear/1024:.1f}KB) after TTS response ready")
        
        # Build response
        response_data = {
            "text_response": assistant_response,
            "conversation_id": conversation_id,
            "updates_applied": updates_applied,
            "user_text": merged_text,
        }
        
        if audio_response:
            import base64
            audio_base64 = base64.b64encode(audio_response).decode('utf-8')
            response_data["audio_base64"] = audio_base64
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error processing streamed text: {e}", exc_info=True)
        # Enhanced error recovery: return helpful error message
        error_message = str(e)
        if "timeout" in error_message.lower():
            error_message = "Request timeout - processing took too long. Please try again."
        elif "rate limit" in error_message.lower():
            error_message = "Rate limit exceeded - too many requests. Please wait a moment."
        elif "session" in error_message.lower() or "not found" in error_message.lower():
            error_message = "Session expired or not found. Please restart the conversation."
        elif "llm" in error_message.lower() or "model" in error_message.lower():
            error_message = "AI service temporarily unavailable. Please try again in a moment."
        else:
            error_message = "Error processing request. Please try again."
        
        return jsonify({
            "error": error_message,
            "text_response": "",
            "conversation_id": conversation_id if 'conversation_id' in locals() else None
        }), 500


@app.route('/api/text/process', methods=['POST'])
@limiter.limit("30 per minute")  # Text processing is lighter, allow more requests
def process_text():
    """
    Text processing endpoint
    Pipeline: LLM -> TTS (skips STT)
    
    Request:
        - text: User text message
        - user_id: User identifier
        - conversation_id: Optional conversation ID
        - language_code: Optional language code (default: en-US)
    
    Returns:
        - text_response: LLM text response
        - audio_url: URL to audio response
        - conversation_id: Conversation ID
        - updates_applied: Any personalization updates applied
    """
    try:
        data = request.json
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        user_name = data.get('user_name')  # Optional user name
        user_text = data.get('text')
        if not user_text:
            return jsonify({"error": "text is required"}), 400
        
        conversation_id = data.get('conversation_id') or str(uuid.uuid4())
        language_code = data.get('language_code', 'en-US')
        
        # Get services
        svcs = services()
        
        # Load conversation history
        conversation = svcs['storage'].load_conversation(user_id, conversation_id)
        conversation_history = conversation.get("messages", []) if conversation else []
        
        # Add user message to history
        user_message = {
            "role": "user",
            "content": user_text,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(user_message)
        
        # LLM - Generate response with personalization
        print(f"Processing text input for user {user_id}, conversation {conversation_id}")
        print(f"User message: {user_text[:100]}...")
        print(f"Conversation history length: {len(conversation_history)}")
        
        llm_result = svcs['llm'].generate_response(
            user_id=user_id,
            user_message=user_text,
            conversation_history=conversation_history,
            user_name=user_name
        )
        
        assistant_response = llm_result["response"]
        updates_applied = llm_result.get("updates_applied", [])
        
        print(f"LLM: Final response length: {len(assistant_response)} characters")
        print(f"LLM: Final response (full): {assistant_response}")
        
        if updates_applied:
            print(f"Applied {len(updates_applied)} personalization updates")
        else:
            print("No personalization updates in this response")
        
        # Add assistant message to history
        assistant_message = {
            "role": "assistant",
            "content": assistant_response,
            "timestamp": datetime.now().isoformat()
        }
        conversation_history.append(assistant_message)
        
        # Save conversation
        svcs['storage'].save_conversation(user_id, conversation_id, conversation_history)
        
        # TTS - Optional: Convert text to speech (for text mode, TTS is optional)
        # Only generate audio if requested
        audio_response = None
        generate_audio = data.get('generate_audio', False)  # Default to False for text mode
        
        if generate_audio:
            print(f"TTS: Generating audio for greeting/initial message (length: {len(assistant_response)} chars)")
            print(f"TTS: Available providers: {svcs['tts'].providers}")
            try:
                # Split long text into sentences for TTS (Groq has 200 char limit)
                # For greeting, use first sentence or truncate to 200 chars
                tts_text = assistant_response
                if len(tts_text) > 200:
                    # Try to find first sentence
                    sentence_end = tts_text.find('.')
                    if sentence_end > 0 and sentence_end < 200:
                        tts_text = tts_text[:sentence_end + 1]
                    else:
                        # Just truncate to 200 chars
                        tts_text = tts_text[:197] + "..."
                    print(f"TTS: Text truncated to {len(tts_text)} chars for TTS")
                
                print(f"TTS: Calling synthesize_speech with text: '{tts_text[:50]}...'")
                audio_response = svcs['tts'].synthesize_speech(
                    text=tts_text
                )
                if audio_response:
                    print(f"TTS: Greeting audio generated successfully: {len(audio_response)} bytes")
                else:
                    print("TTS: WARNING - Greeting audio generation returned None")
                    print("   Check GROQ_API_KEY in .env.local")
                    print("   Check backend logs for TTS errors")
                    print("   Available TTS providers:", svcs['tts'].providers)
            except Exception as e:
                print(f"TTS: Error generating greeting audio: {e}")
                import traceback
                traceback.print_exc()
                audio_response = None
        
        # Ensure audio_base64 is always included if generate_audio was requested
        if generate_audio and not audio_response:
            print("TTS: WARNING - generate_audio=True but no audio was generated")
            print("   This may cause the greeting/error message to not play audio")
            print("   Check TTS service logs above for errors")
        
        response_data = {
            "text_response": assistant_response,
            "conversation_id": conversation_id,
            "updates_applied": updates_applied,
        }
        
        if audio_response:
            import base64
            audio_base64 = base64.b64encode(audio_response).decode('utf-8')
            response_data["audio_base64"] = audio_base64
            response_data["audio_url"] = f"/api/voice/audio/{conversation_id}/latest?user_id={user_id}"
        else:
            # No audio requested or TTS failed - this is normal for text mode
            response_data["audio_url"] = None
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error processing text: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/voice/audio/<conversation_id>/latest', methods=['GET'])
def get_latest_audio(conversation_id):
    """
    Get the latest audio response for a conversation
    """
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        # Get services
        svcs = services()
        
        # Load conversation
        conversation = svcs['storage'].load_conversation(user_id, conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        # Get last assistant message
        messages = conversation.get("messages", [])
        last_assistant = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_assistant = msg.get("content")
                break
        
        if not last_assistant:
            return jsonify({"error": "No assistant response found"}), 404
        
        # Generate audio
        audio_data = svcs['tts'].synthesize_speech(
            text=last_assistant
        )
        
        if not audio_data:
            return jsonify({"error": "Could not generate audio"}), 500
        
        # Return audio file (Groq Orpheus returns WAV format)
        return send_file(
            io.BytesIO(audio_data),
            mimetype='audio/wav',
            as_attachment=False
        )
        
    except Exception as e:
        print(f"Error getting audio: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations', methods=['GET'])
@limiter.limit("100 per minute")  # More lenient for listing (lightweight operation)
def list_conversations():
    """List all conversations for a user"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        svcs = services()
        conversations = svcs['storage'].list_user_conversations(user_id)
        return jsonify({"conversations": conversations}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/conversations/<conversation_id>', methods=['GET'])
@limiter.limit("100 per minute")  # More lenient for individual conversation loads (lightweight operation)
def get_conversation(conversation_id):
    """Get a specific conversation"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        svcs = services()
        conversation = svcs['storage'].load_conversation(user_id, conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        
        return jsonify(conversation), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/personalization', methods=['GET'])
def get_personalization():
    """Get user personalization data"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        svcs = services()
        personalization = svcs['storage'].load_personalization(user_id)
        return jsonify(personalization), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/personalization', methods=['PUT'])
def update_personalization():
    """Update user personalization data"""
    try:
        user_id = request.json.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        svcs = services()
        updates = request.json.get('updates', {})
        personalization = svcs['storage'].load_personalization(user_id)
        
        # Apply updates
        personalization.update(updates)
        
        # Save
        success = svcs['storage'].save_personalization(user_id, personalization)
        
        if success:
            return jsonify({"message": "Personalization updated", "data": personalization}), 200
        else:
            return jsonify({"error": "Failed to update personalization"}), 500
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/auth/google', methods=['GET'])
def google_auth():
    """
    Initiate Google OAuth flow
    Redirects user to Google authorization page
    """
    try:
        from backend.services.google_auth import get_google_auth_service
        auth_service = get_google_auth_service()
        
        auth_url = auth_service.get_authorization_url()
        return jsonify({"auth_url": auth_url}), 200
    except Exception as e:
        print(f"Error generating Google auth URL: {e}")
        return jsonify({"error": "Failed to generate authorization URL"}), 500


@app.route('/api/auth/google/callback', methods=['GET'])
def google_auth_callback():
    """
    Handle Google OAuth callback
    Exchanges authorization code for user data
    """
    try:
        from backend.services.google_auth import get_google_auth_service
        auth_service = get_google_auth_service()
        
        code = request.args.get('code')
        if not code:
            return jsonify({"error": "Authorization code not provided"}), 400
        
        # Authenticate user (code → token → profile → SQLite)
        user = auth_service.authenticate_user(code)
        
        if not user:
            return jsonify({"error": "Failed to authenticate user"}), 401
        
        return jsonify({
            "user": user,
            "message": "Authentication successful"
        }), 200
    except Exception as e:
        print(f"Error in Google auth callback: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ==================== Metrics API Endpoints ====================

@app.route('/api/metrics/summary', methods=['GET'])
def get_metrics_summary():
    """Get metrics summary for dashboard"""
    try:
        hours = int(request.args.get('hours', 24))
        svcs = services()
        metrics_service = svcs.get('metrics')
        
        if not metrics_service:
            return jsonify({"error": "Metrics service not available"}), 500
        
        summary = metrics_service.get_metrics_summary(hours=hours)
        return jsonify(summary), 200
    except Exception as e:
        print(f"Error getting metrics summary: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/metrics/timeseries', methods=['GET'])
def get_metrics_timeseries():
    """Get time series data for a specific metric type"""
    try:
        metric_type = request.args.get('type', 'pipeline_calls')  # stt_calls, llm_calls, tts_calls, pipeline_calls
        hours = int(request.args.get('hours', 24))
        group_by = request.args.get('group_by', 'minute')  # minute, hour, second
        
        svcs = services()
        metrics_service = svcs.get('metrics')
        
        if not metrics_service:
            return jsonify({"error": "Metrics service not available"}), 500
        
        timeseries = metrics_service.get_time_series(
            metric_type=metric_type,
            hours=hours,
            group_by=group_by
        )
        
        return jsonify({
            'metric_type': metric_type,
            'hours': hours,
            'group_by': group_by,
            'data': timeseries
        }), 200
    except Exception as e:
        print(f"Error getting time series: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/metrics/models', methods=['GET'])
def get_model_stats():
    """Get statistics per model"""
    try:
        hours = int(request.args.get('hours', 24))
        svcs = services()
        metrics_service = svcs.get('metrics')
        
        if not metrics_service:
            return jsonify({"error": "Metrics service not available"}), 500
        
        summary = metrics_service.get_metrics_summary(hours=hours)
        
        # Extract model-specific stats
        models = {
            'stt_models': summary.get('stt', {}).get('by_model', {}),
            'llm_models': summary.get('llm', {}).get('by_model', {}),
            'tts_providers': summary.get('tts', {}).get('by_provider', {})
        }
        
        return jsonify(models), 200
    except Exception as e:
        print(f"Error getting model stats: {e}")
        return jsonify({"error": str(e)}), 500


# Note: Use backend/run.py to start the server
# This allows proper environment variable loading
if __name__ == '__main__':
    print("Warning: Use 'python backend/run.py' to start the server")
    print("This ensures proper environment variable loading")
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
