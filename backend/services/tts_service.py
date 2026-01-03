"""
Text-to-Speech Service
Supports Groq and Gemini TTS models with fallback
"""

import os
import requests
import google.generativeai as genai
from typing import Optional, List
from pathlib import Path

# Try to import Groq SDK
try:
    from groq import Groq
    GROQ_SDK_AVAILABLE = True
except ImportError:
    GROQ_SDK_AVAILABLE = False
    Groq = None


class TTSService:
    """TTS service with multiple providers and fallback"""
    
    def __init__(self):
        self.groq_api_key = os.getenv('GROQ_API_KEY') or os.getenv('VITE_GROQ_API_KEY')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.providers = []
        
        # Check if keys are placeholders
        groq_key_valid = bool(self.groq_api_key) and not self.groq_api_key.startswith('your_') and len(self.groq_api_key) > 20
        gemini_key_valid = bool(self.gemini_api_key) and not self.gemini_api_key.startswith('your_') and len(self.gemini_api_key) > 20
        
        print(f"TTS: Groq API key present: {bool(self.groq_api_key)} (valid: {groq_key_valid})")
        print(f"TTS: Gemini API key present: {bool(self.gemini_api_key)} (valid: {gemini_key_valid})")
        
        if not groq_key_valid:
            print("TTS: WARNING - GROQ_API_KEY not set or invalid. TTS will not work!")
            print("TTS: Set GROQ_API_KEY in .env.local to enable TTS")
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize available TTS providers"""
        # Try Groq first
        if self.groq_api_key:
            self.providers.append('groq')
            print("TTS: Groq provider available")
        
        # Try Gemini TTS
        if self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
                self.providers.append('gemini')
                print("TTS: Gemini provider available")
            except:
                pass
        
        if not self.providers:
            print("Warning: No TTS providers available")
    
    def synthesize_speech_groq(self, text: str, model: str = None, voice: str = None) -> Optional[bytes]:
        """
        Synthesize speech using Groq Orpheus TTS API
        
        Args:
            text: Text to convert to speech (max 200 characters)
            model: Groq TTS model name (default: canopylabs/orpheus-v1-english)
            voice: Voice persona ID (default: autumn)
                Available voices: autumn, diana, hannah, austin, daniel, troy
            
        Returns:
            Audio bytes (WAV format) or None if failed
        """
        if not self.groq_api_key:
            return None
        
        # Use Groq SDK if available, otherwise fall back to requests
        if GROQ_SDK_AVAILABLE:
            try:
                client = Groq(api_key=self.groq_api_key)
                
                # Use Orpheus model
                tts_model = model or "canopylabs/orpheus-v1-english"
                
                # Available voices: autumn, diana, hannah, austin, daniel, troy
                # Default to troy as requested
                voice_id = voice or "troy"
                
                # Truncate text to 200 characters (Groq limit)
                if len(text) > 200:
                    print(f"Groq TTS: Text truncated from {len(text)} to 200 characters")
                    text = text[:197] + "..."
                
                print(f"Groq TTS: Using SDK - model: {tts_model}, voice: {voice_id}")
                print(f"Groq TTS: Text length: {len(text)} characters")
                
                # Use Groq SDK
                response = client.audio.speech.create(
                    model=tts_model,
                    voice=voice_id,
                    response_format="wav",
                    input=text
                )
                
                # Get audio content as bytes
                audio_content = response.content if hasattr(response, 'content') else b''.join(response.iter_bytes())
                
                print(f"Groq TTS: Success! Generated audio: {len(audio_content)} bytes (WAV format)")
                return audio_content
                
            except Exception as e:
                print(f"Groq TTS: SDK error: {e}")
                import traceback
                traceback.print_exc()
                # Fall through to requests fallback
                pass
        
        # Fallback to requests if SDK not available or failed
        try:
            url = "https://api.groq.com/openai/v1/audio/speech"
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            
            # Use Orpheus model
            tts_model = model or "canopylabs/orpheus-v1-english"
            
            # Available voices: autumn, diana, hannah, austin, daniel, troy
            # Default to troy as requested
            voice_id = voice or "troy"
            
            # Truncate text to 200 characters (Groq limit)
            if len(text) > 200:
                print(f"Groq TTS: Text truncated from {len(text)} to 200 characters")
                text = text[:197] + "..."
            
            data = {
                "model": tts_model,
                "input": text,
                "voice": voice_id,
                "response_format": "wav"  # Only supported format for Orpheus
            }
            
            print(f"Groq TTS: Using requests - model: {tts_model}, voice: {voice_id}")
            print(f"Groq TTS: Text length: {len(text)} characters")
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            print(f"Groq TTS: Response status: {response.status_code}")
            
            if response.status_code == 200:
                audio_content = response.content
                print(f"Groq TTS: Success! Received audio: {len(audio_content)} bytes (WAV format)")
                return audio_content
            elif response.status_code == 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('error', {}).get('message', '') if error_data else response.text[:200]
                print(f"Groq TTS: Error: {error_msg}")
                if 'terms acceptance' in error_msg.lower():
                    print(f"Groq TTS: Model requires terms acceptance at https://console.groq.com/playground")
                return None
            else:
                print(f"Groq TTS: Error response: {response.text[:200]}")
                response.raise_for_status()
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Groq TTS: Request error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Groq TTS: Response text: {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"Groq TTS: Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def synthesize_speech_gemini(self, text: str) -> Optional[bytes]:
        """
        Synthesize speech using Gemini TTS
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Audio bytes or None if failed
        """
        if not self.gemini_api_key:
            return None
        
        print("Gemini TTS: Note - Gemini TTS models are not available via the standard Generative AI API")
        print("Gemini TTS: Consider using Google Cloud Text-to-Speech API instead")
        print("Gemini TTS: For now, returning None - use Groq TTS as primary provider")
        
        # Gemini TTS models don't work via the standard API
        # Would need to use Google Cloud Text-to-Speech API
        return None
    
    def synthesize_speech(self, text: str, preferred_provider: Optional[str] = None) -> Optional[bytes]:
        """
        Synthesize speech with fallback between providers
        
        Args:
            text: Text to convert to speech
            preferred_provider: Preferred provider ('groq' or 'gemini')
            
        Returns:
            Audio bytes or None if all providers fail
        """
        if not text or not text.strip():
            print("TTS: Empty text provided")
            return None
        
        print(f"TTS: Attempting to synthesize speech (text length: {len(text)})")
        print(f"TTS: Available providers: {self.providers}")
        
        # Determine provider order
        providers_to_try = []
        if preferred_provider and preferred_provider in self.providers:
            providers_to_try.append(preferred_provider)
        
        # Add other available providers
        for provider in self.providers:
            if provider != preferred_provider:
                providers_to_try.append(provider)
        
        if not providers_to_try:
            print("TTS: No providers available")
            return None
        
        # Try each provider
        for provider in providers_to_try:
            print(f"TTS: Trying provider: {provider}")
            if provider == 'groq':
                audio = self.synthesize_speech_groq(text)
                if audio:
                    print(f"TTS: Success with Groq (audio size: {len(audio)} bytes)")
                    return audio
                else:
                    print("TTS: Groq failed, trying next provider")
            elif provider == 'gemini':
                audio = self.synthesize_speech_gemini(text)
                if audio:
                    print(f"TTS: Success with Gemini (audio size: {len(audio)} bytes)")
                    return audio
                else:
                    print("TTS: Gemini failed, trying next provider")
        
        print("TTS: All providers failed")
        return None


# Singleton instance
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get TTS service instance (singleton)"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service

