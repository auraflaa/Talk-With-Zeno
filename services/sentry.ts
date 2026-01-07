/**
 * Sentry Error Monitoring Service
 * Initializes and configures Sentry for frontend error tracking
 */

// Import Sentry - it's now installed, but we'll handle errors gracefully
import * as Sentry from '@sentry/react';

export function initSentry(): boolean {
  
  const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string;
  
  if (!sentryDsn) {
    // Sentry is optional - don't fail if DSN is not set
    return false;
  }

  try {
    const environment = (import.meta.env.MODE || 'development') as string;
    
    Sentry.init({
      dsn: sentryDsn,
      environment,
      
      // Performance monitoring
      tracesSampleRate: environment === 'development' ? 1.0 : 0.1,
      
      // Session replay (for debugging)
      replaysSessionSampleRate: environment === 'development' ? 0.1 : 0.0,
      replaysOnErrorSampleRate: 1.0,
      
      // Release tracking
      release: (import.meta.env.VITE_APP_VERSION as string) || 'unknown',
      
      // Integrations
      integrations: [
        Sentry.replayIntegration({
          maskAllText: true,  // Privacy: mask all text
          blockAllMedia: true,  // Privacy: block all media
        }),
        Sentry.browserTracingIntegration(),
      ],
      
      // Error filtering
      beforeSend(event, hint) {
        // Filter out known non-critical errors
        if (event.exception) {
          const error = hint.originalException;
          if (error instanceof Error) {
            // Don't report network errors (user's connection issue)
            if (error.message.includes('Failed to fetch') || 
                error.message.includes('NetworkError') ||
                error.message.includes('Network request failed')) {
              return null;
            }
          }
        }
        return event;
      },
    });

    return true;
  } catch (error) {
    console.warn('Failed to initialize Sentry:', error);
    return false;
  }
}

// Helper function to manually capture errors
export function captureError(error: Error, context?: Record<string, any>): void {
  try {
    if (context) {
      Sentry.setContext('additional', context);
    }
    Sentry.captureException(error);
  } catch (e) {
    // Silently fail if Sentry is not properly initialized
    console.warn('Sentry error capture failed:', e);
  }
}

// Helper function to capture messages
export function captureMessage(message: string, level: Sentry.SeverityLevel = 'info'): void {
  try {
    Sentry.captureMessage(message, level);
  } catch (e) {
    // Silently fail if Sentry is not properly initialized
    console.warn('Sentry message capture failed:', e);
  }
}

