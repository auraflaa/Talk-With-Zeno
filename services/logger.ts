/**
 * Production Logging Service
 * Provides structured logging with levels (debug, info, warn, error)
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4,
}

class Logger {
  private level: LogLevel;
  private isProduction: boolean;

  constructor() {
    // Get log level from environment (default: INFO in production, DEBUG in development)
    const envLevel = ((import.meta.env.VITE_LOG_LEVEL as string) || '').toUpperCase();
    this.level = this.parseLogLevel(envLevel);
    
    // Check if we're in production
    this.isProduction = import.meta.env.MODE === 'production';
    
    // In production, default to INFO if not specified
    if (this.isProduction && !envLevel) {
      this.level = LogLevel.INFO;
    }
  }

  private parseLogLevel(level: string): LogLevel {
    switch (level) {
      case 'DEBUG':
        return LogLevel.DEBUG;
      case 'INFO':
        return LogLevel.INFO;
      case 'WARN':
        return LogLevel.WARN;
      case 'ERROR':
        return LogLevel.ERROR;
      case 'NONE':
        return LogLevel.NONE;
      default:
        return this.isProduction ? LogLevel.INFO : LogLevel.DEBUG;
    }
  }

  private shouldLog(level: LogLevel): boolean {
    return level >= this.level;
  }

  private formatMessage(level: string, message: string, ...args: any[]): string {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level}]`;
    
    if (args.length === 0) {
      return `${prefix} ${message}`;
    }
    
    // Format with arguments
    try {
      return `${prefix} ${message} ${args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
      ).join(' ')}`;
    } catch (e) {
      return `${prefix} ${message} [Error formatting arguments]`;
    }
  }

  debug(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      if (this.isProduction) {
        // In production, only log to console if explicitly enabled
        console.debug(this.formatMessage('DEBUG', message, ...args));
      } else {
        console.debug(this.formatMessage('DEBUG', message, ...args));
      }
    }
  }

  info(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.INFO)) {
      console.info(this.formatMessage('INFO', message, ...args));
    }
  }

  warn(message: string, ...args: any[]): void {
    if (this.shouldLog(LogLevel.WARN)) {
      console.warn(this.formatMessage('WARN', message, ...args));
    }
  }

  error(message: string, error?: Error | unknown, ...args: any[]): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      const errorDetails = error instanceof Error 
        ? `\nError: ${error.message}\nStack: ${error.stack}`
        : error 
          ? `\nError: ${JSON.stringify(error)}`
          : '';
      
      console.error(this.formatMessage('ERROR', message, ...args) + errorDetails);
    }
  }

  setLevel(level: LogLevel): void {
    this.level = level;
  }

  getLevel(): LogLevel {
    return this.level;
  }
}

// Singleton instance
export const logger = new Logger();

