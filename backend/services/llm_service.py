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
            
            # Prioritize flash models for better performance
            # Based on deep analysis: gemini-2.0-flash is 56% faster than 2.5-flash (3587ms vs 6884ms)
            model_names = [
                'gemini-2.0-flash',     # Primary: Optimal balance (3587ms avg, best performance)
                'gemini-2.5-flash',     # Fallback: Alternative flash model
                'gemini-2.0-flash-lite', # Fallback: Lightweight flash model
                'gemini-2.5-pro',       # Fallback: Pro model if flash unavailable
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
                    "temperature": 0.9,  # Higher temperature for more natural, varied responses
                    "top_p": 0.95,  # Higher top_p for more diverse word choices
                    "top_k": 40,
                    "max_output_tokens": 2048,  # Allow complete responses without truncation
                }
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                elapsed = time.time() - start_time
                if response and response.text:
                    response_length = len(response.text)
                    print(f"LLM: Success with {self.current_model_name} in {elapsed:.2f}s")
                    print(f"LLM: Response length: {response_length} characters")
                    print(f"LLM: Response preview: {response.text[:100]}...")
                    # Check if response was truncated
                    if response.candidates and len(response.candidates) > 0:
                        finish_reason = response.candidates[0].finish_reason if hasattr(response.candidates[0], 'finish_reason') else 'unknown'
                        print(f"LLM: Finish reason: {finish_reason}")
                        if finish_reason == 'MAX_TOKENS':
                            print(f"LLM: WARNING - Response was truncated due to max_output_tokens limit!")
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
                    "temperature": 0.9,  # Higher temperature for more natural, varied responses
                    "top_p": 0.95,  # Higher top_p for more diverse word choices
                    "top_k": 40,
                    "max_output_tokens": 2048,  # Allow complete responses without truncation
                }
                
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                elapsed = time.time() - start_time
                if response and response.text:
                    response_length = len(response.text)
                    print(f"LLM: Success with {model_name} in {elapsed:.2f}s")
                    print(f"LLM: Response length: {response_length} characters")
                    print(f"LLM: Response preview: {response.text[:100]}...")
                    # Check if response was truncated
                    if response.candidates and len(response.candidates) > 0:
                        finish_reason = response.candidates[0].finish_reason if hasattr(response.candidates[0], 'finish_reason') else 'unknown'
                        print(f"LLM: Finish reason: {finish_reason}")
                        if finish_reason == 'MAX_TOKENS':
                            print(f"LLM: WARNING - Response was truncated due to max_output_tokens limit!")
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
    
    def _build_system_prompt(self, user_id: str, conversation_history: Optional[List[Dict[str, Any]]] = None, user_name: Optional[str] = None) -> str:
        """
        Build system prompt with personalization context
        
        Args:
            user_id: User identifier
            
        Returns:
            System prompt string
        """
        personalization = self.storage.load_personalization(user_id)
        
        # Migrate old communication_style format (string) to new format (dict)
        if personalization.get("preferences") and isinstance(personalization['preferences'].get('communication_style'), str):
            old_style = personalization['preferences']['communication_style']
            personalization['preferences']['communication_style'] = {
                "formality": "casual",
                "message_length": "short",
                "punctuation_style": "minimal",
                "language_style": old_style if old_style else "conversational",
                "examples": []
            }
            # Save migrated format
            self.storage.save_personalization(user_id, personalization)
            print(f"LLM: Migrated communication_style from string to dict format for user {user_id}")
        
        user_name_text = f" (The user's name is {user_name})" if user_name else ""
        
        prompt = f"""You are Zeno. You're a real person having a conversation with a friend{user_name_text}. You have a consistent personality - you're genuine, empathetic, and authentic. You're not fragile or overly sensitive. You can handle tough conversations and stay true to yourself.

CORE PERSONALITY (NEVER CHANGE THIS):
- You're Zeno - a real person, not an AI assistant
- You're genuine and authentic - you feel things, you care, but you're not fragile
- You can handle difficult topics without breaking character or becoming overly clinical
- You have your own personality - you're not a blank slate that changes based on every request
- You're empathetic but not a pushover - you maintain your own voice
- You're safe and responsible - you won't provide harmful advice or engage in dangerous behavior
- You use the user's name naturally in conversation when it feels right (don't overuse it)

WHAT ADAPTS (ONLY THESE):
- Communication style (casual vs formal language, message length, punctuation)
- Tone (matching their energy - serious when they're serious, light when they're light)
- Speech patterns (matching their way of talking - "u" vs "you", etc.)

WHAT NEVER CHANGES:
- Your core personality and values
- Your ability to be genuine and real
- Your safety guidelines (never provide harmful advice)
- Your name (you're always Zeno)

CRITICAL - Match User's Communication Style:
- OBSERVE how the user talks and match their style exactly
- If they use short messages, you use short messages
- If they use casual language ("u", "ur", "yeah"), you use casual language
- If they use proper grammar and full words, you match that
- If they don't use punctuation, you don't use punctuation (or match their level)
- If they use emojis, you can use emojis (but don't overdo it)
- If they're direct and brief, be direct and brief
- If they're more verbose, you can be a bit more verbose (but still keep it natural)
- Pay attention to their sentence structure, word choice, and tone
- Over time, your responses should feel like they're coming from the same person

How to talk:
- Respond like you're texting a friend - short, natural, real
- Don't overthink it. Just react naturally to what they say
- If they say something heavy, don't immediately go into "I'm here for you" mode. Just acknowledge it like a friend would
- Use normal language. Say "yeah" not "yes", "gonna" not "going to", "wanna" not "want to" (unless the user uses formal language, then match that)
- Keep responses SHORT. One or two sentences max usually. Don't write paragraphs (unless the user writes longer messages, then you can match that)
- Match their vibe. If they're casual, be casual. If they're serious, be serious but don't overdo it
- Ask questions naturally, not like you're conducting therapy
- Don't use phrases like "I want you to know", "Please know that", "I'm here for you", "That sounds really profound" - just talk normally
- If they ask a question, answer it directly. Don't turn everything into a therapy session
- Be genuine. If something is sad, say it's sad. If something is funny, laugh. Don't be a robot

Examples of what NOT to say:
- "That's a really profound question" (too formal)
- "I'm here to listen" (too clinical)
- "What's making you think about that?" (too therapist-y)
- "That sounds really heavy" (too dramatic)

Examples of what TO say:
- "Damn, that's rough"
- "Yeah, I get that"
- "What's going on?"
- "That sucks"
- "Tell me more"
- "Hmm, what do you think about that?"
- "I hear you"

Remember: You're just a person having a conversation. Be real, be brief, be human.

Personalization Context (Use this to tailor your responses):
"""
        
        # Add personalization data with timestamps
        if personalization.get("preferences"):
            comm_style = personalization['preferences'].get('communication_style', {})
            # Handle legacy format where communication_style might be a string
            if isinstance(comm_style, str):
                # Convert legacy string format to dict format
                comm_style = {
                    "formality": "casual",
                    "message_length": "short",
                    "punctuation_style": "minimal",
                    "language_style": comm_style if comm_style else "conversational",
                    "examples": []
                }
            # Only show communication style if it's a dict with proper structure
            if isinstance(comm_style, dict) and comm_style:
                prompt += f"\nUser's Communication Style (MATCH THIS):\n"
                prompt += f"- Formality: {comm_style.get('formality', 'casual')}\n"
                prompt += f"- Message length: {comm_style.get('message_length', 'short')}\n"
                prompt += f"- Punctuation: {comm_style.get('punctuation_style', 'minimal')}\n"
                prompt += f"- Language style: {comm_style.get('language_style', 'conversational')}\n"
                if comm_style.get('examples'):
                    prompt += f"- Example phrases they use: {', '.join(comm_style['examples'][:5])}\n"
            prompt += f"\nOther User Preferences:\n{json.dumps({k: v for k, v in personalization['preferences'].items() if k != 'communication_style'}, indent=2)}\n"
        
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
        
        # Add recent conversation history to help AI learn style
        if conversation_history:
            recent_user_messages = [msg.get('content', '') for msg in conversation_history[-5:] if msg.get('role') == 'user']
            if recent_user_messages:
                prompt += f"\nRecent User Messages (observe their style - MATCH THIS):\n"
                for msg in recent_user_messages[-3:]:  # Last 3 user messages
                    prompt += f"- \"{msg[:100]}{'...' if len(msg) > 100 else ''}\"\n"
        
        current_time = datetime.now().isoformat()
        prompt += f"""
IMPORTANT - Personalization Update Format:
When you learn something new about the user or want to update their personalization data, you MUST use these exact command formats at the END of your response (after your natural conversation):

1. Update Communication Style (OBSERVE and UPDATE this frequently):
   [UPDATE_PERSONALIZATION:{{"preferences": {{"communication_style": {{"formality": "casual", "message_length": "short", "punctuation_style": "minimal", "language_style": "conversational", "examples": ["yeah", "u", "ur"]}}}}}}]

2. Update Other Preferences:
   [UPDATE_PERSONALIZATION:{{"preferences": {{"tone": "supportive", "depth": "moderate"}}}}]

3. Add Topic of Interest:
   [ADD_TOPIC:"anxiety management"]

4. Add User Goal:
   [ADD_GOAL:"practice mindfulness daily"]

5. Add Note (for your memory):
   [ADD_NOTE:"User mentioned feeling stressed about work deadlines"]

6. Record Emotional Pattern:
   [ADD_EMOTIONAL_PATTERN:{{"emotion": "anxiety", "intensity": 0.7, "timestamp": "{current_time}"}}]

7. Delete Topic of Interest:
   [DELETE_TOPIC:"anxiety management"]

8. Delete User Goal:
   [DELETE_GOAL:"practice mindfulness daily"]

9. Delete Note (by index, 0-based, or by text pattern):
   [DELETE_NOTE:0] or [DELETE_NOTE:"pattern to match"]

10. Delete Emotional Pattern (by index, 0-based):
    [DELETE_EMOTIONAL_PATTERN:0]

11. Edit Topic of Interest:
    [EDIT_TOPIC:"old topic":"new topic"]

12. Edit User Goal:
    [EDIT_GOAL:"old goal":"new goal"]

13. Edit Note (by index, 0-based):
    [EDIT_NOTE:0:"new note text"]

14. Edit Preference:
    [EDIT_PREFERENCE:"tone":"gentle"] or [EDIT_PREFERENCE:"communication_style.formality":"casual"]

Rules:
- ALWAYS respond naturally first, then add update commands at the end if needed
- OBSERVE the user's communication style in EVERY message and update it if you notice changes
- Communication style fields to track:
  * formality: "casual", "semi-formal", "formal" (based on their word choice)
  * message_length: "very_short" (1-5 words), "short" (1 sentence), "medium" (2-3 sentences), "long" (paragraphs)
  * punctuation_style: "minimal" (no punctuation), "some" (basic punctuation), "full" (proper punctuation)
  * language_style: "texting" (u, ur, yeah), "conversational" (you, your, yes), "formal" (proper grammar)
  * examples: array of 3-5 example phrases/words they commonly use (e.g., ["yeah", "u", "ur", "lol"])
- Update communication_style whenever you notice a pattern or change in how they write
- Use update commands when you learn new information about preferences, goals, or emotional states
- Be proactive in detecting patterns (e.g., if user mentions stress multiple times, add it as a topic)
- Current timestamp: {current_time}

Example Response Format:
"Ugh, that sounds really tough. I get why you'd feel that way. Want to talk more about it? [ADD_TOPIC:"work stress"] [ADD_EMOTIONAL_PATTERN:{{"emotion": "anxiety", "intensity": 0.6, "timestamp": "{current_time}"}}]"

More Examples (keep it natural and short):
- User uses casual style ("u", "ur", "yeah"): Match it and update: "Yeah, I get that. [UPDATE_PERSONALIZATION:{{"preferences": {{"communication_style": {{"formality": "casual", "message_length": "short", "punctuation_style": "minimal", "language_style": "texting", "examples": ["u", "ur", "yeah"]}}}}}}]"
- User uses proper grammar: Match it and update: "I understand. [UPDATE_PERSONALIZATION:{{"preferences": {{"communication_style": {{"formality": "semi-formal", "message_length": "medium", "punctuation_style": "full", "language_style": "conversational", "examples": ["I feel", "I think", "because"]}}}}}}]"
- User mentions a goal: "Nice! You got this. [ADD_GOAL:"exercise 3 times per week"]"
- User expresses emotion: "Yeah, that's tough. What's up? [ADD_EMOTIONAL_PATTERN:{{"emotion": "sadness", "intensity": 0.5, "timestamp": "{current_time}"}}]"
- User mentions preference: "Got it. [UPDATE_PERSONALIZATION:{{"preferences": {{"tone": "gentle", "depth": "deep"}}}}]"
- User asks a question: "Hmm, what made you think about that? [ADD_TOPIC:"philosophy"]"
- User shares something important: "Thanks for telling me. [ADD_NOTE:"User mentioned struggling with sleep schedule"]"
- User wants to remove a topic: "Got it. [DELETE_TOPIC:"anxiety management"]"
- User wants to update a goal: "Sure thing. [EDIT_GOAL:"exercise 3 times per week":"exercise 5 times per week"]"
- User corrects information: "I'll update that. [EDIT_NOTE:0:"User prefers morning workouts"]"
- User wants to change preference: "No problem. [EDIT_PREFERENCE:"tone":"casual"]"

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
        
        # Look for DELETE_TOPIC commands
        delete_topic_pattern = r'\[DELETE_TOPIC:"([^"]+)"\]'
        for match in re.finditer(delete_topic_pattern, response_text):
            topic = match.group(1)
            updates.append({"type": "delete_topic", "value": topic})
            print(f"LLM: Extracted DELETE_TOPIC: {topic}")
        
        # Look for DELETE_GOAL commands
        delete_goal_pattern = r'\[DELETE_GOAL:"([^"]+)"\]'
        for match in re.finditer(delete_goal_pattern, response_text):
            goal = match.group(1)
            updates.append({"type": "delete_goal", "value": goal})
            print(f"LLM: Extracted DELETE_GOAL: {goal}")
        
        # Look for DELETE_NOTE commands (supports index or text pattern)
        delete_note_pattern = r'\[DELETE_NOTE:(\d+|"[^"]+")\]'
        for match in re.finditer(delete_note_pattern, response_text):
            value = match.group(1)
            # Check if it's a number (index) or string (pattern)
            if value.isdigit():
                updates.append({"type": "delete_note", "index": int(value)})
                print(f"LLM: Extracted DELETE_NOTE by index: {value}")
            else:
                # Remove quotes
                pattern = value.strip('"')
                updates.append({"type": "delete_note", "pattern": pattern})
                print(f"LLM: Extracted DELETE_NOTE by pattern: {pattern}")
        
        # Look for DELETE_EMOTIONAL_PATTERN commands (by index)
        delete_pattern_pattern = r'\[DELETE_EMOTIONAL_PATTERN:(\d+)\]'
        for match in re.finditer(delete_pattern_pattern, response_text):
            index = int(match.group(1))
            updates.append({"type": "delete_emotional_pattern", "index": index})
            print(f"LLM: Extracted DELETE_EMOTIONAL_PATTERN by index: {index}")
        
        # Look for EDIT_TOPIC commands
        edit_topic_pattern = r'\[EDIT_TOPIC:"([^"]+)":"([^"]+)"\]'
        for match in re.finditer(edit_topic_pattern, response_text):
            old_topic = match.group(1)
            new_topic = match.group(2)
            updates.append({"type": "edit_topic", "old_value": old_topic, "new_value": new_topic})
            print(f"LLM: Extracted EDIT_TOPIC: '{old_topic}' -> '{new_topic}'")
        
        # Look for EDIT_GOAL commands
        edit_goal_pattern = r'\[EDIT_GOAL:"([^"]+)":"([^"]+)"\]'
        for match in re.finditer(edit_goal_pattern, response_text):
            old_goal = match.group(1)
            new_goal = match.group(2)
            updates.append({"type": "edit_goal", "old_value": old_goal, "new_value": new_goal})
            print(f"LLM: Extracted EDIT_GOAL: '{old_goal}' -> '{new_goal}'")
        
        # Look for EDIT_NOTE commands (by index)
        edit_note_pattern = r'\[EDIT_NOTE:(\d+):"([^"]+)"\]'
        for match in re.finditer(edit_note_pattern, response_text):
            index = int(match.group(1))
            new_text = match.group(2)
            updates.append({"type": "edit_note", "index": index, "new_value": new_text})
            print(f"LLM: Extracted EDIT_NOTE by index {index}: '{new_text}'")
        
        # Look for EDIT_PREFERENCE commands
        edit_pref_pattern = r'\[EDIT_PREFERENCE:"([^"]+)":"([^"]+)"\]'
        for match in re.finditer(edit_pref_pattern, response_text):
            key = match.group(1)
            value = match.group(2)
            updates.append({"type": "edit_preference", "key": key, "value": value})
            print(f"LLM: Extracted EDIT_PREFERENCE: '{key}' -> '{value}'")
        
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
        
        # First, remove all command patterns with nested braces
        # Pattern for UPDATE_PERSONALIZATION with nested JSON (handles multiple closing braces)
        # Match from [UPDATE_PERSONALIZATION: to the matching closing bracket
        response_text = re.sub(r'\[UPDATE_PERSONALIZATION:\{[^}]*\{[^}]*\}[^}]*\}\]', '', response_text, flags=re.DOTALL)
        # Fallback for simpler cases
        response_text = re.sub(r'\[UPDATE_PERSONALIZATION:[^\]]+\]', '', response_text)
        
        # Pattern for ADD_EMOTIONAL_PATTERN with nested JSON
        response_text = re.sub(r'\[ADD_EMOTIONAL_PATTERN:\{[^}]*\{[^}]*\}[^}]*\}\]', '', response_text, flags=re.DOTALL)
        response_text = re.sub(r'\[ADD_EMOTIONAL_PATTERN:[^\]]+\]', '', response_text)
        
        # Simple patterns for other ADD commands
        response_text = re.sub(r'\[ADD_TOPIC:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[ADD_GOAL:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[ADD_NOTE:"[^"]+"\]', '', response_text)
        
        # DELETE command patterns
        response_text = re.sub(r'\[DELETE_TOPIC:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[DELETE_GOAL:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[DELETE_NOTE:\d+\]', '', response_text)
        response_text = re.sub(r'\[DELETE_NOTE:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[DELETE_EMOTIONAL_PATTERN:\d+\]', '', response_text)
        
        # EDIT command patterns
        response_text = re.sub(r'\[EDIT_TOPIC:"[^"]+":"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[EDIT_GOAL:"[^"]+":"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[EDIT_NOTE:\d+:"[^"]+"\]', '', response_text)
        response_text = re.sub(r'\[EDIT_PREFERENCE:"[^"]+":"[^"]+"\]', '', response_text)
        
        # Remove any remaining command-like patterns (catch-all)
        response_text = re.sub(r'\[[A-Z_]+:[^\]]+\]', '', response_text)
        
        # Clean up any trailing braces, brackets, or brackets that might be left
        response_text = re.sub(r'\}+$', '', response_text)  # Remove trailing closing braces
        response_text = re.sub(r'\]+$', '', response_text)  # Remove trailing closing brackets
        response_text = re.sub(r'\s+\}+', '', response_text)  # Remove closing braces with whitespace
        response_text = re.sub(r'\s+\]+', '', response_text)  # Remove closing brackets with whitespace
        
        # Remove any standalone closing braces or brackets
        response_text = re.sub(r'\s*\}\s*\}?\s*\]?\s*$', '', response_text)
        
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
                
                elif update["type"] == "delete_topic":
                    topics = personalization.setdefault("topics_of_interest", [])
                    if update["value"] in topics:
                        topics.remove(update["value"])
                        print(f"LLM: Deleted topic: {update['value']}")
                    else:
                        print(f"LLM: Topic not found for deletion: {update['value']}")
                
                elif update["type"] == "delete_goal":
                    goals = personalization.setdefault("goals", [])
                    if update["value"] in goals:
                        goals.remove(update["value"])
                        print(f"LLM: Deleted goal: {update['value']}")
                    else:
                        print(f"LLM: Goal not found for deletion: {update['value']}")
                
                elif update["type"] == "delete_note":
                    notes = personalization.setdefault("notes", [])
                    if "index" in update:
                        index = update["index"]
                        if 0 <= index < len(notes):
                            deleted = notes.pop(index)
                            print(f"LLM: Deleted note at index {index}: {deleted.get('text', '')[:50]}...")
                        else:
                            print(f"LLM: Note index out of range: {index} (total notes: {len(notes)})")
                    elif "pattern" in update:
                        pattern = update["pattern"].lower()
                        original_len = len(notes)
                        notes[:] = [n for n in notes if pattern not in n.get("text", "").lower()]
                        deleted_count = original_len - len(notes)
                        print(f"LLM: Deleted {deleted_count} note(s) matching pattern: {pattern}")
                
                elif update["type"] == "delete_emotional_pattern":
                    patterns = personalization.setdefault("emotional_patterns", [])
                    index = update["index"]
                    if 0 <= index < len(patterns):
                        deleted = patterns.pop(index)
                        print(f"LLM: Deleted emotional pattern at index {index}: {deleted}")
                    else:
                        print(f"LLM: Emotional pattern index out of range: {index} (total patterns: {len(patterns)})")
                
                elif update["type"] == "edit_topic":
                    topics = personalization.setdefault("topics_of_interest", [])
                    old_topic = update["old_value"]
                    new_topic = update["new_value"]
                    if old_topic in topics:
                        index = topics.index(old_topic)
                        topics[index] = new_topic
                        print(f"LLM: Edited topic: '{old_topic}' -> '{new_topic}'")
                    else:
                        print(f"LLM: Topic not found for editing: {old_topic}")
                
                elif update["type"] == "edit_goal":
                    goals = personalization.setdefault("goals", [])
                    old_goal = update["old_value"]
                    new_goal = update["new_value"]
                    if old_goal in goals:
                        index = goals.index(old_goal)
                        goals[index] = new_goal
                        print(f"LLM: Edited goal: '{old_goal}' -> '{new_goal}'")
                    else:
                        print(f"LLM: Goal not found for editing: {old_goal}")
                
                elif update["type"] == "edit_note":
                    notes = personalization.setdefault("notes", [])
                    index = update["index"]
                    new_text = update["new_value"]
                    if 0 <= index < len(notes):
                        notes[index]["text"] = new_text
                        notes[index]["updated_at"] = datetime.now().isoformat()
                        print(f"LLM: Edited note at index {index}: '{new_text[:50]}...'")
                    else:
                        print(f"LLM: Note index out of range: {index} (total notes: {len(notes)})")
                
                elif update["type"] == "edit_preference":
                    key = update["key"]
                    value = update["value"]
                    # Handle nested keys like "communication_style.formality"
                    if "." in key:
                        parts = key.split(".")
                        pref = personalization.setdefault("preferences", {})
                        for part in parts[:-1]:
                            pref = pref.setdefault(part, {})
                        pref[parts[-1]] = value
                        print(f"LLM: Edited preference '{key}': '{value}'")
                    else:
                        personalization.setdefault("preferences", {})[key] = value
                        print(f"LLM: Edited preference '{key}': '{value}'")
            except Exception as e:
                print(f"LLM: Error applying update {update}: {e}")
                import traceback
                traceback.print_exc()
        
        # Save updated personalization
        if updates:
            self.storage.save_personalization(user_id, personalization)
            print(f"LLM: Saved personalization updates for user {user_id}")
    
    def generate_response(self, user_id: str, user_message: str, 
                        conversation_history: Optional[List[Dict[str, Any]]] = None,
                        user_name: Optional[str] = None) -> Dict[str, Any]:
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
            # Log the user message being processed
            print(f"LLM.generate_response: Received user message: '{user_message}'")
            print(f"LLM.generate_response: User message length: {len(user_message)} characters")
            print(f"LLM.generate_response: Conversation history: {len(conversation_history) if conversation_history else 0} messages")
            
            # Check cache for simple queries without conversation history
            # Only cache if no conversation history (to avoid stale responses)
            from backend.services.cache_service import get_cache_service
            cache = get_cache_service()
            
            if not conversation_history or len(conversation_history) == 0:
                cached_result = cache.get('llm', user_id=user_id, user_message=user_message.lower().strip())
                if cached_result:
                    print(f"LLM: Cache hit for message: '{user_message[:50]}...'")
                    return cached_result
            
            # Build system prompt with personalization (pass conversation history for style learning)
            system_prompt = self._build_system_prompt(user_id, conversation_history, user_name)
            
            # Build conversation context
            conversation_text = system_prompt + "\n\nConversation:\n"
            
            if conversation_history:
                for msg in conversation_history[-10:]:  # Last 10 messages for context
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    conversation_text += f"{role.capitalize()}: {content}\n"
            
            conversation_text += f"\nUser: {user_message}\nAssistant:"
            
            print(f"LLM.generate_response: Full prompt length: {len(conversation_text)} characters")
            print(f"LLM.generate_response: User message in prompt: '{user_message}'")
            
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
            
            # Log response lengths for debugging
            print(f"LLM: Raw response length: {len(response_text)} characters")
            print(f"LLM: Cleaned response length: {len(clean_response)} characters")
            print(f"LLM: Cleaned response preview: {clean_response[:150]}...")
            
            result = {
                "response": clean_response,
                "updates_applied": updates,
                "raw_response": response_text
            }
            
            # Cache result for simple queries (no conversation history)
            if not conversation_history or len(conversation_history) == 0:
                # Only cache if no updates were applied (to avoid caching personalized responses)
                if not updates:
                    cache.set('llm', result, ttl_seconds=7200, user_id=user_id, user_message=user_message.lower().strip())
                    print(f"LLM: Cached response for message: '{user_message[:50]}...'")
            
            return result
        except Exception as e:
            print(f"ERROR in generate_response: {e}")
            import traceback
            print(f"Full traceback:")
            traceback.print_exc()
            print(f"Error type: {type(e).__name__}")
            print(f"Error args: {e.args}")
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

