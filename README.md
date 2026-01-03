# Talk With Zeno

A voice-first AI companion that listens with care, notices emotional patterns over time, and offers calm, thoughtful support.

> Built as part of **GDG TechSprint Hackathon**

---

## Problem Statement

Most people struggle silently. When they need support the most, they often lack the energy to fill out forms, track moods manually, or seek professional help immediately.

Existing mental health tools tend to be:
- **High-effort** (manual tracking, questionnaires)
- **Reactive** rather than preventive
- **Clinical or overwhelming**
- Not designed for everyday, casual emotional check-ins

### The Challenge

Build an AI companion that:
- Lets users log moods, thoughts, or stress in seconds
- Detects emotional patterns over time
- Responds with personalized reflections or journaling prompts
- Encourages healthy habits
- Does **not** replace mental health professionals

---

## Solution Overview

Talk With Zeno is a voice-first, emotionally intelligent AI companion that enables low-friction emotional expression through natural conversation.

Instead of forms or clinical assessments, users simply speak or type. The system tracks patterns over time using explicit backend memory and responds with gentle reflections and prompts, while maintaining clear ethical boundaries.

The intelligence comes not from hidden model memory, but from **explicit context injection and pattern tracking** managed by the backend.

---

## Key Design Principles

- **Voice-first, low-friction interaction** — speaking is easier than typing or filling forms
- **Longitudinal pattern awareness** — emotional patterns matter more than single messages
- **Explicit system memory, stateless language model** — the model is stateless; the system owns memory
- **Non-clinical and non-diagnostic responses** — no diagnosis, no risk scoring, no therapy replacement
- **Clear separation of concerns** — frontend, backend, and AI services are explicitly separated

---

## System Architecture

The system follows a standard **frontend–backend architecture** with managed AI services.

### Components

- **Frontend (React)**: Captures voice/text input, streams audio to backend, plays synthesized responses, maintains session context
- **Backend (Python/Flask)**: Orchestrates AI service calls, manages user context and memory, enforces safety and ethical constraints

### AI Services

- **Speech-to-Text (STT)**: Google Cloud Speech-to-Text (`phone_call` model for optimal latency)
- **Language Model (LLM)**: Gemini 2.0 Flash (primary) with fallback to Gemini 2.5 Flash, Gemini 2.0 Flash Lite
- **Text-to-Speech (TTS)**: Groq Orpheus TTS (primary) with Gemini TTS fallback

### Storage

- **File-based JSON storage**: Conversation history and personalization data stored locally
- **In-memory caching**: LLM and TTS responses cached for reduced latency

---

## End-to-End Flow

1. **User speaks or types** in the frontend
2. **Voice input** is converted to text via Speech-to-Text (streaming chunks for continuous listening)
3. **Backend retrieves** relevant conversation context and personalization data
4. **Controlled prompt** is constructed for the language model with system instructions and user context
5. **Model generates** a reflection, prompt, or supportive response
6. **Updated summaries** and pattern metadata are stored
7. **Response is converted** to speech (if voice mode) using TTS
8. **Output is returned** to the user (text and/or audio)

### Streaming Voice Pipeline

For voice mode, the system uses a **streaming architecture**:
- Continuous audio recording with Voice Activity Detection (VAD)
- Chunk-wise STT processing (2.5-second intervals)
- Automatic processing when silence is detected after speech
- Real-time transcription and response generation

---

## Pattern Detection & Personalization

Emotional pattern detection is handled **outside the language model** using backend logic over stored JSON records.

### Tracked Patterns

- **Repeated themes** over multiple sessions (e.g., work stress, relationship concerns)
- **Changes in emotional intensity** over time
- **Usage timing patterns** (e.g., late-night check-ins, high-stress periods)
- **Recurring phrasing or concerns** that indicate persistent issues

### Personalization Features

- **Communication style adaptation**: Formality, message length, punctuation style
- **Topic awareness**: Remembers topics of interest and goals
- **Emotional pattern recognition**: Tracks emotional states and patterns
- **Conversation history**: Maintains context across sessions

These patterns are:
- Used to adapt future responses
- Never surfaced as diagnoses
- Never framed as medical conclusions
- Stored as abstracted signals, not raw transcripts

---

## Safety & Ethical Boundaries

Talk With Zeno is **not a therapist** and does not replace professional care.

### System-Level Safeguards

- **No diagnostic language** — responses avoid clinical terminology
- **No medical advice** — system does not provide health recommendations
- **No crisis intervention** — no automatic escalation or alerts
- **Optional support suggestions** — suggestions to seek human support are non-urgent and optional
- **Backend-enforced constraints** — all safety rules are enforced at the backend level, independent of the LLM

### What This System Is Not

- ❌ Not a clinical mental health tool
- ❌ Not a crisis intervention system
- ❌ Not an agentic or autonomous AI
- ❌ Not a system that stores raw audio or full chat logs by default

---

## Tech Stack

### Frontend
- **React 18.3** with TypeScript
- **Vite** for build tooling
- **Tailwind CSS** + **DaisyUI** for styling
- **Framer Motion** for animations
- **React Markdown** for message formatting

### Backend
- **Python 3.11+** with Flask
- **Google Cloud Speech-to-Text** for STT
- **Google Gemini API** for LLM
- **Groq API** for TTS (primary)
- **File-based storage** (JSON) for conversations and personalization

### Development Tools
- **Voice Activity Detection (VAD)** for speech detection
- **Streaming audio processing** for real-time transcription
- **In-memory caching** for performance optimization

---

## Quick Start

### Prerequisites

- **Node.js** 18+ (for frontend)
- **Python** 3.11+ (for backend)
- **API Keys** (see Setup below)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Talk-With-Zeno
   ```

2. **Install dependencies:**
   ```bash
   # Frontend
   npm install
   
   # Backend
   pip install -r backend/requirements.txt
   ```

3. **Set up environment variables:**
   ```bash
   # Create .env.local file
   cp .env.example .env.local  # If example exists
   ```
   
   Add the following to `.env.local`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key
   GROQ_API_KEY=your_groq_api_key
   GOOGLE_APPLICATION_CREDENTIALS=./config/service-account-key.json
   ```

4. **Get API Keys:**
   - **GEMINI_API_KEY**: Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
   - **GROQ_API_KEY**: Get from [Groq Console](https://console.groq.com/)
   - **GOOGLE_APPLICATION_CREDENTIALS**: Download service account JSON from [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts) and place in `config/` directory

5. **Start the application:**
   
   **Option 1: Use the startup script (Windows PowerShell):**
   ```powershell
   .\scripts\start.ps1
   ```
   
   **Option 2: Manual startup:**
   ```bash
   # Terminal 1: Backend
   python backend/run.py
   
   # Terminal 2: Frontend
   npm run dev
   ```

6. **Access the app:**
   - Frontend: http://localhost:5173
   - Backend: http://localhost:5000

### Test Your Setup

Run the test script to verify all services:
```bash
python backend/tests/test_all_services.py
```

All services should show ✅ when properly configured.

---

## Repository Structure

```
Talk-With-Zeno/
├── backend/                 # Python Flask API
│   ├── services/          # STT, LLM, TTS services
│   │   ├── stt_service.py
│   │   ├── llm_service.py
│   │   ├── tts_service.py
│   │   ├── storage_service.py
│   │   ├── streaming_service.py
│   │   └── cache_service.py
│   ├── tests/             # Test suite
│   │   ├── test_services.py
│   │   ├── test_pipeline.py
│   │   └── deep_analysis.py
│   ├── app.py             # Main API endpoints
│   └── run.py             # Server runner
├── components/            # React components
│   ├── LiveInterface.tsx  # Voice/text interaction
│   ├── TextChat.tsx       # Text mode UI
│   ├── Dashboard.tsx      # Main app container
│   └── MarkdownMessage.tsx # Markdown renderer
├── services/              # Frontend services
│   ├── apiService.ts      # API client
│   └── audioService.ts    # Audio recording/playback
├── scripts/               # Utility scripts
│   └── start.ps1          # Startup script
├── config/                # Configuration files
│   └── service-account-key.json
├── data/                  # Local storage
│   ├── chats/            # Conversation history
│   └── personalization/  # User personalization data
├── performance_results/   # Analysis reports
└── .env.local            # API keys (gitignored)
```

---

## Features

### Voice Mode
- **Continuous listening** with Voice Activity Detection (VAD)
- **Streaming STT** for real-time transcription
- **Automatic processing** when silence is detected
- **TTS audio playback** for responses

### Text Mode
- **Markdown support** for rich text responses
- **Conversation history** persistence
- **Real-time typing indicators**

### Personalization
- **Adaptive communication style** based on user preferences
- **Emotional pattern tracking** over time
- **Topic awareness** and goal tracking
- **CRUD operations** on personalization data via LLM

### Performance Optimizations
- **In-memory caching** for LLM and TTS responses
- **Parallel STT processing** for chunked audio
- **Streaming architecture** for low-latency voice interactions

---

## Troubleshooting

### Voice Mode Not Working

1. **Check API keys:**
   ```bash
   python backend/tests/test_services.py
   ```

2. **Common issues:**
   - Invalid `GEMINI_API_KEY` → Get valid key from [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Missing `GROQ_API_KEY` → Get key from [Groq Console](https://console.groq.com/)
   - Missing `GOOGLE_APPLICATION_CREDENTIALS` → Set up Google Cloud service account and place key in `config/` directory

3. **Check backend logs** for detailed error messages

4. **Run performance analysis:**
   ```bash
   python backend/tests/deep_analysis.py
   ```
   Results saved to `performance_results/DEEP_ANALYSIS.md`

### Backend Not Starting

- Check Python version: `python --version` (need 3.11+)
- Install dependencies: `pip install -r backend/requirements.txt`
- Check `.env.local` exists and has valid keys
- Ensure `config/service-account-key.json` exists

### Frontend Issues

- Clear browser cache and reload
- Check browser console for errors
- Ensure backend is running on `http://localhost:5000`
- Verify microphone permissions are granted

---

## Prototype Scope & Limitations

This repository represents a **hackathon-scale prototype**.

### Current Focus
- ✅ Core voice and text interaction flows
- ✅ Basic pattern detection and personalization
- ✅ Streaming audio processing
- ✅ Safety constraints and ethical boundaries

### Known Limitations
- ⚠️ File-based storage (not production-ready)
- ⚠️ Simplified error handling
- ⚠️ Basic pattern detection (not ML-based)
- ⚠️ Limited scalability (single-instance backend)

### Design Decisions

For the prototype, the system intentionally avoids:
- Agentic AI frameworks
- End-to-end black-box audio models
- Implicit model memory
- Complex database systems

This makes the system:
- Easier to reason about
- Easier to explain to judges
- Easier to control ethically
- Directly aligned with the problem statement

---

## Future Work

- **Richer pattern detection** using ML-based analysis
- **Enhanced safety controls** with monitoring and alerting
- **Multilingual support** for voice and text
- **Production-ready storage** (database migration)
- **Advanced personalization** with fine-tuned models

---

## Performance Analysis

The system includes comprehensive performance analysis tools:

```bash
# Run full system analysis
python backend/tests/deep_analysis.py

# Test individual services
python backend/tests/test_services.py

# Test pipeline
python backend/tests/test_pipeline.py
```

Results are saved to `performance_results/DEEP_ANALYSIS.md` with:
- Service health checks
- Latency measurements
- Model comparison (STT, LLM, TTS)
- Chunk size optimization
- Full pipeline evaluation

---

## Why This Architecture

The architecture is designed for:
- **Clarity**: Each component has a clear responsibility
- **Explainability**: Every behavior maps to a system component
- **Control**: Safety constraints are enforced at the backend level
- **Extensibility**: Easy to add new features or services

This approach ensures the system remains:
- Transparent to users and judges
- Ethically sound
- Technically sound
- Aligned with the problem statement

---

## Intended Outcome

Talk With Zeno provides users with:
- A **calm space** to express themselves
- **Gentle reflection** rather than instruction
- **Awareness of emotional patterns** they may not notice themselves
- **Encouragement** toward healthier habits and human connection

All without adding pressure, labels, or clinical framing.

---

## Team & Acknowledgements

Built as part of **GDG TechSprint Hackathon**.

### Special Thanks
- **Google Cloud** for Speech-to-Text API
- **Google Gemini** for language model capabilities
- **Groq** for fast TTS generation
- **Open source community** for excellent tools and libraries

---

## License

MIT

---

## Contact & Support

For questions, issues, or contributions, please open an issue on the repository.

---

**Remember**: Talk With Zeno is a prototype designed for clarity and learning. It is not a replacement for professional mental health care.
