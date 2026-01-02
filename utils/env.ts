/**
 * Environment Variables Utility
 * 
 * This file provides type-safe access to environment variables.
 * Update this file as you add new environment variables.
 */

// Access environment variables in Vite
// Note: For client-side access, variables must be prefixed with VITE_
// For sensitive keys, use backend proxy instead

export const env = {
  // Gemini API Key (already configured in vite.config.ts)
  get geminiApiKey(): string {
    return import.meta.env.GEMINI_API_KEY || '';
  },

  // Google Speech-to-Text API Key
  get googleSttApiKey(): string {
    return import.meta.env.VITE_GOOGLE_STT_API_KEY || '';
  },

  // Google Text-to-Speech API Key
  get googleTtsApiKey(): string {
    return import.meta.env.VITE_GOOGLE_TTS_API_KEY || '';
  },

  // Google Cloud Project ID
  get googleCloudProjectId(): string {
    return import.meta.env.VITE_GOOGLE_CLOUD_PROJECT_ID || '';
  },

  // Firestore Project ID
  get firestoreProjectId(): string {
    return import.meta.env.VITE_GOOGLE_FIRESTORE_PROJECT_ID || '';
  },

  // API Base URL
  get apiBaseUrl(): string {
    return import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
  },
};

/**
 * Validate that required environment variables are set
 * Call this during app initialization
 */
export function validateEnv(): { valid: boolean; missing: string[] } {
  const missing: string[] = [];

  // Check required variables
  if (!env.geminiApiKey) {
    missing.push('GEMINI_API_KEY');
  }

  // Add other required checks as needed
  // Note: Some may be optional or only needed for specific features

  return {
    valid: missing.length === 0,
    missing,
  };
}

/**
 * Example usage in a service file:
 * 
 * import { env } from '@/utils/env';
 * 
 * const response = await fetch('https://api.example.com', {
 *   headers: {
 *     'Authorization': `Bearer ${env.geminiApiKey}`
 *   }
 * });
 */

