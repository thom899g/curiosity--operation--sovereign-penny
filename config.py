"""
Configuration management for Operation Sovereign Penny.
Centralizes all environment variables, constants, and settings.
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

@dataclass
class TradingConfig:
    """Global trading configuration"""
    # Network Configuration
    BASE_RPC_URLS: List[str] = field(default_factory=lambda: [
        "https://mainnet.base.org",
        "https://base-mainnet.g.alchemy.com/v2/",
        "https://base.llamarpc.com"
    ])
    
    # Trading Parameters
    MIN_PROFIT_TARGET: float = 0.03  # 3%
    MAX_PROFIT_TARGET: float = 0.08  # 8%
    MAX_POSITION_SIZE_ETH: float = 0.01  # 0.01 ETH per trade
    MIN_LIQUIDITY_USD: float = 5000  # $5k minimum liquidity
    MAX_SLIPPAGE_BPS: int = 200  # 2%
    
    # Risk Management
    DAILY_LOSS_LIMIT_ETH: float = 0.05  # 0.05 ETH
    MAX_CONCURRENT_TRADES: int = 5
    COOLDOWN_SECONDS: int = 30  # Between trades
    
    # ML Model Parameters
    MIN_CONFIDENCE_SCORE: float = 0.7
    ANOMALY_THRESHOLD: float = -0.5  # Isolation Forest
    
    # Firebase Configuration
    FIREBASE_PROJECT_ID: Optional[str] = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_CREDENTIALS_PATH: Optional[str] = os.getenv("FIREBASE_CREDENTIALS_PATH")
    
    # API Keys (validate presence)
    def validate(self) -> bool:
        """Validate critical configuration"""
        missing = []
        
        if not self.FIREBASE_PROJECT_ID:
            missing.append("FIREBASE_PROJECT_ID")
        if not self.FIREBASE_CREDENTIALS_PATH or not os.path.exists(self.FIREBASE_CREDENTIALS_PATH):
            missing.append("FIREBASE_CREDENTIALS_PATH (or file doesn't exist)")
            
        if missing:
            logging.error(f"Missing required configs: {missing}")
            return False
        return True

# Global config instance
CONFIG = TradingConfig()

def setup_logging() -> logging.Logger:
    """Configure structured logging"""
    logger = logging.getLogger("sovereign_penny")
    logger.setLevel(logging.INFO)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Formatter with timestamp and component
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger

# Initialize logger
logger = setup_logging()