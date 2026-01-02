import React, { useState } from 'react';
import { Mail, Lock, User as UserIcon } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { User } from '../types';

interface LoginCardProps {
  onLogin: (user: User) => void;
}

interface MockAccount extends User {
    // extending User from types
}

export const LoginCard: React.FC<LoginCardProps> = ({ onLogin }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [showGoogleModal, setShowGoogleModal] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);

    // Strict Account Isolation Logic
    // 1. Normalize Email
    const normalizedEmail = email.trim().toLowerCase();
    
    // 2. Generate Deterministic ID
    // Simple hash to hex string simulation
    const simpleHash = btoa(normalizedEmail).replace(/[^a-zA-Z0-9]/g, "").substring(0, 16);
    const accountId = `user_${simpleHash}`;

    // 3. Construct User Object
    const user: User = {
        id: accountId,
        name: normalizedEmail.split('@')[0], // Use part before @ as display name
        email: normalizedEmail,
        avatarColor: "bg-primary"
    };

    setTimeout(() => onLogin(user), 1000);
  };

  const handleGoogleClick = () => {
    setShowGoogleModal(true);
  };

  const selectGoogleAccount = (account: MockAccount) => {
    setShowGoogleModal(false);
    setIsLoading(true);
    
    // Ensure Google accounts also follow isolation principles if they were dynamic
    // Here we use the predefined accounts, but in a real app we'd normalize their IDs too
    setTimeout(() => onLogin(account), 1500);
  };

  const accounts: MockAccount[] = [
    { id: "user_demo_001", name: "Demo User", email: "demo.user@example.com", avatarColor: "bg-neutral" },
    { id: "user_zeno_002", name: "Zeno Fan", email: "zeno.lover@example.com", avatarColor: "bg-primary" }
  ];

  return (
    <>
      <div className="bg-white rounded-2xl p-6 md:p-8 shadow-[0_10px_30px_rgba(0,0,0,0.06)] border border-gray-100 relative z-20">
          <form onSubmit={handleSignIn} className="space-y-4">
            <div className="relative">
               <Mail className="absolute left-4 top-3.5 text-gray-400 w-5 h-5" />
               <input 
                  type="email" 
                  placeholder="Email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input input-bordered w-full pl-11 bg-gray-50 border-gray-200 focus:border-primary focus:ring-1 focus:ring-primary rounded-xl text-gray-700 placeholder:text-gray-400 h-12" 
                  required 
               />
            </div>
            
            <div className="relative">
               <Lock className="absolute left-4 top-3.5 text-gray-400 w-5 h-5" />
               <input 
                  type="password" 
                  placeholder="Password" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input input-bordered w-full pl-11 bg-gray-50 border-gray-200 focus:border-primary focus:ring-1 focus:ring-primary rounded-xl text-gray-700 placeholder:text-gray-400 h-12" 
                  required 
               />
            </div>

            <button 
              type="submit" 
              className="btn w-full bg-primary hover:bg-primary-hover text-white border-none rounded-xl h-12 text-base font-medium shadow-sm normal-case" 
              disabled={isLoading}
            >
              {isLoading ? <span className="loading loading-spinner"></span> : "Sign In"}
            </button>
          </form>

          <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200"></div>
              </div>
              <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-gray-400 font-medium">OR</span>
              </div>
          </div>

          <button 
              onClick={handleGoogleClick}
              disabled={isLoading}
              className="w-full border border-gray-200 rounded-xl py-3 flex items-center justify-center gap-3 bg-white hover:bg-gray-50 transition-colors h-12 disabled:opacity-50"
          >
              <svg viewBox="0 0 24 24" className="w-5 h-5" xmlns="http://www.w3.org/2000/svg">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              <span className="text-gray-700 text-sm font-medium">Continue with Google</span>
          </button>
      </div>

      {/* Mock Google Account Selector Modal */}
      <AnimatePresence>
        {showGoogleModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowGoogleModal(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            
            <motion.div 
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden relative z-10"
            >
              <div className="p-6 border-b border-gray-100 flex flex-col items-center">
                 <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center mb-2">
                    <svg viewBox="0 0 24 24" className="w-8 h-8" xmlns="http://www.w3.org/2000/svg">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                    </svg>
                 </div>
                 <h3 className="text-xl font-medium text-gray-800">Choose an account</h3>
                 <p className="text-sm text-gray-500 mt-1">to continue to Talk with Zeno</p>
              </div>

              <div className="py-2">
                  {accounts.map((acc) => (
                    <button 
                      key={acc.id}
                      onClick={() => selectGoogleAccount(acc)}
                      className="w-full px-6 py-4 flex items-center gap-4 hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0 text-left group"
                    >
                        <div className={`w-10 h-10 rounded-full ${acc.avatarColor} text-white flex items-center justify-center text-sm font-medium`}>
                          {acc.name.charAt(0)}
                        </div>
                        <div className="flex-1">
                           <div className="text-sm font-medium text-gray-700">{acc.name}</div>
                           <div className="text-xs text-gray-500">{acc.email}</div>
                        </div>
                    </button>
                  ))}
                  
                  <button className="w-full px-6 py-4 flex items-center gap-4 hover:bg-gray-50 transition-colors text-left text-gray-600">
                       <div className="w-10 h-10 rounded-full border border-gray-200 flex items-center justify-center text-gray-400">
                          <UserIcon size={20} />
                       </div>
                       <span className="text-sm font-medium">Use another account</span>
                  </button>
              </div>

              <div className="p-4 border-t border-gray-100 bg-gray-50/50 text-center">
                 <p className="text-xs text-gray-500 max-w-xs mx-auto">
                    To continue, Google will share your name, email address, and language preference with Zeno.
                 </p>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};