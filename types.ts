export enum AppMode {
  LOGIN = 'LOGIN',
  AUTHENTICATED = 'AUTHENTICATED'
}

export enum SessionMode {
  NONE = 'NONE',
  VOICE = 'VOICE',
  TEXT = 'TEXT'
}

export enum InteractionMode {
  VOICE = 'VOICE',
  TEXT = 'TEXT'
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatarColor: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

export interface ChatSession {
  id: string;
  title: string;
  date: Date;
  messages: Message[];
}

export interface UserState {
  isAuthenticated: boolean;
  email?: string;
  name?: string;
}

// Mock Types for the Live Service Abstraction
export enum LiveConnectionState {
  DISCONNECTED = 'DISCONNECTED',
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  ERROR = 'ERROR'
}