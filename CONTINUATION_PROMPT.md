s# Continuation Prompt for New Context Window

Use this prompt when starting a new session to continue development on the Talk With Zeno project.

---

## Context Setup

I'm working on **Talk With Zeno**, a voice-first AI companion built for the GDG TechSprint Hackathon. The project is a React + TypeScript frontend with a Flask (Python) backend, using Google Gemini (LLM), Google Speech-to-Text (STT), and Groq Orpheus (TTS).

## Current Project State

**Status:** ✅ Functional with production-ready logging and monitoring

**Key Features Working:**
- Text mode with LLM responses
- Voice mode with streaming STT → LLM → TTS pipeline
- Live transcription display
- VAD for speech detection
- Greeting pre-generation and caching
- Personalization with CRUD operations
- Markdown rendering in responses
- Production logging (backend + frontend)
- Sentry error monitoring
- Metrics dashboard
- Comprehensive test suite

## Architecture Overview

**Frontend:**
- React + TypeScript + Vite
- Main component: `components/LiveInterface.tsx` (most complex, handles voice/text interaction)
- Services: `apiService.ts`, `audioService.ts`, `greetingService.ts`, `logger.ts`, `sentry.ts`
- Streaming audio with chunk-wise STT processing

**Backend:**
- Flask (Python)
- Services: `stt_service.py`, `llm_service.py`, `tts_service.py`, `storage_service.py`, `streaming_service.py`, `cache_service.py`, `metrics_service.py`, `logger_service.py`, `sentry_service.py`, `vad_service.py`
- File-based JSON storage for conversations and personalization
- SQLite for user management

**AI Services:**
- **STT:** Google `phone_call` model (primary), Groq Whisper (fallback)
- **LLM:** `gemini-2.0-flash` (primary), with fallback chain
- **TTS:** Groq Orpheus "troy" voice (primary), Gemini TTS (fallback)

## Critical Implementation Details

### Streaming STT Flow
1. Frontend continuously records audio with VAD (Web Audio API)
2. Audio chunks accumulated in `audioService.speechChunks`
3. Every 3 seconds, chunks ≥80KB are sent to `/api/voice/stream/chunk`
4. Backend accumulates chunks in `StreamingSession.audio_chunks`
5. When threshold (80KB) reached or `is_final=true`, STT processes accumulated audio
6. If noise detected and previous text exists, trigger LLM processing
7. Frontend displays live transcription as chunks are processed
8. Final merged text sent to `/api/voice/stream/process` for LLM → TTS

### Key Configuration Values
- **Processing Model:** Complete utterances (frontend buffers, sends one request per utterance)
- **VAD Silence Duration:** 800ms (frontend detects speech end)
- **VAD Min Speech Duration:** 300ms (filters noise)
- **Max Segment Duration:** 10 seconds (long utterances split with 300ms overlap)
- **Max Recording Duration:** 120 seconds (auto-resets after processing)
- **Audio Format:** WebM→WAV conversion (16kHz mono) before STT
- **STT Retry Attempts:** 2 (re-convert, then split)
- **STT Timeout:** 60 seconds
- **LLM Timeout:** 60 seconds
- **TTS Timeout:** 30 seconds

### Personalization System
- LLM can modify personalization via commands: `[ADD_TOPIC:"..."], [DELETE_TOPIC:"..."], [EDIT_GOAL:"..."], etc.`
- User name passed through entire pipeline
- System prompt includes personalization context
- Communication style adapts based on user preferences

## Important Files

**Documentation:**
- `PROJECT_HISTORY.md` - Complete development history (READ THIS FIRST)
- `README.md` - Main project documentation
- `LOGGING.md` - Logging and error monitoring guide
- `backend/README.md` - Backend API documentation

**Key Code Files:**
- `components/LiveInterface.tsx` - Voice/text interaction (most complex)
- `services/audioService.ts` - Audio recording, playback, VAD
- `backend/app.py` - Flask app, API endpoints
- `backend/services/llm_service.py` - LLM with personalization
- `backend/services/stt_service.py` - STT with Google + Groq
- `backend/services/tts_service.py` - TTS with Groq + Gemini

**Test Files:**
- `backend/tests/test_services.py` - Service tests
- `backend/tests/test_pipeline.py` - Pipeline tests
- `backend/tests/deep_analysis.py` - Performance analysis

## Environment Variables Required

```bash
# LLM
GEMINI_API_KEY=your_gemini_api_key

# STT (Primary: Google, Fallback: Groq)
GOOGLE_APPLICATION_CREDENTIALS=config/service-account-key.json
GROQ_API_KEY=your_groq_api_key

# TTS (Primary: Groq, Fallback: Gemini)
GROQ_API_KEY=your_groq_api_key  # Same as STT
GEMINI_API_KEY=your_gemini_api_key  # Same as LLM

# Database
DATABASE_PATH=data/zeno.db

# Logging (Optional)
LOG_LEVEL=INFO
VITE_LOG_LEVEL=INFO

# Sentry (Optional)
SENTRY_DSN=https://your-dsn@sentry.io/project-id
VITE_SENTRY_DSN=https://your-dsn@sentry.io/project-id
VITE_APP_VERSION=1.0.0
```

## Development Workflow

1. **Start Application:**
   ```bash
   .\scripts\start.ps1
   ```
   - Backend: http://localhost:5000
   - Frontend: http://localhost:5173
   - Dashboard: `dashboard/index.html`

2. **Run Tests:**
   ```bash
   python backend/tests/test_services.py
   python backend/tests/test_pipeline.py
   python backend/tests/deep_analysis.py
   ```

3. **Check Logs:**
   - Backend: `logs/zeno_backend.log` (production) or console
   - Frontend: Browser console
   - Sentry: Dashboard at sentry.io

## Known Limitations

1. **Backend VAD:** ✅ Fixed - Now supports WebM/Opus conversion to PCM for VAD processing. ✅ webrtcvad installed and working (fallback VAD library)
2. **Storage:** File-based JSON (not scalable for production) - Intentionally kept for prototype
3. **Database:** No migration system yet - Intentionally kept for prototype
4. **Edge Cases:** ✅ Fixed - Improved handling of empty chunks, timeouts, concurrent requests, and duplicate chunks
5. **Rate Limiting:** ✅ Implemented - Added Flask-Limiter with configurable limits per endpoint
6. **Error Recovery:** ✅ Enhanced - Better error messages, retry logic, and session cleanup
7. **VAD Parameters:** ✅ Updated - Currently set to 800ms silence detection (optimized for responsiveness) and 300ms minimum speech duration - prevents 19+ second accumulations while filtering noise

## Recent Changes (Last Session)

1. ✅ Consolidated test files (8 → 3)
2. ✅ Consolidated markdown files (11 → 6)
3. ✅ Created comprehensive `PROJECT_HISTORY.md`
4. ✅ Production logging and Sentry integration complete
5. ✅ Metrics dashboard functional
6. ✅ Codebase cleanup and organization complete

## Latest Improvements (Current Session)

1. ✅ **Backend VAD for WebM:** Added WebM/Opus to PCM conversion using pydub, enabling backend VAD on WebM audio
2. ✅ **Rate Limiting:** Implemented Flask-Limiter with per-endpoint limits (voice: 10/min, streaming chunks: 30/min, text: 30/min)
3. ✅ **Enhanced Error Recovery:** Improved error messages, better timeout handling, session cleanup, and graceful degradation
4. ✅ **Streaming Edge Cases:** Fixed duplicate chunk processing, concurrent request handling, memory management (chunk limits), and session staleness detection
5. ✅ **Periodic Cleanup:** Added background thread for automatic cleanup of stale streaming sessions (every 5 minutes)
6. ✅ **VAD Improvements:** Increased silence duration from 800ms to 1500ms to prevent premature speech end detection
7. ✅ **Chunk Clearing:** Implemented automatic chunk clearing after TTS response ready to prevent large file accumulation
8. ✅ **Max Recording Duration:** Increased from 60s to 120s with automatic timer reset after successful processing
9. ✅ **Parallel Processing Verification:** Added detailed logging with timestamps to verify parallel STT processing
10. ✅ **Large Audio Processing:** Improved splitting strategy (20s segments) with parallel processing for faster transcription
11. ✅ **Parallel Processing Limits:** Limited to most recent 10 chunks for faster, more efficient processing

## Next Steps (Future Work)

- Connection pooling (for production database)
- Production deployment configuration
- Advanced personalization features
- WebSocket support for real-time streaming
- Multi-language support

## Important Notes

1. **Model Priority:** Always prioritize "flash" models for latency
2. **Caching:** Simple queries are cached, complex ones are not
3. **Streaming:** Chunks are accumulated until threshold (80KB) or final flag
4. **VAD:** Frontend VAD is primary, backend VAD is optional
5. **Error Handling:** Always provide helpful error messages
6. **Personalization:** User name is passed through entire pipeline
7. **Greeting:** Pre-generated and cached for immediate playback
8. **Code Quality:** Follow existing patterns, maintain consistency

## When Making Changes

1. **Read `PROJECT_HISTORY.md` first** to understand the evolution
2. **Check existing code patterns** before implementing new features
3. **Update tests** when adding new functionality
4. **Update documentation** when changing behavior
5. **Use structured logging** instead of print/console.log
6. **Handle errors gracefully** with helpful messages
7. **Maintain backward compatibility** when possible

## Common Issues & Solutions

1. **STT not working:** Check `GOOGLE_APPLICATION_CREDENTIALS` path, verify service account key
2. **LLM not responding:** Check `GEMINI_API_KEY`, verify API key is valid
3. **TTS not playing:** Check `GROQ_API_KEY`, verify audio playback permissions
4. **Streaming issues:** Check chunk size thresholds, verify backend is receiving chunks
5. **VAD not detecting speech:** Check VAD parameters, verify microphone permissions

---

**Use this context to continue development. Always refer to `PROJECT_HISTORY.md` for detailed information about past decisions and implementations.**

