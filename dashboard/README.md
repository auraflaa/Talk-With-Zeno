# Performance Dashboard

A separate monitoring dashboard for Talk With Zeno that provides real-time insights into model and pipeline performance.

## Features

- **Real-time Metrics**: Live updates of service performance (STT, LLM, TTS, Pipeline)
- **Time Series Analysis**: Visual charts showing latency and call volume over time
- **Model Statistics**: Detailed breakdown of performance by model/provider
- **Error Tracking**: Monitor error rates and types across services
- **Historical Data**: View metrics for the last hour, 6 hours, 24 hours, or 7 days

## Usage

1. **Start the backend server** (if not already running):
   ```bash
   python backend/run.py
   ```

2. **Open the dashboard**:
   - Simply open `dashboard/index.html` in your web browser
   - Or serve it using a local web server:
     ```bash
     # Python 3
     cd dashboard
     python -m http.server 8080
     # Then open http://localhost:8080
     ```

3. **View metrics**:
   - The dashboard automatically refreshes every 10 seconds
   - Use the time range selector to view different periods
   - Click "Refresh" to manually update

## Metrics Collected

### Service Metrics
- **STT (Speech-to-Text)**: Call count, latency, success rate, model usage
- **LLM (Language Model)**: Call count, latency, success rate, model distribution
- **TTS (Text-to-Speech)**: Call count, latency, success rate, provider usage
- **Pipeline**: End-to-end latency, component breakdown, success rate

### Time Series Data
- Latency trends over time
- Call volume patterns
- Success rate trends
- Model usage distribution

### Error Statistics
- Total error count
- Errors by service (STT, LLM, TTS)
- Error types and frequencies

## API Endpoints

The dashboard uses the following backend API endpoints:

- `GET /api/metrics/summary?hours=24` - Get overall metrics summary
- `GET /api/metrics/timeseries?type=pipeline_calls&hours=24&group_by=minute` - Get time series data
- `GET /api/metrics/models?hours=24` - Get model-specific statistics

## Integration

Metrics are automatically collected when services are called through the main API. The metrics service stores data in `data/metrics.json` and maintains a rolling history (default: 7 days).

## Integration

Metrics are automatically collected when services are called through the main API. To fully enable metrics collection, add timing and recording calls around service invocations in `backend/app.py`:

```python
# Example: STT metrics
stt_start_time = time.time()
user_text = svcs['stt'].transcribe_audio(audio_data, language_code, audio_format)
stt_latency_ms = (time.time() - stt_start_time) * 1000

if svcs.get('metrics'):
    svcs['metrics'].record_metric('stt', stt_latency_ms, success=bool(user_text))
```

The metrics service stores data in `data/metrics.json` and maintains a rolling history (default: 7 days).

## Notes

- The dashboard is completely separate from the main UI
- No authentication required (for local development)
- Data is stored locally in `data/metrics.json`
- Metrics are collected automatically - no additional configuration needed
- See `backend/app.py` for examples of metrics integration

