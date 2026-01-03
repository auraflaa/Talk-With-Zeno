"""
Streaming STT Service
Manages continuous audio chunk processing with state management
"""

from typing import Dict, List, Optional
from datetime import datetime
import threading
import time


class StreamingSession:
    """Manages state for a streaming conversation session"""
    
    def __init__(self, session_id: str, user_id: str, conversation_id: str, language_code: str = 'en-US'):
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.language_code = language_code
        
        # Chunk tracking
        self.audio_chunks: List[bytes] = []  # Raw audio chunks
        self.text_chunks: List[str] = []  # Transcribed text chunks
        self.chunk_timestamps: List[float] = []  # Timestamp for each chunk
        
        # State tracking
        self.last_chunk_time = time.time()
        self.is_processing = False
        self.pending_chunks: List[bytes] = []  # Chunks waiting to be processed
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Metadata
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
    
    def add_chunk(self, audio_data: bytes) -> None:
        """Add a new audio chunk to the session"""
        with self.lock:
            self.audio_chunks.append(audio_data)
            self.chunk_timestamps.append(time.time())
            self.last_chunk_time = time.time()
            self.last_activity = datetime.now()
            self.pending_chunks.append(audio_data)
    
    def add_text_chunk(self, text: str) -> None:
        """Add a transcribed text chunk (prevents duplicates)"""
        with self.lock:
            if text and text.strip():
                text_stripped = text.strip()
                # Prevent duplicate consecutive chunks
                if not self.text_chunks or self.text_chunks[-1] != text_stripped:
                    self.text_chunks.append(text_stripped)
                    self.last_activity = datetime.now()
                else:
                    # Duplicate detected, skip adding
                    print(f"StreamingService: Skipping duplicate text chunk: '{text_stripped[:50]}...'")
    
    def get_pending_chunks(self) -> List[bytes]:
        """Get and clear pending chunks"""
        with self.lock:
            chunks = self.pending_chunks.copy()
            self.pending_chunks = []
            return chunks
    
    def get_merged_text(self) -> str:
        """Get merged text from all text chunks (removes duplicates)"""
        with self.lock:
            if not self.text_chunks:
                return ""
            
            # Remove exact duplicates while preserving order
            seen = set()
            unique_chunks = []
            for chunk in self.text_chunks:
                # Normalize for comparison (lowercase, no punctuation)
                import re
                normalized = re.sub(r'[.!?,;:\s]+', ' ', chunk.lower()).strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    unique_chunks.append(chunk)
            
            # Merge with spaces
            merged = " ".join(unique_chunks)
            # Clean up multiple spaces
            merged = re.sub(r'\s+', ' ', merged).strip()
            return merged
    
    def clear_text_chunks(self) -> None:
        """Clear all text chunks (after processing)"""
        with self.lock:
            self.text_chunks = []
            self.audio_chunks = []
            self.chunk_timestamps = []
    
    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if session is stale (no activity for timeout)"""
        with self.lock:
            elapsed = (datetime.now() - self.last_activity).total_seconds()
            return elapsed > timeout_seconds


class StreamingService:
    """Manages streaming STT sessions"""
    
    def __init__(self):
        self.sessions: Dict[str, StreamingSession] = {}
        self.lock = threading.Lock()
    
    def create_session(self, user_id: str, conversation_id: str, language_code: str = 'en-US') -> str:
        """Create a new streaming session"""
        import uuid
        session_id = str(uuid.uuid4())
        
        with self.lock:
            session = StreamingSession(session_id, user_id, conversation_id, language_code)
            self.sessions[session_id] = session
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[StreamingSession]:
        """Get a session by ID"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> None:
        """Delete a session"""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
    
    def cleanup_stale_sessions(self, timeout_seconds: int = 300) -> None:
        """Remove stale sessions"""
        with self.lock:
            stale_ids = [
                sid for sid, session in self.sessions.items()
                if session.is_stale(timeout_seconds)
            ]
            for sid in stale_ids:
                del self.sessions[sid]
            if stale_ids:
                print(f"StreamingService: Cleaned up {len(stale_ids)} stale sessions")


# Global singleton instance
_streaming_service = None

def get_streaming_service() -> StreamingService:
    """Get the global streaming service instance"""
    global _streaming_service
    if _streaming_service is None:
        _streaming_service = StreamingService()
    return _streaming_service

