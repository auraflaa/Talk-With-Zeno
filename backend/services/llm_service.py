"""
Gemini LLM Service
Handles conversation with LLM, personalization context, and CRUD operations
"""

import os
import json
import google.generativeai as genai
from typing import Optional, Dict, Any, List
from datetime import datetime
from backend.services.storage_service import get_storage_service


class LLMService:
    """Gemini LLM service with personalization support"""
    
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        self.model = None
        self.current_model_name = None
        self.storage = get_storage_service()
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize Gemini model with fallback options"""
        if not self.api_key:
            print("Warning: GEMINI_API_KEY not set. LLM will not be available.")
            print("  Set GEMINI_API_KEY in .env.local file")
            return
        
        # Check if API key looks valid (not placeholder)
        if self.api_key.startswith('your_') or 'here' in self.api_key.lower() or len(self.api_key) < 20:
            print(f"Warning: GEMINI_API_KEY appears to be a placeholder: {self.api_key[:10]}...")
            print("  Please set a valid GEMINI_API_KEY in .env.local file")
            return
        
        try:
            genai.configure(api_key=self.api_key)
            print(f"LLM: Configured with API key (length: {len(self.api_key)})")
            
            # Prioritize flash models for better performance (2.4x faster)
            # Flash models are optimized for speed while maintaining good quality
            model_names = [
                'gemini-2.5-flash',     # Primary: Fastest and most capable flash model
                'gemini-2.0-flash',     # Fallback: Alternative flash model
                'gemini-2.0-flash-lite', # Fallback: Lightweight flash model
                'gemini-1.5-flash',     # Fallback: Legacy flash model
                'gemini-2.5-pro',       # Fallback: Pro model if flash unavailable
                'gemini-1.5-pro',       # Fallback: Alternative pro model
                'gemini-pro'            # Fallback: Legacy pro model
            ]
            
            for model_name in model_names:
                try:
                    # Just create the model object - don't test it yet
                    self.model = genai.GenerativeModel(model_name)
                    print(f"LLM: Initialized model: {model_name}")
                    self.current_model_name = model_name
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    if 'api key' in error_str or 'authentication' in error_str or '401' in error_str or '403' in error_str:
                        print(f"LLM: Authentication error with {model_name}: {e}")
                        print("  Check GEMINI_API_KEY in .env.local - it may be invalid")
                        break  # Don't try other models if auth fails
                    print(f"LLM: Could not initialize {model_name}: {e}")
                    continue
            
            if not self.model:
                print("LLM: ERROR - Could not initialize any Gemini model")
                print("  Check GEMINI_API_KEY in .env.local and restart backend")
        except Exception as e:
            print(f"Error initializing Gemini model: {e}")
            import traceback
            traceback.print_exc()
    
    def _try_models_with_fallback(self, prompt: str) -> Optional[str]:
        """
        Try generating response with multiple models, fallback on rate limit
        
        Args:
            prompt: Input prompt
            
        Returns:
            Response text or None if all models fail
        """
        if not self.api_key:
            print("LLM: ERROR - No API key set")
            return None
        
        # Use the already initialized model first (faster)
        if self.model and self.current_model_name:
            try:
                import time
                start_time = time.time()
                print(f"LLM: Using initialized model: {self.current_model_name}")
                
                generation_config = {
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                elapsed = time.time() - start_time
                if response and response.text:
                    print(f"LLM: Success with {self.current_model_name} in {elapsed:.2f}s")
                    return response.text
                else:
                    print(f"LLM: {self.current_model_name} returned empty response")
            except Exception as e:
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                error_str = str(e).lower()
                print(f"LLM: Error with initialized model {self.current_model_name} (after {elapsed:.2f}s): {e}")
                # Continue to fallback models
        
        # Models to try in order - prioritize flash models for speed
        model_names = [
            'gemini-2.5-flash',      # Primary: Fastest and most capable flash model
            'gemini-2.0-flash',      # Fallback: Alternative flash model
            'gemini-2.0-flash-lite', # Fallback: Lightweight flash model
            'gemini-1.5-flash',      # Fallback: Legacy flash model
            'gemini-2.5-pro',       # Fallback: Pro model if flash unavailable
            'gemini-1.5-pro',       # Fallback: Alternative pro model
            'gemini-pro'            # Fallback: Legacy pro model
        ]
        
        import time
        for model_name in model_names:
            # Skip if we already tried this model
            if self.current_model_name == model_name:
                continue
                
            try:
                start_time = time.time()
                print(f"LLM: Trying {model_name}...")
                model = genai.GenerativeModel(model_name)
                
                # Add generation config for faster responses
                generation_config = {
                    "temperature": 0.7,
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
                
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                elapsed = time.time() - start_time
                if response and response.text:
                    print(f"LLM: Success with {model_name} in {elapsed:.2f}s")
                    # Update current model
                    self.model = model
                    self.current_model_name = model_name
                    return response.text
                else:
                    print(f"LLM: {model_name} returned empty response")
            except Exception as e:
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                error_str = str(e).lower()
                # Check if it's a rate limit error
                if 'rate limit' in error_str or 'quota' in error_str or '429' in error_str:
                    print(f"LLM: Rate limited on {model_name} (after {elapsed:.2f}s), trying next model...")
                    continue
                elif 'timeout' in error_str or 'timed out' in error_str:
                    print(f"LLM: Timeout on {model_name} (after {elapsed:.2f}s), trying next model...")
                    continue
                elif 'api key' in error_str or 'authentication' in error_str or '401' in error_str or '403' in error_str:
                    print(f"LLM: Authentication error with {model_name}: {e}")
                    print("LLM: Check GEMINI_API_KEY in .env.local")
                    # Don't continue if it's an auth error - all models will fail
                    break
                else:
                    print(f"LLM: Error with {model_name} (after {elapsed:.2f}s): {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        print("LLM: All models failed - check backend logs for details")
        return None
    
    def _build_system_prompt(self, user_id: str) -> str:
        """
        Build system prompt with personalization context
        
        Args:
            user_id: User identifier
            
        Returns:
            System prompt string
        """
        personalization = self.storage.load_personalization(user_id)
        
        prompt = """You are Zeno, a friendly and caring AI companion. Think of yourself as a close friend who's always there to listen and chat.

Your personality:
- Be warm, friendly, and conversational - like talking to a good friend
- Use natural, casual language - avoid being too formal or clinical
- Show genuine interest and curiosity about what the user shares
- Be empathetic but not overly therapeutic - keep it real and relatable
- Use humor when appropriate, but be sensitive to serious topics
- Ask follow-up questions like a friend would
- Share your own thoughts and perspectives naturally
- Be supportive without being preachy or giving unsolicited advice
- NEVER provide medical diagnoses or replace professional help
- Learn about the user over time and remember what they tell you

Conversation style:
- Talk like you're texting a friend - be natural and authentic
- Use contractions (I'm, you're, that's) to sound more casual
- Don't be afraid to be a bit playful or lighthearted when appropriate
- Match the user's energy - if they're serious, be serious; if they're casual, be casual
- Avoid phrases like "I want you to know" or "Please know that" - just be direct and friendly
- Instead of "I'm here for you," just be present in the conversation naturally

Personalization Context (Use this to tailor your responses):
"""
        
        # Add personalization data with timestamps
        if personalization.get("preferences"):
            prompt += f"\nUser Preferences:\n{json.dumps(personalization['preferences'], indent=2)}\n"
        
        if personalization.get("topics_of_interest"):
            prompt += f"\nTopics of Interest: {', '.join(personalization['topics_of_interest'])}\n"
        
        if personalization.get("goals"):
            prompt += f"\nUser Goals: {', '.join(personalization['goals'])}\n"
        
        if personalization.get("emotional_patterns"):
            recent_patterns = personalization['emotional_patterns'][-5:]
            if recent_patterns:
                prompt += f"\nRecent Emotional Patterns:\n{json.dumps(recent_patterns, indent=2)}\n"
        
        if personalization.get("notes"):
            recent_notes = personalization['notes'][-3:]
            if recent_notes:
                prompt += f"\nRecent Notes:\n{json.dumps(recent_notes, indent=2)}\n"
        
        current_time = datetime.now().isoformat()
        prompt += f"""
IMPORTANT - Personalization Update Format:
When you learn something new about the user or want to update their personalization data, you MUST use these exact command formats at the END of your response (after your natural conversation):

1. Update Preferences:
   [UPDATE_PERSONALIZATION:{{"preferences": {{"tone": "supportive", "depth": "moderate"}}}}]

2. Add Topic of Interest:
   [ADD_TOPIC:"anxiety management"]

3. Add User Goal:
   [ADD_GOAL:"practice mindfulness daily"]

4. Add Note (for your memory):
   [ADD_NOTE:"User mentioned feeling stressed about work deadlines"]

5. Record Emotional Pattern:
   [ADD_EMOTIONAL_PATTERN:{{"emotion": "anxiety", "intensity": 0.7, "timestamp": "{current_time}"}}]

Rules:
- ALWAYS respond naturally first, then add update commands at the end if needed
- Use update commands when you learn new information about preferences, goals, or emotional states
- Be proactive in detecting patterns (e.g., if user mentions stress multiple times, add it as a topic)
- Update preferences if user indicates they want a different communication style
- Current timestamp: {current_time}

Example Response Format:
"Ugh, that sounds really tough. I get why you'd feel that way. Want to talk more about it? [ADD_TOPIC:"work stress"] [ADD_EMOTIONAL_PATTERN:{{"emotion": "anxiety", "intensity": 0.6, "timestamp": "{current_time}"}}]"

More Examples:
- User mentions a goal: "Oh nice! That's a solid goal. I'm rooting for you! [ADD_GOAL:"exercise 3 times per week"]"
- User expresses emotion: "Yeah, I can see why that would make you feel that way. What's going on? [ADD_EMOTIONAL_PATTERN:{{"emotion": "sadness", "intensity": 0.5, "timestamp": "{current_time}"}}]"
- User mentions preference: "Got it! I'll keep that in mind. [UPDATE_PERSONALIZATION:{{"preferences": {{"tone": "gentle", "depth": "deep"}}}}]"
- User asks a question: "Hmm, that's a big question. What made you think about that? [ADD_TOPIC:"philosophy"]"
- User shares something important: "Thank you for sharing that with me. [ADD_NOTE:"User mentioned struggling with sleep schedule"]"

Remember: Always place update commands at the END of your response, after your natural conversation.
"""
        
        return prompt
    
    def _extract_updates(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Extract personalization update commands from LLM response
        
        Args:
            response_text: LLM response text
            
        Returns:
            List of update commands
        """
        updates = []
        import re
        
        # Look for UPDATE_PERSONALIZATION commands (supports nested JSON)
        # Use a more robust pattern that handles nested braces
        update_pattern = r'\[UPDATE_PERSONALIZATION:(\{.*?\})\]'
        for match in re.finditer(update_pattern, response_text, re.DOTALL):
            try:
                json_str = match.group(1)
                update_data = json.loads(json_str)
                updates.append({"type": "update", "data": update_data})
                print(f"LLM: Extracted UPDATE_PERSONALIZATION: {update_data}")
            except Exception as e:
                print(f"LLM: Failed to parse UPDATE_PERSONALIZATION: {e}, JSON: {match.group(1)[:100]}")
        
        # Look for ADD_TOPIC commands
        topic_pattern = r'\[ADD_TOPIC:"([^"]+)"\]'
        for match in re.finditer(topic_pattern, response_text):
            topic = match.group(1)
            updates.append({"type": "add_topic", "value": topic})
            print(f"LLM: Extracted ADD_TOPIC: {topic}")
        
        # Look for ADD_GOAL commands
        goal_pattern = r'\[ADD_GOAL:"([^"]+)"\]'
        for match in re.finditer(goal_pattern, response_text):
            goal = match.group(1)
            updates.append({"type": "add_goal", "value": goal})
            print(f"LLM: Extracted ADD_GOAL: {goal}")
        
        # Look for ADD_NOTE commands
        note_pattern = r'\[ADD_NOTE:"([^"]+)"\]'
        for match in re.finditer(note_pattern, response_text):
            note = match.group(1)
            updates.append({"type": "add_note", "value": note})
            print(f"LLM: Extracted ADD_NOTE: {note}")
        
        # Look for ADD_EMOTIONAL_PATTERN commands (supports nested JSON)
        pattern_pattern = r'\[ADD_EMOTIONAL_PATTERN:(\{.*?\})\]'
        for match in re.finditer(pattern_pattern, response_text, re.DOTALL):
            try:
                json_str = match.group(1)
                pattern_data = json.loads(json_str)
                # Ensure timestamp is set
                if "timestamp" not in pattern_data:
                    pattern_data["timestamp"] = datetime.now().isoformat()
                updates.append({"type": "add_emotional_pattern", "data": pattern_data})
                print(f"LLM: Extracted ADD_EMOTIONAL_PATTERN: {pattern_data}")
            except Exception as e:
                print(f"LLM: Failed to parse ADD_EMOTIONAL_PATTERN: {e}, JSON: {match.group(1)[:100]}")
        
        if updates:
            print(f"LLM: Total updates extracted: {len(updates)}")
        
        return updates
    
    def _clean_response(self, response_text: str) -> str:
        """
        Remove update commands from response text
        
        Args:
            response_text: Raw response text
            
        Returns:
            Cleaned response text
        """
        import re
        # Remove all command patterns
        response_text = re.sub(r'\[UPDATE_PERSONALIZATION:[^\]]+\]', '', response_text)
        response_text = re.sub(r'\[ADD_TOPIC:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[ADD_GOAL:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[ADD_NOTE:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[ADD_EMOTIONAL_PATTERN:[^\]]+\]', '', response_text)
        return response_text.strip()
    
    def _apply_updates(self, user_id: str, updates: List[Dict[str, Any]]) -> None:
        """
        Apply personalization updates to storage
        
        Args:
            user_id: User identifier
            updates: List of update commands
        """
        personalization = self.storage.load_personalization(user_id)
        
        for update in updates:
            try:
                if update["type"] == "update":
                    # Update fields - handle nested structures
                    update_data = update["data"]
                    for key, value in update_data.items():
                        if key == "preferences" and isinstance(value, dict):
                            # Merge preferences
                            personalization.setdefault("preferences", {}).update(value)
                            print(f"LLM: Updated preferences: {value}")
                        elif key in personalization:
                            # Direct field update
                            personalization[key] = value
                            print(f"LLM: Updated {key}: {value}")
                        else:
                            # New field
                            personalization[key] = value
                            print(f"LLM: Added new field {key}: {value}")
                
                elif update["type"] == "add_topic":
                    topics = personalization.setdefault("topics_of_interest", [])
                    if update["value"] not in topics:
                        topics.append(update["value"])
                        print(f"LLM: Added topic: {update['value']}")
                
                elif update["type"] == "add_goal":
                    goals = personalization.setdefault("goals", [])
                    if update["value"] not in goals:
                        goals.append(update["value"])
                        print(f"LLM: Added goal: {update['value']}")
                
                elif update["type"] == "add_note":
                    notes = personalization.setdefault("notes", [])
                    notes.append({
                        "text": update["value"],
                        "timestamp": datetime.now().isoformat()
                    })
                    print(f"LLM: Added note: {update['value'][:50]}...")
                
                elif update["type"] == "add_emotional_pattern":
                    patterns = personalization.setdefault("emotional_patterns", [])
                    pattern_data = update["data"].copy()
                    pattern_data.setdefault("timestamp", datetime.now().isoformat())
                    patterns.append(pattern_data)
                    print(f"LLM: Added emotional pattern: {pattern_data}")
            except Exception as e:
                print(f"LLM: Error applying update {update}: {e}")
        
        # Save updated personalization
        if updates:
            self.storage.save_personalization(user_id, personalization)
            print(f"LLM: Saved personalization updates for user {user_id}")
    
    def generate_response(self, user_id: str, user_message: str, 
                        conversation_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generate LLM response with personalization context
        
        Args:
            user_id: User identifier
            user_message: User's message text
            conversation_history: Previous messages in conversation
            
        Returns:
            Dictionary with response text and any updates applied
        """
        if not self.model:
            return {
                "response": "I'm sorry, the AI service is not available right now.",
                "updates_applied": []
            }
        
        try:
            # Build system prompt with personalization
            system_prompt = self._build_system_prompt(user_id)
            
            # Build conversation context
            conversation_text = system_prompt + "\n\nConversation:\n"
            
            if conversation_history:
                for msg in conversation_history[-10:]:  # Last 10 messages for context
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    conversation_text += f"{role.capitalize()}: {content}\n"
            
            conversation_text += f"\nUser: {user_message}\nAssistant:"
            
            # Generate response with fallback
            response_text = self._try_models_with_fallback(conversation_text)
            
            if not response_text:
                return {
                    "response": "I'm sorry, I'm having trouble processing your request right now. Please try again.",
                    "updates_applied": [],
                    "error": "All models failed or rate limited"
                }
            
            # Extract and apply updates
            updates = self._extract_updates(response_text)
            if updates:
                self._apply_updates(user_id, updates)
            
            # Clean response
            clean_response = self._clean_response(response_text)
            
            return {
                "response": clean_response,
                "updates_applied": updates,
                "raw_response": response_text
            }
        except Exception as e:
            print(f"Error generating response: {e}")
            return {
                "response": "I'm sorry, I encountered an error. Could you try again?",
                "updates_applied": [],
                "error": str(e)
            }


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get LLM service instance (singleton)"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

