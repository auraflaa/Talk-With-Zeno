<div align="center">

# Talk With Zeno


[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

</div>

---

A voice-first AI companion that listens with care, notices emotional patterns over time, and offers calm, thoughtful support.

---

## Problem Statement

Most people struggle silently. When they need support the most, they often lack the energy to fill out forms, track moods manually, or seek professional help immediately.

Existing mental health tools tend to be:

* **High-effort** (manual tracking, questionnaires)
* **Reactive** rather than preventive
* **Clinical or overwhelming**
* Not designed for everyday, casual emotional check-ins

### The Challenge

Build an AI companion that:

* Lets users log moods, thoughts, or stress in seconds
* Detects emotional patterns over time
* Responds with personalized reflections or journaling prompts
* Encourages healthy habits
* Does **not** replace mental health professionals

---

## Solution Overview

### Product Demo

[![Talk With Zeno Demo](https://github.com/auraflaa/Talk-With-Zeno/blob/main/Talk%20With%20Zeno.png)](https://drive.google.com/file/d/11wGJnxeEvT0HgcFUpAoBE9nmeOCX0Zux/view?usp=sharing)

> *Click to watch a short demo of the voice-first interaction, streaming pipeline, and personalization flow.*

Talk With Zeno is a voice-first, emotionally intelligent AI companion that enables low-friction emotional expression through natural conversation.

Instead of forms or clinical assessments, users simply speak or type. The system tracks patterns over time using explicit backend memory and responds with gentle reflections and prompts, while maintaining strict boundaries on clinical language.

The intelligence comes not from hidden model memory, but from **explicit context injection and pattern tracking** managed by the backend.

---

## Key Design Principles

* **Voice-first, low-friction interaction** — speaking is easier than typing or filling forms
* **Longitudinal pattern awareness** — emotional patterns matter more than single messages
* **Explicit system memory, stateless language model** — the model is stateless; the system owns memory
* **Non-clinical and non-diagnostic responses** — no diagnosis, no risk scoring, no therapy replacement
* **Clear separation of concerns** — frontend, backend, and AI services are explicitly separated

---

## System Architecture

The system follows a standard **frontend–backend architecture** with managed AI services.

### Components

* **Frontend (React)**: Captures voice/text input, streams audio to backend, plays synthesized responses, maintains session context
* **Backend (Python/Flask)**: Orchestrates AI service calls, manages user context and memory, enforces safety and ethical constraints

### AI Services

* **Speech-to-Text (STT)**: Google Cloud Speech-to-Text (`phone_call` model for optimal latency)
* **Language Model (LLM)**: Gemini 2.5 Flash (primary) with fallback to Gemini 2.0 Flash
* **Text-to-Speech (TTS)**: Groq Orpheus TTS (primary) with Gemini TTS fallback

### Storage

* **File-based JSON storage**: Conversation history and personalization data stored locally
* **In-memory caching**: LLM and TTS responses cached for reduced latency

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

1. **Frontend continuously records audio** with VAD (Web Audio API)
2. **Audio chunks accumulated** in `audioService.speechChunks`
3. **Every 3 seconds**, chunks ≥80KB are sent to `/api/voice/stream/chunk`
4. **Backend accumulates chunks** in `StreamingSession.audio_chunks`
5. **When threshold (80KB) reached or `is_final=true`**, STT processes accumulated audio
6. **If noise detected and previous text exists**, trigger LLM processing
7. **Frontend displays live transcription** as chunks are processed
8. **Final merged text sent** to `/api/voice/stream/process` for LLM → TTS

**Key Configuration:**

* **VAD Silence Duration:** 800ms
* **VAD Min Speech Duration:** 300ms
* **Max Segment Duration:** 10 seconds (300ms overlap)
* **Max Recording Duration:** 120 seconds
* **Audio Format:** WebM → WAV (16kHz mono) via FFmpeg
* **STT Retry Attempts:** 2
* **LLM Timeout:** 60s | **TTS Timeout:** 30s

---

## Pattern Detection & Personalization

Emotional pattern detection is handled **outside the language model** using backend logic over stored JSON records.

### Tracked Patterns

* Repeated themes across sessions
* Changes in emotional intensity
* Usage timing patterns (e.g., late-night check-ins)
* Recurring phrasing indicating persistent concerns

### Personalization Features

* Communication style adaptation
* Topic and goal awareness
* Emotional pattern recognition
* Cross-session conversation context

Patterns are:

* Used only to adapt responses
* Never framed as diagnoses
* Stored as abstracted signals, not raw transcripts

---

## Safety & Ethical Boundaries

Talk With Zeno is **not a therapist** and does not replace professional care.

* No diagnostic language or medical advice
* No crisis intervention or escalation
* Optional, non-urgent suggestions for human support
* Safety rules enforced at the backend (model-agnostic)

---

## Tech Stack

### Frontend

* React 18.3 + TypeScript
* Vite
* Tailwind CSS + DaisyUI
* Framer Motion
* React Markdown

### Backend

* Python 3.11+ (Flask)
* Google Cloud Speech-to-Text
* Google Gemini API
* Groq API (TTS)
* File-based JSON storage

---

## Current Status

### Working

* Streaming STT → LLM → TTS pipeline
* Voice and text modes
* Live transcription
* Personalization and memory
* Backend and frontend logging

### Limitations

* TTS rate limits (free tier)
* File-based storage (prototype scope)
* Single-instance backend

---

## Quick Start

Refer to the **Installation**, **Setup**, and **Testing** sections below to run the prototype locally.

---

## License

MIT

---

## Contact

For issues or contributions, please open a GitHub issue on this repository.
