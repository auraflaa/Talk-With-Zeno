"""
File System Storage Service
Manages chat history and personalization data storage
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path


class StorageService:
    """File system storage for chats and personalization"""
    
    def __init__(self, base_path: str = "data"):
        """
        Initialize storage service
        
        Args:
            base_path: Base directory for storage
        """
        self.base_path = Path(base_path)
        self.chats_path = self.base_path / "chats"
        self.personalization_path = self.base_path / "personalization"
        
        # Create directories if they don't exist
        self.chats_path.mkdir(parents=True, exist_ok=True)
        self.personalization_path.mkdir(parents=True, exist_ok=True)
    
    # ========== Chat History Methods ==========
    
    def save_conversation(self, user_id: str, conversation_id: str, messages: List[Dict[str, Any]]) -> bool:
        """
        Save a conversation to a JSON file (1 conversation = 1 file)
        
        Args:
            user_id: User identifier
            conversation_id: Unique conversation ID
            messages: List of message objects
            
        Returns:
            True if saved successfully
        """
        try:
            user_chats_dir = self.chats_path / user_id
            user_chats_dir.mkdir(parents=True, exist_ok=True)
            
            conversation_file = user_chats_dir / f"{conversation_id}.json"
            
            # Load existing conversation to preserve created_at
            existing = self.load_conversation(user_id, conversation_id)
            created_at = existing.get("created_at") if existing else datetime.now().isoformat()
            
            conversation_data = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "created_at": created_at,
                "updated_at": datetime.now().isoformat(),
                "message_count": len(messages),
                "messages": messages
            }
            
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error saving conversation: {e}")
            return False
    
    def load_conversation(self, user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a conversation from JSON file
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID
            
        Returns:
            Conversation data or None if not found
        """
        try:
            conversation_file = self.chats_path / user_id / f"{conversation_id}.json"
            
            if not conversation_file.exists():
                return None
            
            with open(conversation_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading conversation: {e}")
            return None
    
    def add_message_to_conversation(self, user_id: str, conversation_id: str, 
                                   message: Dict[str, Any]) -> bool:
        """
        Add a message to an existing conversation
        
        Args:
            user_id: User identifier
            conversation_id: Conversation ID
            message: Message object to add
            
        Returns:
            True if added successfully
        """
        conversation = self.load_conversation(user_id, conversation_id)
        
        if conversation is None:
            # Create new conversation
            conversation = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "messages": []
            }
        
        # Add message
        conversation["messages"].append(message)
        conversation["updated_at"] = datetime.now().isoformat()
        
        # Save updated conversation
        return self.save_conversation(user_id, conversation_id, conversation["messages"])
    
    def list_user_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """
        List all conversations for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of conversation metadata
        """
        try:
            user_chats_dir = self.chats_path / user_id
            
            if not user_chats_dir.exists():
                return []
            
            conversations = []
            for conversation_file in user_chats_dir.glob("*.json"):
                with open(conversation_file, 'r', encoding='utf-8') as f:
                    conv_data = json.load(f)
                    conversations.append({
                        "conversation_id": conv_data.get("conversation_id"),
                        "created_at": conv_data.get("created_at"),
                        "updated_at": conv_data.get("updated_at"),
                        "message_count": len(conv_data.get("messages", []))
                    })
            
            # Sort by updated_at descending
            conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return conversations
        except Exception as e:
            print(f"Error listing conversations: {e}")
            return []
    
    # ========== Personalization Methods ==========
    
    def load_personalization(self, user_id: str) -> Dict[str, Any]:
        """
        Load user personalization data (1 file per user)
        
        Args:
            user_id: User identifier
            
        Returns:
            Personalization data dictionary
        """
        try:
            personalization_file = self.personalization_path / f"{user_id}.json"
            
            if not personalization_file.exists():
                # Return default personalization
                return self._get_default_personalization(user_id)
            
            with open(personalization_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure all required fields exist
                default = self._get_default_personalization(user_id)
                default.update(data)
                return default
        except Exception as e:
            print(f"Error loading personalization: {e}")
            return self._get_default_personalization(user_id)
    
    def save_personalization(self, user_id: str, personalization: Dict[str, Any]) -> bool:
        """
        Save user personalization data
        
        Args:
            user_id: User identifier
            personalization: Personalization data dictionary
            
        Returns:
            True if saved successfully
        """
        try:
            personalization_file = self.personalization_path / f"{user_id}.json"
            
            # Add metadata
            personalization["updated_at"] = datetime.now().isoformat()
            if "created_at" not in personalization:
                personalization["created_at"] = datetime.now().isoformat()
            
            with open(personalization_file, 'w', encoding='utf-8') as f:
                json.dump(personalization, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"Error saving personalization: {e}")
            return False
    
    def update_personalization_field(self, user_id: str, field: str, value: Any) -> bool:
        """
        Update a specific field in personalization
        
        Args:
            user_id: User identifier
            field: Field name to update
            value: New value
            
        Returns:
            True if updated successfully
        """
        personalization = self.load_personalization(user_id)
        personalization[field] = value
        return self.save_personalization(user_id, personalization)
    
    def _get_default_personalization(self, user_id: str) -> Dict[str, Any]:
        """Get default personalization structure"""
        return {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "preferences": {
                "tone": "supportive",
                "depth": "moderate",
                "communication_style": {
                    "formality": "casual",
                    "message_length": "short",
                    "punctuation_style": "minimal",
                    "language_style": "conversational",
                    "examples": []
                }
            },
            "emotional_patterns": [],
            "topics_of_interest": [],
            "goals": [],
            "notes": [],
            "metadata": {}
        }


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service(base_path: Optional[str] = None) -> StorageService:
    """Get storage service instance (singleton)"""
    global _storage_service
    if _storage_service is None:
        if base_path:
            _storage_service = StorageService(base_path)
        else:
            _storage_service = StorageService()
    return _storage_service

