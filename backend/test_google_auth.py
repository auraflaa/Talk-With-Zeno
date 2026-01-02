"""
Test Google OAuth authentication service
Verifies Google Auth configuration and functionality
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Load environment variables
env_path = parent_dir / '.env.local'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv('.env.local')

from backend.services.google_auth import get_google_auth_service
from backend.services.database import get_database


def test_google_auth_config():
    """Test Google Auth configuration"""
    print("\n" + "="*60)
    print("TESTING GOOGLE AUTH CONFIGURATION")
    print("="*60)
    
    # Check environment variables
    client_id = os.getenv('VITE_GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI')
    
    print("\n[CHECK] Environment Variables:")
    
    if client_id:
        masked = client_id[:20] + "..." if len(client_id) > 20 else client_id
        print(f"  [OK] VITE_GOOGLE_CLIENT_ID: {masked}")
    else:
        print(f"  [X] VITE_GOOGLE_CLIENT_ID: Not set")
        return False
    
    if client_secret:
        masked = client_secret[:20] + "..." if len(client_secret) > 20 else client_secret
        print(f"  [OK] GOOGLE_CLIENT_SECRET: {masked}")
    else:
        print(f"  [X] GOOGLE_CLIENT_SECRET: Not set")
        return False
    
    if redirect_uri:
        print(f"  [OK] GOOGLE_REDIRECT_URI: {redirect_uri}")
    else:
        print(f"  [X] GOOGLE_REDIRECT_URI: Not set")
        return False
    
    return True


def test_google_auth_service():
    """Test Google Auth service initialization"""
    print("\n" + "="*60)
    print("TESTING GOOGLE AUTH SERVICE")
    print("="*60)
    
    try:
        auth_service = get_google_auth_service()
        
        print("\n[OK] Google Auth Service initialized")
        print(f"    Client ID configured: {bool(auth_service.client_id)}")
        print(f"    Client Secret configured: {bool(auth_service.client_secret)}")
        print(f"    Redirect URI: {auth_service.redirect_uri}")
        
        # Check if database is connected
        if auth_service.db:
            print(f"    Database connected: Yes")
        else:
            print(f"    Database connected: No")
            return False
        
        return True
    except Exception as e:
        print(f"\n[X] Error initializing Google Auth service: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_auth_url_generation():
    """Test authorization URL generation"""
    print("\n" + "="*60)
    print("TESTING AUTH URL GENERATION")
    print("="*60)
    
    try:
        auth_service = get_google_auth_service()
        
        # Generate auth URL
        auth_url = auth_service.get_authorization_url()
        
        if auth_url:
            print(f"\n[OK] Authorization URL generated")
            print(f"    URL: {auth_url[:80]}...")
            
            # Check URL contains required parameters
            required_params = ['client_id', 'redirect_uri', 'response_type', 'scope']
            missing = []
            for param in required_params:
                if param not in auth_url:
                    missing.append(param)
            
            if missing:
                print(f"    [WARNING] Missing parameters: {', '.join(missing)}")
                return False
            else:
                print(f"    [OK] All required parameters present")
                return True
        else:
            print(f"\n[X] Failed to generate authorization URL")
            return False
    except Exception as e:
        print(f"\n[X] Error generating auth URL: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_integration():
    """Test database integration for user storage"""
    print("\n" + "="*60)
    print("TESTING DATABASE INTEGRATION")
    print("="*60)
    
    try:
        db = get_database()
        auth_service = get_google_auth_service()
        
        # Test user creation via auth service
        test_user_id = "test_google_auth_user"
        test_email = "test.google@example.com"
        
        # Clean up if exists
        existing = db.get_user(test_user_id)
        if existing:
            db.delete_user(test_user_id)
        
        # Create test user
        created = db.create_user(
            user_id=test_user_id,
            name="Test Google User",
            email=test_email,
            avatar_color="bg-primary"
        )
        
        if not created:
            print("[X] Failed to create test user")
            return False
        
        print("[OK] Test user created")
        
        # Retrieve user
        user = db.get_user(test_user_id)
        if not user:
            print("[X] Failed to retrieve test user")
            return False
        
        print("[OK] Test user retrieved")
        print(f"    User: {user['name']} ({user['email']})")
        
        # Cleanup
        db.delete_user(test_user_id)
        print("[OK] Test user cleaned up")
        
        return True
    except Exception as e:
        print(f"[X] Error in database integration: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoints():
    """Check if Google Auth API endpoints are registered"""
    print("\n" + "="*60)
    print("TESTING API ENDPOINTS")
    print("="*60)
    
    try:
        from backend.app import app
        
        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint != 'static' and 'auth' in rule.rule.lower():
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
                    'path': rule.rule
                })
        
        if routes:
            print(f"\n[OK] Found {len(routes)} Google Auth endpoints:")
            for route in routes:
                methods = ', '.join(route['methods'])
                print(f"    {methods:15} {route['path']}")
            
            # Check for critical endpoints
            expected_endpoints = ['/api/auth/google', '/api/auth/google/callback']
            found = [r['path'] for r in routes]
            
            missing = [ep for ep in expected_endpoints if ep not in found]
            if missing:
                print(f"\n[WARNING] Missing endpoints: {', '.join(missing)}")
                print("    Note: These may be in api_example.py (example file)")
                return False
            else:
                print(f"\n[OK] All expected endpoints found")
                return True
        else:
            print(f"\n[WARNING] No Google Auth endpoints found in app.py")
            print("    Note: Google Auth endpoints may need to be added to app.py")
            print("    Check google_auth_integration.md for integration guide")
            return False
            
    except Exception as e:
        print(f"[X] Error checking API endpoints: {e}")
        return False


def main():
    """Run all Google Auth tests"""
    print("="*60)
    print("GOOGLE AUTH TEST SUITE")
    print("="*60)
    
    results = {
        'Configuration': test_google_auth_config(),
        'Service Initialization': test_google_auth_service(),
        'Auth URL Generation': test_auth_url_generation(),
        'Database Integration': test_database_integration(),
        'API Endpoints': test_api_endpoints()
    }
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        status = "[OK]" if result else "[X]"
        print(f"{status} {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("[SUCCESS] Google Auth is fully configured and working!")
    else:
        print("[WARNING] Some Google Auth components need attention.")
        print("\nNext steps:")
        if not results['Configuration']:
            print("  1. Set up environment variables in .env.local:")
            print("     - VITE_GOOGLE_CLIENT_ID")
            print("     - GOOGLE_CLIENT_SECRET")
            print("     - GOOGLE_REDIRECT_URI")
        if not results['API Endpoints']:
            print("  2. Add Google Auth endpoints to backend/app.py")
            print("     See: backend/google_auth_integration.md")
    print("="*60)
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

