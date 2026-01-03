"""
Main Flask API for Talk With Zeno
Handles voice input pipeline: STT -> LLM -> TTS
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import io
import uuid
from datetime import datetime

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
    return {
        'stt': get_stt_service(),
        'llm': get_llm_service(),
        'tts': get_tts_service(),
        'storage': get_storage_service()
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
    stt_available = svcs['stt'].client is not None if svcs['stt'] else False
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
        
        user_name = request.form.get('user_name')  # Optional user name
        conversation_id = request.form.get('conversation_id') or str(uuid.uuid4())
        language_code = request.form.get('language_code', 'en-US')
        
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
        
        print(f"Audio validation: size={len(audio_data)} bytes, format={audio_format}, valid=True")
        
        # Detect audio format from filename or content type
        filename = audio_file.filename or 'audio.webm'
        audio_format = 'webm'  # Default
        if filename.endswith('.wav'):
            audio_format = 'wav'
        elif filename.endswith('.webm') or filename.endswith('.opus'):
            audio_format = 'webm'
        
        print(f"Received audio file: {filename}, size: {len(audio_data)} bytes, format: {audio_format}")
        
        # Get services
        svcs = services()
        
        # Step 1: STT - Convert speech to text using chunk-wise processing
        if not svcs['stt'].client:
            print("ERROR: STT client not initialized")
            return jsonify({
                "error": "Speech-to-Text service not available. Please check GOOGLE_APPLICATION_CREDENTIALS in .env.local"
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
            try:
                audio_response = svcs['tts'].synthesize_speech(
                    text=assistant_response
                )
                if audio_response:
                    print(f"TTS: Greeting audio generated: {len(audio_response)} bytes")
                else:
                    print("TTS: WARNING - Greeting audio generation failed")
                    print("   Check GROQ_API_KEY in .env.local")
            except Exception as e:
                print(f"TTS: Error generating greeting audio: {e}")
                import traceback
                traceback.print_exc()
                audio_response = None
        
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


# Note: Use backend/run.py to start the server
# This allows proper environment variable loading
if __name__ == '__main__':
    print("Warning: Use 'python backend/run.py' to start the server")
    print("This ensures proper environment variable loading")
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)
