"""
Run script for Talk With Zeno backend
"""

import os
import sys
import threading
import time
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path so we can import backend modules
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Load environment variables
env_path = parent_dir / '.env.local'
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try current directory
    load_dotenv('.env.local')

# Initialize Sentry before importing app
from backend.services.sentry_service import init_sentry
sentry_initialized = init_sentry()

# Initialize logger
from backend.services.logger_service import get_logger
logger = get_logger()

# Import app after environment is loaded
from backend.app import app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    logger.info(f"Starting Talk With Zeno backend on {host}:{port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Log level: {os.getenv('LOG_LEVEL', 'INFO')}")
    if sentry_initialized:
        logger.info("Sentry error monitoring: Enabled")
    else:
        logger.info("Sentry error monitoring: Disabled (SENTRY_DSN not set)")
    
    # Start background thread for periodic cleanup of stale streaming sessions
    def cleanup_sessions():
        """Periodically clean up stale streaming sessions"""
        from backend.services.streaming_service import get_streaming_service
        while True:
            try:
                time.sleep(300)  # Run every 5 minutes
                streaming_service = get_streaming_service()
                streaming_service.cleanup_stale_sessions(timeout_seconds=300)
                logger.debug(f"Session cleanup: {streaming_service.get_session_count()} active sessions")
            except Exception as e:
                logger.error(f"Error in session cleanup thread: {e}")
    
    cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
    cleanup_thread.start()
    logger.info("Background session cleanup thread started")
    
    # Run Flask in threaded mode to handle concurrent requests
    # This allows STT processing and response handling to happen in parallel
    app.run(debug=debug, host=host, port=port, threaded=True)

