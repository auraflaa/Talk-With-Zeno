"""
Metrics Service for Audio Processing Pipeline
Tracks transcription success rate, latency, retry rates, and system health
"""

import time
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
import threading

class MetricsService:
    """Tracks metrics for audio processing pipeline"""
    
    def __init__(self):
        self.lock = threading.Lock()
        
        # Transcription metrics
        self.total_utterances = 0
        self.successful_transcriptions = 0
        self.failed_transcriptions = 0
        
        # Latency metrics (in milliseconds)
        self.stt_latencies: deque = deque(maxlen=100)  # Last 100 STT latencies
        self.end_to_end_latencies: deque = deque(maxlen=100)  # Last 100 end-to-end latencies
        
        # Retry metrics
        self.total_stt_attempts = 0
        self.stt_retries = 0
        self.stt_requests_per_minute: deque = deque(maxlen=60)  # Track last 60 seconds
        
        # Validation metrics
        self.total_validations = 0
        self.validation_failures = 0
        
        # Error tracking
        self.error_counts: Dict[str, int] = {}
        
        # Current utterance tracking
        self.current_utterance_id: Optional[str] = None
        self.utterance_start_time: Optional[float] = None
        
    def start_utterance(self, utterance_id: str) -> None:
        """Mark start of utterance processing"""
        with self.lock:
            self.current_utterance_id = utterance_id
            self.utterance_start_time = time.time()
            self.total_utterances += 1
    
    def record_stt_latency(self, latency_ms: float) -> None:
        """Record STT latency for an utterance"""
        with self.lock:
            self.stt_latencies.append(latency_ms)
            self.total_stt_attempts += 1
            self.stt_requests_per_minute.append(time.time())
    
    def record_stt_retry(self) -> None:
        """Record that a retry was needed"""
        with self.lock:
            self.stt_retries += 1
    
    def record_transcription_success(self, success: bool) -> None:
        """Record transcription success or failure"""
        with self.lock:
            if success:
                self.successful_transcriptions += 1
            else:
                self.failed_transcriptions += 1
    
    def record_end_to_end_latency(self, latency_ms: float) -> None:
        """Record end-to-end latency (speech end → TTS start)"""
        with self.lock:
            self.end_to_end_latencies.append(latency_ms)
    
    def record_validation(self, success: bool) -> None:
        """Record audio validation result"""
        with self.lock:
            self.total_validations += 1
            if not success:
                self.validation_failures += 1
    
    def record_error(self, error_type: str) -> None:
        """Record an error by type"""
        with self.lock:
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def get_transcription_success_rate(self) -> float:
        """Get transcription success rate percentage"""
        with self.lock:
            total = self.successful_transcriptions + self.failed_transcriptions
            if total == 0:
                return 0.0
            return (self.successful_transcriptions / total) * 100.0
    
    def get_avg_stt_latency(self) -> float:
        """Get average STT latency in milliseconds"""
        with self.lock:
            if len(self.stt_latencies) == 0:
                return 0.0
            return sum(self.stt_latencies) / len(self.stt_latencies)
    
    def get_avg_end_to_end_latency(self) -> float:
        """Get average end-to-end latency in milliseconds"""
        with self.lock:
            if len(self.end_to_end_latencies) == 0:
                return 0.0
            return sum(self.end_to_end_latencies) / len(self.end_to_end_latencies)
    
    def get_retry_rate(self) -> float:
        """Get retry rate percentage"""
        with self.lock:
            if self.total_stt_attempts == 0:
                return 0.0
            return (self.stt_retries / self.total_stt_attempts) * 100.0
    
    def get_validation_failure_rate(self) -> float:
        """Get validation failure rate percentage"""
        with self.lock:
            if self.total_validations == 0:
                return 0.0
            return (self.validation_failures / self.total_validations) * 100.0
    
    def get_stt_requests_per_minute(self) -> int:
        """Get current STT requests per minute"""
        with self.lock:
            now = time.time()
            # Count requests in last 60 seconds
            recent_requests = [t for t in self.stt_requests_per_minute if now - t < 60]
            return len(recent_requests)
    
    def get_metrics_summary(self) -> Dict:
        """Get complete metrics summary (optimized to avoid nested locks)"""
        with self.lock:
            # Calculate all values while holding the lock once
            total_transcriptions = self.successful_transcriptions + self.failed_transcriptions
            transcription_success_rate = (self.successful_transcriptions / total_transcriptions * 100.0) if total_transcriptions > 0 else 0.0
            
            avg_stt_latency = (sum(self.stt_latencies) / len(self.stt_latencies)) if len(self.stt_latencies) > 0 else 0.0
            avg_e2e_latency = (sum(self.end_to_end_latencies) / len(self.end_to_end_latencies)) if len(self.end_to_end_latencies) > 0 else 0.0
            
            retry_rate = (self.stt_retries / self.total_stt_attempts * 100.0) if self.total_stt_attempts > 0 else 0.0
            validation_failure_rate = (self.validation_failures / self.total_validations * 100.0) if self.total_validations > 0 else 0.0
            
            # Calculate STT requests per minute
            now = time.time()
            recent_requests = [t for t in self.stt_requests_per_minute if now - t < 60]
            stt_requests_per_min = len(recent_requests)
            
            return {
                'transcription_success_rate': transcription_success_rate,
                'avg_stt_latency_ms': avg_stt_latency,
                'avg_end_to_end_latency_ms': avg_e2e_latency,
                'retry_rate': retry_rate,
                'validation_failure_rate': validation_failure_rate,
                'stt_requests_per_minute': stt_requests_per_min,
                'total_utterances': self.total_utterances,
                'successful_transcriptions': self.successful_transcriptions,
                'failed_transcriptions': self.failed_transcriptions,
                'total_stt_attempts': self.total_stt_attempts,
                'stt_retries': self.stt_retries,
                'error_counts': dict(self.error_counts),
                'sample_size': len(self.stt_latencies)
            }
    
    def reset(self) -> None:
        """Reset all metrics (for testing)"""
        with self.lock:
            self.total_utterances = 0
            self.successful_transcriptions = 0
            self.failed_transcriptions = 0
            self.stt_latencies.clear()
            self.end_to_end_latencies.clear()
            self.total_stt_attempts = 0
            self.stt_retries = 0
            self.stt_requests_per_minute.clear()
            self.total_validations = 0
            self.validation_failures = 0
            self.error_counts.clear()


# Global metrics service instance
_metrics_service: Optional[MetricsService] = None

def get_metrics_service() -> MetricsService:
    """Get global metrics service instance"""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
