"""
Main Flask API for Talk With Zeno
Handles voice input pipeline: STT -> LLM -> TTS
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import io
import uuid
import time
from datetime import datetime

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


@app.route('/api/voice/process', methods=['POST'])
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
def process_stream_chunk():
    """
    Streaming STT endpoint - processes audio chunks continuously
    Returns text for each chunk, or triggers LLM when noise is detected
    
    Request:
        - audio: Audio chunk (multipart/form-data)
        - session_id: Streaming session ID (required)
        - user_id: User identifier (required)
        - conversation_id: Optional conversation ID
        - language_code: Optional language code (default: en-US)
        - is_final: Optional flag to force processing (default: false)
    
    Returns:
        - chunk_text: Transcribed text for this chunk (if any)
        - is_noise: True if chunk contains only noise
        - merged_text: Merged text from all chunks (if noise detected)
        - should_process: True if should send to LLM
        - session_id: Session ID
    """
    try:
        from backend.services.streaming_service import get_streaming_service
        streaming_service = get_streaming_service()
        
        # Get request data
        session_id = request.form.get('session_id') or ''
        user_id = request.form.get('user_id')
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        
        user_name = request.form.get('user_name')
        conversation_id = request.form.get('conversation_id')
        language_code = request.form.get('language_code', 'en-US')
        is_final = request.form.get('is_final', 'false').lower() == 'true'
        
        # Get or create session
        session = streaming_service.get_session(session_id)
        if not session:
            # Create new session
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
            session_id = streaming_service.create_session(user_id, conversation_id, language_code)
            session = streaming_service.get_session(session_id)
            if not session:
                return jsonify({"error": "Failed to create session"}), 500
        
        # Get audio chunk
        if 'audio' not in request.files:
            return jsonify({"error": "audio chunk is required"}), 400
        
        audio_file = request.files['audio']
        audio_data = audio_file.read()
        
        # Handle empty or very small chunks (for noise detection)
        if len(audio_data) < 100:  # Too small to be valid audio
            print(f"Streaming: Received very small chunk ({len(audio_data)} bytes) - treating as noise/silence")
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
        
        # Add chunk to session
        session.add_chunk(audio_data)
        
        # Detect audio format
        filename = audio_file.filename or 'audio.webm'
        audio_format = 'webm'
        if filename.endswith('.wav'):
            audio_format = 'wav'
        
        # Get services
        svcs = services()
        
        if not svcs['stt'].groq_client and not svcs['stt'].google_client:
            return jsonify({"error": "STT service not available"}), 500
        
        # NOTE: Backend VAD (silero-vad/webrtcvad) requires PCM audio, not WebM/Opus
        # We cannot use backend VAD on WebM chunks directly - it will incorrectly reject all audio
        # Instead, let STT process the audio and use STT results to determine if it's noise
        # Frontend VAD is sufficient for initial filtering
        # Backend VAD can be used later if we convert WebM to PCM (requires additional processing)
        use_backend_vad = False  # Disabled for WebM - VAD requires PCM audio
        
        # Add chunk to session for accumulation (only if valid size)
        # Empty or very small chunks create invalid WebM files
        if audio_data and len(audio_data) >= 100:
            session.add_chunk(audio_data)
        else:
            # Empty or very small chunk - treat as noise, don't accumulate
            print(f"Streaming: Skipping empty/small chunk ({len(audio_data) if audio_data else 0} bytes)")
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
        # 30KB ≈ 3-4 seconds of audio at typical WebM/Opus bitrates (~64kbps)
        # Process more frequently to prevent chunks from growing too large and becoming invalid
        total_accumulated = sum(len(chunk) for chunk in session.audio_chunks)
        MIN_CHUNK_SIZE_FOR_STT = 30000  # 30KB minimum for 3-4 seconds of audio (faster processing)
        MAX_CHUNK_SIZE_FOR_STT = 300000  # 300KB maximum (≈20 seconds) - prevent Google STT "too long" errors and invalid WebM
        
        chunk_text = None
        
        # Process if:
        # 1. We have enough accumulated audio (40KB)
        # 2. Chunk is getting too large (1MB) - force processing to prevent errors
        # 3. This is the final chunk
        should_process = total_accumulated >= MIN_CHUNK_SIZE_FOR_STT or total_accumulated >= MAX_CHUNK_SIZE_FOR_STT or is_final
        
        if should_process:
            # Merge all accumulated chunks into one audio segment
            accumulated_audio = b''.join(session.audio_chunks)
            print(f"Streaming: Processing accumulated audio (chunks: {len(session.audio_chunks)}, total size: {len(accumulated_audio)} bytes, format: {audio_format})")
            
            try:
                print(f"Streaming: Calling STT with {len(accumulated_audio)} bytes of {audio_format} audio")
                
                # If chunk is too large, split it into smaller segments
                if len(accumulated_audio) > MAX_CHUNK_SIZE_FOR_STT:
                    print(f"Streaming: WARNING - Chunk too large ({len(accumulated_audio)} bytes), splitting into segments")
                    # Split into 500KB segments (≈30 seconds each)
                    segment_size = 500000
                    segments = [accumulated_audio[i:i+segment_size] for i in range(0, len(accumulated_audio), segment_size)]
                    print(f"Streaming: Split into {len(segments)} segments")
                    
                    # Process first segment only (most recent audio)
                    chunk_text = svcs['stt'].transcribe_audio(
                        segments[-1],  # Use last segment (most recent)
                        language_code=language_code,
                        audio_format=audio_format
                    )
                else:
                    chunk_text = svcs['stt'].transcribe_audio(
                        accumulated_audio,
                        language_code=language_code,
                        audio_format=audio_format
                    )
                
                if chunk_text and chunk_text.strip():
                    chunk_text = chunk_text.strip()
                    print(f"Streaming: STT transcribed successfully: '{chunk_text}' (length: {len(chunk_text)} chars)")
                    # Add transcribed text to session (will prevent duplicates)
                    session.add_text_chunk(chunk_text)
                else:
                    print(f"Streaming: STT returned empty/None (likely noise/silence or STT error)")
                    print(f"Streaming: Check STT service logs above for details")
                    chunk_text = None
                
                # CRITICAL: Clear accumulated chunks after processing to prevent memory buildup and invalid WebM files
                chunks_cleared = len(session.audio_chunks)
                session.audio_chunks.clear()
                print(f"Streaming: Cleared {chunks_cleared} accumulated audio chunks after processing")
            except Exception as e:
                print(f"Streaming: STT error: {e}")
                import traceback
                traceback.print_exc()
                chunk_text = None
                # Clear chunks even on error to prevent accumulation
                session.audio_chunks.clear()
                print(f"Streaming: Cleared accumulated chunks after error")
        else:
            # Not enough audio yet, wait for more chunks
            if total_accumulated > 0:
                print(f"Streaming: Accumulating audio (current: {total_accumulated} bytes, need: {MIN_CHUNK_SIZE_FOR_STT} bytes, max: {MAX_CHUNK_SIZE_FOR_STT} bytes)")
        
        # Check if chunk is noise (empty or very short)
        is_noise = False
        should_process = False
        merged_text = ""
        
        if not chunk_text or len(chunk_text.strip()) < 2:
            # This chunk is noise
            is_noise = True
            print(f"Streaming: Accumulated audio is noise (no text detected, {len(session.audio_chunks)} chunks)")
            
            # If we have previous text chunks, merge and trigger processing
            merged_text = session.get_merged_text()
            if merged_text and len(merged_text.strip()) >= 2:
                should_process = True
                print(f"Streaming: Noise detected, merging {len(session.text_chunks)} text chunks: '{merged_text}'")
            
            # Clear accumulated audio chunks if we processed them (to prevent memory buildup)
            if total_accumulated >= MIN_CHUNK_SIZE_FOR_STT or is_final:
                session.audio_chunks = []  # Clear processed chunks
        else:
            # Chunk has text - it was already added to session in the try block above
            chunk_text = chunk_text.strip()
            print(f"Streaming: Accumulated audio transcribed: '{chunk_text}' (already added to session)")
            
            # Clear accumulated audio chunks after successful transcription
            session.audio_chunks = []  # Clear processed chunks
        
        # Force processing if is_final flag is set
        if is_final:
            merged_text = session.get_merged_text()
            if merged_text and len(merged_text.strip()) >= 2:
                should_process = True
                print(f"Streaming: Final chunk, processing merged text: '{merged_text}'")
            # Clear all accumulated chunks on final
            session.audio_chunks = []
        
        return jsonify({
            "chunk_text": chunk_text or "",
            "is_noise": is_noise,
            "merged_text": merged_text,
            "should_process": should_process,
            "session_id": session_id,
            "conversation_id": session.conversation_id
        }), 200
        
    except Exception as e:
        print(f"Error processing stream chunk: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/voice/stream/process', methods=['POST'])
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
        
        # Clear processed chunks from session
        session.clear_text_chunks()
        
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
        print(f"Error processing streamed text: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/text/process', methods=['POST'])
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
