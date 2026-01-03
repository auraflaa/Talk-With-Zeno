"""
Production Logging Service
Provides structured logging with levels (DEBUG, INFO, WARN, ERROR)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


class LoggerService:
    """Centralized logging service with configurable levels"""
    
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize logger with configuration"""
        # Get log level from environment (default: INFO)
        log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        
        # Get environment (development/production)
        env = os.getenv('FLASK_ENV', 'development').lower()
        is_production = env == 'production'
        
        # Create logger
        self._logger = logging.getLogger('zeno_backend')
        self._logger.setLevel(log_level)
        
        # Prevent duplicate handlers
        if self._logger.handlers:
            return
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Console handler (always enabled)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(simple_formatter if is_production else detailed_formatter)
        self._logger.addHandler(console_handler)
        
        # File handler (rotating, for production)
        if is_production:
            log_dir = Path('logs')
            log_dir.mkdir(exist_ok=True)
            
            file_handler = RotatingFileHandler(
                log_dir / 'zeno_backend.log',
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(logging.DEBUG)  # Log everything to file
            file_handler.setFormatter(detailed_formatter)
            self._logger.addHandler(file_handler)
            
            # Error file handler (only errors)
            error_handler = RotatingFileHandler(
                log_dir / 'zeno_backend_errors.log',
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=3
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(detailed_formatter)
            self._logger.addHandler(error_handler)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message"""
        self._logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log info message"""
        self._logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message"""
        self._logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, exc_info=False, **kwargs):
        """Log error message with optional exception info"""
        self._logger.error(message, *args, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, *args, exc_info=False, **kwargs):
        """Log critical message"""
        self._logger.critical(message, *args, exc_info=exc_info, **kwargs)
    
    def get_logger(self):
        """Get the underlying logger instance"""
        return self._logger


# Singleton instance
_logger_service = None

def get_logger() -> LoggerService:
    """Get logger service instance"""
    global _logger_service
    if _logger_service is None:
        _logger_service = LoggerService()
    return _logger_service

