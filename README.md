# Talk With Zeno

Voice-first AI companion for emotional support and mental well-being.

## Quick Start

### Prerequisites
- Node.js (for frontend)
- Python 3.11+ (for backend)
- API Keys (see Setup below)

### Installation

1. **Install dependencies:**
   ```bash
   npm install
   pip install -r backend/requirements.txt
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env.local
   ```
   Then edit `.env.local` with your API keys (see Setup section below)

3. **Start servers:**
   ```bash
   # Backend (in one terminal)
   python backend/run.py
   
   # Frontend (in another terminal)
   npm run dev
   ```

4. **Access the app:**
   - Frontend: http://localhost:3000
   - Backend: http://localhost:5000

## Setup - API Keys Required

### Required Keys

1. **GEMINI_API_KEY** (Required)
   - Purpose: LLM for conversational intelligence
   - Get from: https://aistudio.google.com/app/apikey
   - Add to `.env.local`: `GEMINI_API_KEY=your_key_here`

2. **GROQ_API_KEY** (Required for TTS)
   - Purpose: Text-to-Speech (primary provider)
   - Get from: https://console.groq.com/
   - Add to `.env.local`: `GROQ_API_KEY=your_key_here`

3. **GOOGLE_APPLICATION_CREDENTIALS** (Required for STT)
   - Purpose: Speech-to-Text service
   - Get from: Google Cloud Console → Service Accounts
   - Download JSON key file, place in project root
   - Add to `.env.local`: `GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json`

### Test Your Setup

Run the test script to verify all services:
```bash
python backend/test_services.py
```

All services should show ✅ when properly configured.

## Architecture

```
Voice Input → STT (Speech-to-Text) → LLM (Gemini) → TTS (Text-to-Speech) → Audio Output
Text Input → LLM (Gemini) → Text Response
```

### Services

- **STT**: Google Cloud Speech-to-Text
- **LLM**: Google Gemini (with fallback models)
- **TTS**: Groq TTS (primary) → Gemini TTS (fallback)
- **Storage**: File-based (JSON files for chats and personalization)

## Features

- Voice and text conversation modes
- Personalization that learns from conversations
- Conversation history storage
- Emotional pattern tracking
- LLM-driven personalization updates

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment instructions.

## Troubleshooting

### Voice Mode Not Working

1. **Check API keys:**
   ```bash
   python backend/test_services.py
   ```

2. **Common issues:**
   - Invalid GEMINI_API_KEY → Get valid key from https://aistudio.google.com/app/apikey
   - Missing GROQ_API_KEY → Get key from https://console.groq.com/
   - Missing GOOGLE_APPLICATION_CREDENTIALS → Set up Google Cloud service account

3. **Check backend logs** for detailed error messages

### Backend Not Starting

- Check Python version: `python --version` (need 3.11+)
- Install dependencies: `pip install -r backend/requirements.txt`
- Check `.env.local` exists and has valid keys

## Project Structure

```
Talk-With-Zeno/
├── backend/           # Python Flask API
│   ├── services/     # STT, LLM, TTS services
│   ├── app.py        # Main API
│   └── run.py        # Server runner
├── components/        # React components
├── services/         # Frontend services
└── .env.local        # Your API keys (gitignored)
```

## License

MIT
