# Backend API - Talk With Zeno

Flask backend implementing the voice pipeline: **STT → LLM → TTS**

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables in .env.local
# GEMINI_API_KEY, GROQ_API_KEY, GOOGLE_APPLICATION_CREDENTIALS

# Run server
python run.py
```

Server runs on http://localhost:5000

## API Endpoints

### POST `/api/voice/process`
Process voice input: STT → LLM → TTS

**Request:**
- `audio`: Audio file (multipart/form-data)
- `user_id`: User identifier (required)
- `conversation_id`: Optional

**Response:**
```json
{
  "text_response": "LLM response",
  "conversation_id": "uuid",
  "user_text": "transcribed text",
  "audio_base64": "base64_encoded_audio",
  "updates_applied": []
}
```

### POST `/api/text/process`
Process text input: LLM only (no TTS)

**Request:**
```json
{
  "text": "user message",
  "user_id": "user_123",
  "conversation_id": "optional",
  "generate_audio": false
}
```

### GET `/api/health`
Check service status

### GET `/api/conversations?user_id=xxx`
List user conversations

### GET `/api/personalization?user_id=xxx`
Get user personalization data

## Services

### STT Service (`services/stt_service.py`)
- Groq Whisper (primary): `whisper-large-v3-turbo` (fast) or `whisper-large-v3` (accurate)
- Google Cloud Speech-to-Text (fallback): `phone_call` model
- Converts audio (WebM/WAV/M4A) to text with chunk-wise processing
- Automatic fallback on rate limits or errors
- Requires: `GROQ_API_KEY` (primary) or `GOOGLE_APPLICATION_CREDENTIALS` (fallback)

### LLM Service (`services/llm_service.py`)
- Google Gemini models with fallback
- Models: gemini-2.0-flash (primary, optimized), gemini-2.5-flash, gemini-2.0-flash-lite, gemini-2.5-pro (with fallback)
- Includes personalization context and response caching
- Can update personalization via commands: `[ADD_TOPIC:"..."], [ADD_GOAL:"..."], etc.`

### TTS Service (`services/tts_service.py`)
- Groq TTS (primary): `canopylabs/orpheus-v1-english` with "troy" voice
- Gemini TTS (fallback): `gemini-2.5-flash-tts`, `gemini-2.5-pro-tts`
- Includes audio response caching
- Requires: `GROQ_API_KEY` or `GEMINI_API_KEY`

### Storage Service (`services/storage_service.py`)
- Chat history: `data/chats/{user_id}/{conversation_id}.json`
- Personalization: `data/personalization/{user_id}.json`

## Database

SQLite database for user identity (`data/zeno.db`)

Initialize:
```bash
python scripts/init_db.py
```

## Testing

Test services and pipeline:
```bash
# Comprehensive service test (STT, LLM, TTS, Storage, Database, API)
python backend/tests/test_services.py

# End-to-end pipeline test (text, voice, storage, audio files)
python backend/tests/test_pipeline.py

# Deep production-grade analysis (STT, LLM, TTS, chunk sizes, full pipeline)
python backend/tests/deep_analysis.py
```

## Voice Activity Detection (VAD)

The backend includes a VAD service (`services/vad_service.py`) that can detect speech vs noise. Currently, the frontend uses Web Audio API for VAD, but the backend service is available for future use.

**Available Libraries:**
- **silero-vad**: ML-based, highest accuracy (recommended)
- **webrtcvad**: Fast, lightweight fallback
- **Simple energy detection**: Basic fallback if libraries unavailable

**Note:** VAD is currently implemented in the frontend (`services/audioService.ts`) using Web Audio API for real-time processing.

## Environment Variables

Required in `.env.local`:
- `GEMINI_API_KEY` - For LLM
- `GROQ_API_KEY` - For TTS (primary)
- `GROQ_API_KEY` - For STT (primary) and TTS (primary) - same key for both
- `GOOGLE_APPLICATION_CREDENTIALS` - For STT fallback (path to service account JSON)
- `DATABASE_PATH` - SQLite path (default: `./data/zeno.db`)

### Google OAuth (Optional)
- `VITE_GOOGLE_CLIENT_ID` - Google OAuth Client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth Client Secret
- `GOOGLE_REDIRECT_URI` - OAuth redirect URI (default: `http://localhost:3000/auth/callback`)

**Setup Google OAuth:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:3000/auth/callback`
4. Copy Client ID and Secret to `.env.local`
