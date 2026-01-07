import React from 'react';
import { motion } from 'framer-motion';
import { LoginCard } from './LoginCard';
import { User } from '../types';

interface LandingPageProps {
  onLogin: (user: User) => void;
}

interface GraphicProps {
  scale?: number;
  opacity?: number;
  className?: string;
  delay?: number;
}

const ZenStonesGraphic: React.FC<GraphicProps> = ({ scale = 1, opacity = 1, className = "", delay = 0 }) => {
  return (
    <div 
      className={`flex flex-col items-center origin-bottom ${className}`}
      style={{ transform: `scale(${scale})`, opacity }}
    >
      {/* Floating Stack Wrapper */}
      <motion.div 
        animate={{ y: [0, -8, 0] }} 
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", delay }}
        className="flex flex-col items-center relative z-10"
      >
         {/* Top Stone (Sage Accent) */}
         <div className="w-16 h-10 bg-[#1f7a70] rounded-[40%_60%_60%_40%/50%_50%_50%_50%] shadow-sm z-30 -mb-3 opacity-90"></div>
         
         {/* Middle Stone (Light Gray) */}
         <div className="w-24 h-14 bg-gray-300 rounded-[50%_50%_40%_60%/60%_50%_50%_40%] shadow-sm z-20 -mb-4"></div>
         
         {/* Bottom Stone (Darker Gray) */}
         <div className="w-36 h-16 bg-gray-400 rounded-[60%_40%_50%_50%/50%_60%_40%_50%] shadow-md z-10"></div>
      </motion.div>
      
      {/* Soft Shadow on Floor */}
      <motion.div 
        animate={{ scale: [1, 0.9, 1], opacity: [0.3, 0.2, 0.3] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut", delay }}
        className="w-40 h-4 bg-gray-300 rounded-[50%] blur-md mt-1 z-0"
      />
    </div>
  );
};

export const LandingPage: React.FC<LandingPageProps> = ({ onLogin }) => {
  return (
    <div className="min-h-screen bg-[#F6F7F6] relative overflow-hidden flex flex-col items-center">
      
      {/* Background Organic Shape */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
          <svg className="absolute top-[-10%] right-[-10%] w-[600px] h-[600px] text-gray-200/50" fill="currentColor" viewBox="0 0 200 200">
            <path d="M44.7,-76.4C58.9,-69.2,71.8,-59.1,81.6,-46.6C91.4,-34.1,98.1,-19.2,96.6,-4.8C95.1,9.6,85.4,23.5,74.5,36.1C63.6,48.6,51.5,59.8,38.1,66.5C24.7,73.2,10,75.4,-3.6,81.6C-17.2,87.8,-29.7,98,-42.6,96.5C-55.5,95,-68.8,81.8,-77.8,66.6C-86.8,51.4,-91.5,34.2,-91.2,17.3C-90.9,0.4,-85.6,-16.2,-76.6,-31.1C-67.6,-46,-54.9,-59.2,-41.6,-66.8C-28.3,-74.4,-14.1,-76.4,0.5,-77.3C15.1,-78.2,30.5,-83.6,44.7,-76.4Z" transform="translate(100 100)" />
          </svg>
      </div>

      {/* Butterfly Animations */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none" style={{ zIndex: 1 }}>
        <div className="shape-container butterfly-container" id="butterfly">
          <div className="shape cartoon hb">
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="body r ha hb"></div>
            <div className="antenna r ha hb"></div>
          </div>
        </div>
        <div className="shape-container butterfly-container" id="butterflyPink">
          <div className="shape cartoon hb">
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="body r ha hb"></div>
            <div className="antenna r ha hb"></div>
          </div>
        </div>
        <div className="shape-container butterfly-container" id="butterflySmall">
          <div className="shape cartoon hb">
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="wing-bottom ha hb"></div>
            <div className="wing-top ha hb">
              <div className="dots r"></div>
            </div>
            <div className="body r ha hb"></div>
            <div className="antenna r ha hb"></div>
          </div>
        </div>
      </div>

      <div className="relative z-10 w-full max-w-lg px-6 pt-12 md:pt-20 flex flex-col items-center">
        
        {/* Typography */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-8"
        >
            <h1 className="text-5xl md:text-6xl font-bold text-gray-900 tracking-tight font-display mb-2">Talk with Zeno</h1>
            <p className="mt-3 text-gray-600 text-lg font-medium font-display opacity-80">
              A voice-first, emotionally intelligent AI companion.
            </p>
        </motion.div>

        {/* Embedded Login Card */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.6 }}
          className="w-full z-20"
        >
          <LoginCard onLogin={onLogin} />
        </motion.div>

      </div>

      {/* Aesthetic Footer Composition */}
      <div className="absolute bottom-0 w-full h-auto pointer-events-none z-0">
          <motion.div 
             initial={{ opacity: 0 }}
             animate={{ opacity: 1 }}
             transition={{ duration: 1.5 }}
             className="relative w-full h-48 md:h-64"
          >
             {/* Left Side Group */}
             <ZenStonesGraphic scale={0.8} opacity={0.8} className="absolute bottom-4 left-6 md:left-24" delay={0} />
             <ZenStonesGraphic scale={0.5} opacity={0.4} className="absolute bottom-10 left-32 md:left-64" delay={1} />
             {/* Added extra stone to left side */}
             <ZenStonesGraphic scale={0.4} opacity={0.5} className="absolute bottom-14 left-2 md:left-10" delay={2} />
             
             {/* Right Side Group */}
             <ZenStonesGraphic scale={0.9} opacity={0.9} className="absolute -bottom-4 -right-4 md:right-16" delay={1.5} />
             <ZenStonesGraphic scale={0.65} opacity={0.6} className="absolute bottom-6 right-24 md:right-56" delay={0.5} />
          </motion.div>
      </div>

    </div>
  );
};