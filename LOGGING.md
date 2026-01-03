# Logging and Error Monitoring Guide

This document explains how to use the production logging and error monitoring systems.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r backend/requirements.txt
   npm install
   ```

2. **Configure environment variables** (add to `.env.local`):
   ```bash
   LOG_LEVEL=INFO  # DEBUG, INFO, WARN, ERROR
   VITE_LOG_LEVEL=INFO  # For frontend
   SENTRY_DSN=https://your-dsn@sentry.io/project-id  # Optional
   VITE_SENTRY_DSN=https://your-dsn@sentry.io/project-id  # Optional
   ```

3. **Usage:**
   ```python
   # Backend
   from backend.services.logger_service import get_logger
   logger = get_logger()
   logger.info("Message")
   ```
   ```typescript
   // Frontend
   import { logger } from './services/logger'
   logger.info("Message")
   ```

---

## Backend Logging

### Configuration

The backend uses Python's `logging` module with a custom `LoggerService` that provides structured logging.

**Environment Variables:**
- `LOG_LEVEL`: Set the minimum log level (DEBUG, INFO, WARN, ERROR). Default: INFO
- `FLASK_ENV`: Set to `production` for production logging (file rotation enabled)

**Example in `.env.local`:**
```bash
LOG_LEVEL=DEBUG
FLASK_ENV=development
```

### Usage

```python
from backend.services.logger_service import get_logger

logger = get_logger()

# Log messages at different levels
logger.debug("Detailed debugging information")
logger.info("General informational message")
logger.warning("Warning message - something unexpected but not critical")
logger.error("Error message - something failed", exc_info=True)  # Include exception traceback
logger.critical("Critical error - system may be unstable")
```

### Log Levels

- **DEBUG**: Detailed information for diagnosing problems
- **INFO**: General informational messages about application flow
- **WARN**: Warning messages for unexpected but non-critical situations
- **ERROR**: Error messages for failures that don't stop the application
- **CRITICAL**: Critical errors that may cause the application to fail

### Log Files (Production)

In production mode (`FLASK_ENV=production`), logs are written to:
- `logs/zeno_backend.log`: All logs (rotates at 10MB, keeps 5 backups)
- `logs/zeno_backend_errors.log`: Only errors (rotates at 5MB, keeps 3 backups)

## Frontend Logging

### Configuration

The frontend uses a custom `Logger` class that respects log levels.

**Environment Variables:**
- `VITE_LOG_LEVEL`: Set the minimum log level (DEBUG, INFO, WARN, ERROR, NONE). Default: INFO in production, DEBUG in development

**Example in `.env.local`:**
```bash
VITE_LOG_LEVEL=INFO
```

### Usage

```typescript
import { logger } from './services/logger'

// Log messages at different levels
logger.debug("Detailed debugging information")
logger.info("General informational message")
logger.warn("Warning message")
logger.error("Error message", error)  // Pass Error object for stack trace
```

### Log Levels

- **DEBUG**: Detailed debugging information (only in development)
- **INFO**: General informational messages
- **WARN**: Warning messages
- **ERROR**: Error messages
- **NONE**: Disable all logging

## Sentry Error Monitoring

### Setup

1. **Create a Sentry account** at https://sentry.io
2. **Create a new project** (choose Flask for backend, React for frontend)
3. **Get your DSN** from the project settings
4. **Add DSN to environment variables**

### Backend Configuration

**Environment Variable:**
```bash
SENTRY_DSN=https://your-dsn@sentry.io/project-id
```

Sentry is automatically initialized in `backend/run.py`. If `SENTRY_DSN` is not set, Sentry is disabled (no errors).

### Frontend Configuration

**Environment Variable:**
```bash
VITE_SENTRY_DSN=https://your-dsn@sentry.io/project-id
```

Sentry is automatically initialized in `index.tsx`. If `VITE_SENTRY_DSN` is not set, Sentry is disabled.

### Manual Error Reporting

**Backend:**
```python
import sentry_sdk

# Capture exception
try:
    # Your code
    pass
except Exception as e:
    sentry_sdk.capture_exception(e)
    raise

# Capture message
sentry_sdk.capture_message("Something went wrong", level="error")
```

**Frontend:**
```typescript
import { captureError, captureMessage } from './services/sentry'

// Capture exception
try {
    // Your code
} catch (error) {
    captureError(error as Error, { context: 'additional info' })
}

// Capture message
captureMessage("Something went wrong", "error")
```

### What Sentry Captures

- **Exceptions**: All unhandled exceptions
- **Logs**: Error-level logs (configurable)
- **Performance**: Request traces (10% sample rate in production)
- **Session Replay**: User sessions when errors occur (for debugging)
- **Context**: User ID, request details, environment info

### Privacy

- Session replay masks all text and blocks media by default
- Sensitive data should not be logged (use environment variables for secrets)
- Review Sentry's privacy settings in your project

## Migration Guide

### Replacing `print()` Statements

**Before:**
```python
print("Processing audio...")
print(f"Error: {error}")
```

**After:**
```python
from backend.services.logger_service import get_logger
logger = get_logger()

logger.info("Processing audio...")
logger.error(f"Error: {error}", exc_info=True)
```

### Replacing `console.log()` Statements

**Before:**
```typescript
console.log("Processing audio...")
console.error("Error:", error)
```

**After:**
```typescript
import { logger } from './services/logger'

logger.info("Processing audio...")
logger.error("Error", error)
```

## Best Practices

1. **Use appropriate log levels**: Don't log everything as ERROR
2. **Include context**: Add relevant information to log messages
3. **Don't log sensitive data**: Never log passwords, API keys, or personal information
4. **Use structured logging**: Include relevant context in log messages
5. **Monitor production logs**: Set up alerts for ERROR and CRITICAL levels
6. **Review Sentry regularly**: Check for patterns in errors

## Troubleshooting

### Logs not appearing
- Check `LOG_LEVEL` environment variable
- Verify logger is initialized before use
- Check file permissions for log directory (production)

### Sentry not capturing errors
- Verify `SENTRY_DSN` is set correctly
- Check Sentry dashboard for project status
- Review browser console for Sentry initialization errors

### Too many logs
- Increase `LOG_LEVEL` to WARN or ERROR in production
- Review and remove unnecessary debug logs
- Use log filtering in Sentry

