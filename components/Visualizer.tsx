import React from 'react';
import { motion } from 'framer-motion';

interface VisualizerProps {
    isActive: boolean;
    isTalking: boolean; // Is the AI talking?
}

export const Visualizer: React.FC<VisualizerProps> = ({ isActive, isTalking }) => {
  return (
    <div className="relative flex items-center justify-center w-full h-64 md:h-96">
      {/* Central Core */}
      <motion.div
        animate={{
          scale: isActive ? [1, 1.05, 1] : 1,
          opacity: isActive ? 1 : 0.8,
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "easeInOut"
        }}
        className={`w-32 h-32 rounded-full backdrop-blur-2xl flex items-center justify-center transition-colors duration-1000 ${
            isTalking 
            ? "bg-primary/30 shadow-[0_0_60px_rgba(94,234,212,0.4)] border border-primary/50" 
            : "bg-base-100/60 shadow-xl shadow-base-200 border border-base-content/5"
        }`}
      >
        <div className={`w-3 h-3 rounded-full transition-colors duration-500 ${isTalking ? "bg-primary" : "bg-neutral/30"}`} />
      </motion.div>

      {/* Ripples (Only active when listening/talking) */}
      {isActive && (
        <>
            {[1, 2, 3].map((i) => (
                 <motion.div
                 key={i}
                 className="absolute rounded-full border border-primary/20"
                 initial={{ width: "8rem", height: "8rem", opacity: 0.6 }}
                 animate={{ 
                     width: ["8rem", "22rem"], 
                     height: ["8rem", "22rem"],
                     opacity: [0.4, 0] 
                 }}
                 transition={{
                     duration: 4,
                     repeat: Infinity,
                     delay: i * 1.2,
                     ease: "easeOut"
                 }}
               />
            ))}
        </>
      )}
    </div>
  );
};