# Performance Results

This folder contains all performance analysis results and test data.

## Contents

- **`DEEP_ANALYSIS.md`** - Latest comprehensive production-grade analysis (includes STT, LLM, TTS, chunk size analysis)
- **`deep_analysis.json`** - Latest analysis data (JSON)
- **`test_results.json`** - Streaming pipeline test results

## Running Analysis

```bash
# Deep production-grade analysis (recommended)
python backend/tests/deep_analysis.py

# Streaming pipeline test
python backend/tests/test_streaming_pipeline.py

# Pipeline integration test
python backend/tests/test_pipeline_integration.py
```

Results are automatically saved to this folder. Old timestamped files are cleaned up automatically.
