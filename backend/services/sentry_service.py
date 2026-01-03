"""
Sentry Error Monitoring Service
Initializes and configures Sentry for error tracking
"""

import os
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


def init_sentry():
    """Initialize Sentry error monitoring"""
    sentry_dsn = os.getenv('SENTRY_DSN')
    
    if not sentry_dsn:
        # Sentry is optional - don't fail if DSN is not set
        return False
    
    try:
        # Get environment
        environment = os.getenv('FLASK_ENV', 'development')
        
        # Configure Sentry
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            integrations=[
                FlaskIntegration(
                    transaction_style='url',  # Track transactions by URL
                ),
                LoggingIntegration(
                    level=None,  # Capture all logs
                    event_level=None,  # Send all log events
                ),
            ],
            # Performance monitoring
            traces_sample_rate=1.0 if environment == 'development' else 0.1,
            # Session replay (optional, for debugging)
            replays_session_sample_rate=0.1 if environment == 'development' else 0.0,
            replays_on_error_sample_rate=1.0,
            # Release tracking
            release=os.getenv('APP_VERSION', 'unknown'),
            # Additional context
            before_send=lambda event, hint: event,  # Can filter events here
        )
        
        return True
    except Exception as e:
        # Don't fail if Sentry initialization fails
        print(f"Warning: Failed to initialize Sentry: {e}")
        return False

