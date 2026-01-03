# Performance Results

This folder contains all performance analysis results and test data.

## Contents

- **`DEEP_ANALYSIS.md`** - Latest comprehensive production-grade analysis (includes STT, LLM, TTS, chunk size analysis)
- **`deep_analysis.json`** - Latest analysis data (JSON)

## Running Analysis

```bash
# Deep production-grade analysis (recommended)
python backend/tests/deep_analysis.py

# Service tests
python backend/tests/test_services.py

# Pipeline tests
python backend/tests/test_pipeline.py
```

Results are automatically saved to this folder. Old timestamped files are cleaned up automatically.
