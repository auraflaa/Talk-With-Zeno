import React, { useState, useEffect } from 'react';
import { LandingPage } from './components/LandingPage';
import { Dashboard } from './components/Dashboard';
import { AppMode, User } from './types';

const App: React.FC = () => {
  // --- USER STATE MANAGEMENT ---
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    const savedUser = localStorage.getItem('zeno_current_user');
    return savedUser ? JSON.parse(savedUser) : null;
  });

  const [appMode, setAppMode] = useState<AppMode>(() => {
    return localStorage.getItem('zeno_current_user') 
      ? AppMode.AUTHENTICATED 
      : AppMode.LOGIN;
  });

  // --- THEME STATE MANAGEMENT (User Scoped) ---
  // Single Source of Truth: 'light' | 'dark'
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  // Load User's specific theme on mount or user change
  useEffect(() => {
    // Determine target theme
    let targetTheme: 'light' | 'dark' = 'light';
    
    if (currentUser) {
      const userThemeKey = `zeno_theme_${currentUser.id}`;
      const savedTheme = localStorage.getItem(userThemeKey) as 'light' | 'dark';
      if (savedTheme) {
        targetTheme = savedTheme;
      }
    }

    setTheme(targetTheme);
    
    // Apply to Root Element immediately
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(targetTheme);
    
    // Update theme-color meta tag for mobile browsers
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
        metaThemeColor.setAttribute('content', targetTheme === 'dark' ? '#0b1220' : '#ffffff');
    }

  }, [currentUser]); // Re-run when user changes

  // --- HANDLERS ---

  const handleLogin = (user: User) => {
    setCurrentUser(user);
    localStorage.setItem('zeno_current_user', JSON.stringify(user));
    setAppMode(AppMode.AUTHENTICATED);
  };

  const handleLogout = () => {
    setCurrentUser(null);
    localStorage.removeItem('zeno_current_user');
    setAppMode(AppMode.LOGIN);
    
    // Reset to light on logout
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
    setTheme('light');
  };

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    
    // Apply Class
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(newTheme);

    // Persist if user logged in
    if (currentUser) {
       localStorage.setItem(`zeno_theme_${currentUser.id}`, newTheme);
    }
  };

  return (
    <div className="relative w-full h-screen bg-base-100 overflow-hidden text-base-content font-sans transition-colors duration-300">
      <div className="relative z-10 w-full h-full">
        {appMode === AppMode.LOGIN ? (
          <LandingPage onLogin={handleLogin} />
        ) : (
          <Dashboard 
            key={currentUser?.id} 
            currentUser={currentUser!}
            onLogout={handleLogout} 
            theme={theme}
            toggleTheme={toggleTheme}
          />
        )}
      </div>
    </div>
  );
};

export default App;