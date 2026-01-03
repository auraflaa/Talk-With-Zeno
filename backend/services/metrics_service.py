"""
Metrics Collection Service
Collects and stores performance metrics for models and pipeline
Supports time series analysis and real-time monitoring
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
import threading


class MetricsService:
    """Service for collecting and storing performance metrics"""
    
    def __init__(self, metrics_file: str = "data/metrics.json", max_history_days: int = 7):
        """
        Initialize metrics service
        
        Args:
            metrics_file: Path to store metrics JSON file
            max_history_days: Maximum days of history to keep
        """
        self.metrics_file = metrics_file
        self.max_history_days = max_history_days
        self.lock = threading.Lock()
        
        # In-memory metrics storage
        self.metrics: Dict[str, List[Dict]] = {
            'stt_calls': [],
            'llm_calls': [],
            'tts_calls': [],
            'pipeline_calls': [],
            'errors': []
        }
        
        # Aggregated counters
        self.counters: Dict[str, int] = defaultdict(int)
        
        # Load existing metrics
        self._load_metrics()
        
        # Start background cleanup thread
        self._start_cleanup_thread()
    
    def _load_metrics(self):
        """Load metrics from file"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.metrics = data.get('metrics', self.metrics)
                    self.counters = data.get('counters', {})
                    print(f"Metrics: Loaded {len(self.metrics['pipeline_calls'])} pipeline calls from history")
        except Exception as e:
            print(f"Metrics: Error loading metrics: {e}")
            self.metrics = {
                'stt_calls': [],
                'llm_calls': [],
                'tts_calls': [],
                'pipeline_calls': [],
                'errors': []
            }
    
    def _save_metrics(self):
        """Save metrics to file"""
        try:
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'metrics': self.metrics,
                    'counters': dict(self.counters),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"Metrics: Error saving metrics: {e}")
    
    def _start_cleanup_thread(self):
        """Start background thread to clean old metrics"""
        def cleanup():
            while True:
                time.sleep(3600)  # Run every hour
                self._cleanup_old_metrics()
        
        thread = threading.Thread(target=cleanup, daemon=True)
        thread.start()
    
    def _cleanup_old_metrics(self):
        """Remove metrics older than max_history_days"""
        with self.lock:
            cutoff_time = time.time() - (self.max_history_days * 24 * 3600)
            
            for metric_type in self.metrics:
                self.metrics[metric_type] = [
                    m for m in self.metrics[metric_type]
                    if m.get('timestamp', 0) > cutoff_time
                ]
            
            self._save_metrics()
    
    def record_stt_call(self, model: str, latency_ms: float, success: bool, 
                       audio_size_bytes: int, text_length: int = 0):
        """Record STT service call"""
        with self.lock:
            metric = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'model': model,
                'latency_ms': latency_ms,
                'success': success,
                'audio_size_bytes': audio_size_bytes,
                'text_length': text_length
            }
            self.metrics['stt_calls'].append(metric)
            self.counters[f'stt_{model}_total'] += 1
            if success:
                self.counters[f'stt_{model}_success'] += 1
            else:
                self.counters[f'stt_{model}_errors'] += 1
                self.metrics['errors'].append({
                    'timestamp': time.time(),
                    'datetime': datetime.now().isoformat(),
                    'service': 'stt',
                    'model': model,
                    'error_type': 'transcription_failed'
                })
            
            # Save periodically (every 10 calls)
            if len(self.metrics['stt_calls']) % 10 == 0:
                self._save_metrics()
    
    def record_llm_call(self, model: str, latency_ms: float, success: bool,
                       prompt_length: int, response_length: int, tokens_used: int = 0):
        """Record LLM service call"""
        with self.lock:
            metric = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'model': model,
                'latency_ms': latency_ms,
                'success': success,
                'prompt_length': prompt_length,
                'response_length': response_length,
                'tokens_used': tokens_used
            }
            self.metrics['llm_calls'].append(metric)
            self.counters[f'llm_{model}_total'] += 1
            if success:
                self.counters[f'llm_{model}_success'] += 1
            else:
                self.counters[f'llm_{model}_errors'] += 1
                self.metrics['errors'].append({
                    'timestamp': time.time(),
                    'datetime': datetime.now().isoformat(),
                    'service': 'llm',
                    'model': model,
                    'error_type': 'generation_failed'
                })
            
            # Save periodically
            if len(self.metrics['llm_calls']) % 10 == 0:
                self._save_metrics()
    
    def record_tts_call(self, provider: str, model: str, latency_ms: float, success: bool,
                       text_length: int, audio_size_bytes: int = 0):
        """Record TTS service call"""
        with self.lock:
            metric = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'provider': provider,
                'model': model,
                'latency_ms': latency_ms,
                'success': success,
                'text_length': text_length,
                'audio_size_bytes': audio_size_bytes
            }
            self.metrics['tts_calls'].append(metric)
            self.counters[f'tts_{provider}_{model}_total'] += 1
            if success:
                self.counters[f'tts_{provider}_{model}_success'] += 1
            else:
                self.counters[f'tts_{provider}_{model}_errors'] += 1
                self.metrics['errors'].append({
                    'timestamp': time.time(),
                    'datetime': datetime.now().isoformat(),
                    'service': 'tts',
                    'provider': provider,
                    'model': model,
                    'error_type': 'synthesis_failed'
                })
            
            # Save periodically
            if len(self.metrics['tts_calls']) % 10 == 0:
                self._save_metrics()
    
    def record_pipeline_call(self, pipeline_type: str, total_latency_ms: float,
                            stt_latency_ms: float, llm_latency_ms: float, tts_latency_ms: float,
                            success: bool, user_id: str = None):
        """Record full pipeline call"""
        with self.lock:
            metric = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'pipeline_type': pipeline_type,  # 'voice' or 'text'
                'total_latency_ms': total_latency_ms,
                'stt_latency_ms': stt_latency_ms,
                'llm_latency_ms': llm_latency_ms,
                'tts_latency_ms': tts_latency_ms,
                'success': success,
                'user_id': user_id
            }
            self.metrics['pipeline_calls'].append(metric)
            self.counters[f'pipeline_{pipeline_type}_total'] += 1
            if success:
                self.counters[f'pipeline_{pipeline_type}_success'] += 1
            else:
                self.counters[f'pipeline_{pipeline_type}_errors'] += 1
            
            # Save periodically
            if len(self.metrics['pipeline_calls']) % 5 == 0:
                self._save_metrics()
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the last N hours"""
        cutoff_time = time.time() - (hours * 3600)
        
        with self.lock:
            # Filter recent metrics
            recent_stt = [m for m in self.metrics['stt_calls'] if m['timestamp'] > cutoff_time]
            recent_llm = [m for m in self.metrics['llm_calls'] if m['timestamp'] > cutoff_time]
            recent_tts = [m for m in self.metrics['tts_calls'] if m['timestamp'] > cutoff_time]
            recent_pipeline = [m for m in self.metrics['pipeline_calls'] if m['timestamp'] > cutoff_time]
            recent_errors = [m for m in self.metrics['errors'] if m['timestamp'] > cutoff_time]
            
            # Calculate statistics
            def calc_stats(metrics_list, latency_key='latency_ms'):
                if not metrics_list:
                    return {
                        'count': 0,
                        'avg_latency_ms': 0,
                        'min_latency_ms': 0,
                        'max_latency_ms': 0,
                        'success_rate': 0
                    }
                
                latencies = [m[latency_key] for m in metrics_list if latency_key in m]
                successes = [m for m in metrics_list if m.get('success', False)]
                
                return {
                    'count': len(metrics_list),
                    'avg_latency_ms': sum(latencies) / len(latencies) if latencies else 0,
                    'min_latency_ms': min(latencies) if latencies else 0,
                    'max_latency_ms': max(latencies) if latencies else 0,
                    'success_rate': len(successes) / len(metrics_list) if metrics_list else 0
                }
            
            # Group by model/provider
            stt_by_model = defaultdict(list)
            for m in recent_stt:
                stt_by_model[m['model']].append(m)
            
            llm_by_model = defaultdict(list)
            for m in recent_llm:
                llm_by_model[m['model']].append(m)
            
            tts_by_provider = defaultdict(list)
            for m in recent_tts:
                key = f"{m['provider']}_{m['model']}"
                tts_by_provider[key].append(m)
            
            return {
                'period_hours': hours,
                'timestamp': datetime.now().isoformat(),
                'stt': {
                    'overall': calc_stats(recent_stt),
                    'by_model': {model: calc_stats(metrics) for model, metrics in stt_by_model.items()}
                },
                'llm': {
                    'overall': calc_stats(recent_llm),
                    'by_model': {model: calc_stats(metrics) for model, metrics in llm_by_model.items()}
                },
                'tts': {
                    'overall': calc_stats(recent_tts),
                    'by_provider': {provider: calc_stats(metrics) for provider, metrics in tts_by_provider.items()}
                },
                'pipeline': {
                    'overall': calc_stats(recent_pipeline, 'total_latency_ms'),
                    'by_type': {
                        'voice': calc_stats([m for m in recent_pipeline if m['pipeline_type'] == 'voice'], 'total_latency_ms'),
                        'text': calc_stats([m for m in recent_pipeline if m['pipeline_type'] == 'text'], 'total_latency_ms')
                    },
                    'latency_breakdown': {
                        'avg_stt_ms': sum(m['stt_latency_ms'] for m in recent_pipeline) / len(recent_pipeline) if recent_pipeline else 0,
                        'avg_llm_ms': sum(m['llm_latency_ms'] for m in recent_pipeline) / len(recent_pipeline) if recent_pipeline else 0,
                        'avg_tts_ms': sum(m['tts_latency_ms'] for m in recent_pipeline) / len(recent_pipeline) if recent_pipeline else 0
                    }
                },
                'errors': {
                    'total': len(recent_errors),
                    'by_service': {
                        service: len([e for e in recent_errors if e.get('service') == service])
                        for service in ['stt', 'llm', 'tts']
                    }
                },
                'counters': dict(self.counters)
            }
    
    def get_time_series(self, metric_type: str, hours: int = 24, 
                       group_by: str = 'minute') -> List[Dict]:
        """
        Get time series data for a metric type
        
        Args:
            metric_type: 'stt_calls', 'llm_calls', 'tts_calls', 'pipeline_calls'
            hours: Number of hours of history
            group_by: 'minute', 'hour', or 'second'
            
        Returns:
            List of aggregated metrics by time period
        """
        if metric_type not in self.metrics:
            return []
        
        cutoff_time = time.time() - (hours * 3600)
        
        with self.lock:
            recent_metrics = [
                m for m in self.metrics[metric_type]
                if m['timestamp'] > cutoff_time
            ]
        
        # Group by time period
        grouped = defaultdict(lambda: {'count': 0, 'latencies': [], 'successes': 0})
        
        for metric in recent_metrics:
            ts = metric['timestamp']
            dt = datetime.fromtimestamp(ts)
            
            if group_by == 'minute':
                key = dt.strftime('%Y-%m-%d %H:%M')
            elif group_by == 'hour':
                key = dt.strftime('%Y-%m-%d %H:00')
            else:  # second
                key = dt.strftime('%Y-%m-%d %H:%M:%S')
            
            grouped[key]['count'] += 1
            if 'latency_ms' in metric:
                grouped[key]['latencies'].append(metric['latency_ms'])
            elif 'total_latency_ms' in metric:
                grouped[key]['latencies'].append(metric['total_latency_ms'])
            if metric.get('success', False):
                grouped[key]['successes'] += 1
        
        # Convert to list with calculated averages
        result = []
        for time_key in sorted(grouped.keys()):
            data = grouped[time_key]
            result.append({
                'time': time_key,
                'timestamp': time.mktime(datetime.strptime(time_key, 
                    '%Y-%m-%d %H:%M' if group_by == 'minute' else 
                    '%Y-%m-%d %H:00' if group_by == 'hour' else 
                    '%Y-%m-%d %H:%M:%S').timetuple()),
                'count': data['count'],
                'avg_latency_ms': sum(data['latencies']) / len(data['latencies']) if data['latencies'] else 0,
                'success_rate': data['successes'] / data['count'] if data['count'] > 0 else 0
            })
        
        return result


# Singleton instance
_metrics_service: Optional[MetricsService] = None


def get_metrics_service() -> MetricsService:
    """Get metrics service instance (singleton)"""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service

