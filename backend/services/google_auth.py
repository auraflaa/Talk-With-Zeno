"""
Google OAuth Authentication Service
Handles Google OAuth flow and user data synchronization with SQLite
"""

import os
import requests
from typing import Optional, Dict, Any
from backend.services.database import get_database


class GoogleAuthService:
    """Service for Google OAuth authentication"""
    
    def __init__(self):
        self.client_id = os.getenv('VITE_GOOGLE_CLIENT_ID') or os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:3000/auth/callback')
        self.db = get_database()
    
    def get_authorization_url(self) -> str:
        """
        Generate Google OAuth authorization URL
        
        Returns:
            Authorization URL for redirecting user
        """
        scopes = 'openid email profile'
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"response_type=code&"
            f"scope={scopes}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Exchange authorization code for access token
        
        Args:
            code: Authorization code from Google callback
            
        Returns:
            Token response dictionary or None if failed
        """
        token_url = 'https://oauth2.googleapis.com/token'
        
        data = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error exchanging code for token: {e}")
            return None
    
    def get_user_profile(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Get user profile from Google using access token
        
        Args:
            access_token: Google access token
            
        Returns:
            User profile dictionary or None if failed
        """
        profile_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(profile_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting user profile: {e}")
            return None
    
    def authenticate_user(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Complete authentication flow: code → token → profile → SQLite
        
        Args:
            code: Authorization code from Google callback
            
        Returns:
            User dictionary from SQLite or None if failed
        """
        # Exchange code for token
        token_response = self.exchange_code_for_token(code)
        if not token_response:
            return None
        
        access_token = token_response.get('access_token')
        if not access_token:
            return None
        
        # Get user profile from Google
        google_profile = self.get_user_profile(access_token)
        if not google_profile:
            return None
        
        # Extract user data
        google_id = google_profile.get('id')
        email = google_profile.get('email')
        name = google_profile.get('name', email.split('@')[0])
        picture = google_profile.get('picture')
        
        if not email:
            return None
        
        # Check if user exists in SQLite
        existing_user = self.db.get_user_by_email(email)
        
        if existing_user:
            # Update existing user (in case name or profile changed)
            user_id = existing_user['id']
            self.db.update_user(
                user_id,
                name=name,
                email=email
            )
            return self.db.get_user(user_id)
        else:
            # Create new user
            # Use Google ID as part of user ID
            user_id = f"google_{google_id}" if google_id else f"user_{hash(email) % 1000000}"
            
            # Extract avatar color from picture or use default
            avatar_color = "bg-primary"  # Default, can be enhanced
            
            self.db.create_user(
                user_id=user_id,
                name=name,
                email=email,
                avatar_color=avatar_color,
                preferences={
                    'googleId': google_id,
                    'picture': picture,
                    'verifiedEmail': google_profile.get('verified_email', False)
                }
            )
            
            return self.db.get_user(user_id)
    
    def get_or_create_user_from_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Get or create user from Google access token (for token refresh scenarios)
        
        Args:
            access_token: Google access token
            
        Returns:
            User dictionary from SQLite or None if failed
        """
        google_profile = self.get_user_profile(access_token)
        if not google_profile:
            return None
        
        email = google_profile.get('email')
        if not email:
            return None
        
        # Check if user exists
        existing_user = self.db.get_user_by_email(email)
        
        if existing_user:
            return existing_user
        
        # Create new user
        google_id = google_profile.get('id')
        name = google_profile.get('name', email.split('@')[0])
        user_id = f"google_{google_id}" if google_id else f"user_{hash(email) % 1000000}"
        
        self.db.create_user(
            user_id=user_id,
            name=name,
            email=email,
            avatar_color="bg-primary",
            preferences={
                'googleId': google_id,
                'picture': google_profile.get('picture'),
                'verifiedEmail': google_profile.get('verified_email', False)
            }
        )
        
        return self.db.get_user(user_id)


# Singleton instance
_auth_service: Optional[GoogleAuthService] = None


def get_google_auth_service() -> GoogleAuthService:
    """Get Google auth service instance (singleton)"""
    global _auth_service
    if _auth_service is None:
        _auth_service = GoogleAuthService()
    return _auth_service

