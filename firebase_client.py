"""
Firebase Firestore client for state management and real-time streaming.
Implements redundancy and error handling for production use.
"""
import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import firebase_admin
from firebase_admin import firestore, credentials, exceptions
from google.cloud.firestore_v1 import Client
from google.api_core.exceptions import GoogleAPIError

from config import CONFIG, logger

class FirebaseClient:
    """Manages Firebase Firestore connections with error recovery"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._initialized = False
        self._collections = {
            "pending_tx": "pending_transactions",
            "token_screen": "token_screen_results", 
            "trade_signals": "trade_signals",
            "execution_logs": "execution_logs",
            "performance": "performance_metrics",
            "risk_budgets": "risk_budgets"
        }
    
    def initialize(self) -> bool:
        """Initialize Firebase with error handling"""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(CONFIG.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred, {
                    'projectId': CONFIG.FIREBASE_PROJECT_ID
                })
            
            self.client = firestore.client()
            self._initialized = True
            logger.info("Firebase Firestore initialized successfully")
            return True
            
        except FileNotFoundError as e:
            logger.error(f"Firebase credentials file not found: {e}")
            return False
        except ValueError as e:
            logger.error(f"Invalid Firebase configuration: {e}")
            return False
        except GoogleAPIError as e:
            logger.error(f"Google API error during Firebase init: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error initializing Firebase: {e}")
            return False
    
    async def stream_mempool(self, callback) -> bool:
        """Real-time stream of pending transactions collection"""
        if not self._initialized or not self.client:
            logger.error("Firebase not initialized")
            return False
        
        try:
            # Create query for recent pending transactions
            query = self.client.collection(
                self._collections["pending_tx"]
            ).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50)
            
            # Watch the query
            query_watch = query.on_snapshot(callback)
            
            logger.info("Mempool streaming started")
            return True
            
        except exceptions.FirebaseError as e:
            logger.error(f"Firebase streaming error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected streaming error: {e}")
            return False
    
    async def save_token_candidate(self, token_data: Dict[str, Any]) -> str:
        """Save screened token candidate with validation"""
        if not self._initialized:
            logger.error("Cannot save: Firebase not initialized")
            return ""
        
        try:
            # Validate required fields
            required_fields = ["address", "chain", "timestamp", "liquidity_usd"]
            for field in required_fields:
                if field not in token_data:
                    logger.error(f"Missing required field: {field}")
                    return ""
            
            # Add metadata
            token_data["screened_at"] = firestore.SERVER_TIMESTAMP
            token_data["status"] = "pending_analysis"
            
            # Save to Firestore
            doc_ref = self.client.collection(
                self._collections["token_screen"]
            ).document()
            
            doc_ref.set(token_data)
            logger.info(f"Token candidate saved: {token_data['address'][:10]}...")
            return doc_ref.id
            
        except exceptions.FirebaseError as e:
            logger.error(f"Firebase save error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected save error: {e}")
            return ""
    
    async def log_trade_execution(self, trade_data: Dict[str, Any]) -> bool:
        """Log trade execution with comprehensive metadata"""
        if not self._initialized:
            return False
        
        try:
            # Validate trade data
            if "tx_hash" not in trade_data:
                logger.error("Trade log missing transaction hash")
                return False
            
            # Add logging metadata
            trade_data["logged_at"] = firestore.SERVER_TIMESTAMP
            trade_data["system_version"] = "1.0.0"
            
            # Calculate P&L if exit trade
            if trade_data.get("trade_type") == "exit" and "entry_price" in trade_data:
                exit_price = trade_data.get("execution_price", 0)
                entry_price = trade_data["entry_price"]
                if entry_price > 0:
                    trade_data["pnl_percent"] = ((exit_price - entry_price) / entry_price) * 100
            
            # Save to execution logs
            self.client.collection(
                self._collections["execution_logs"]
            ).document(trade_data["tx_hash"]).set(trade_data)
            
            # Update performance metrics
            await self._update_performance_metrics(trade_data)
            
            logger.info(f"Trade logged: {trade_data['tx_hash'][:10]}...")
            return True
            
        except exceptions.FirebaseError as e:
            logger.error(f"Firebase trade log error: {e}")
            return False
    
    async def _update_performance_metrics(self, trade_data: Dict[str, Any]) -> None:
        """Update real-time performance metrics"""
        try:
            metrics_ref = self.client.collection(
                self._collections["performance"]
            ).document("realtime")
            
            # Get current metrics
            current = metrics_ref.get()
            current_data = current.to_dict() if current.exists else {
                "total_trades": 0,
                "profitable_trades": 0,
                "total_pnl_eth": 0.0,
                "win_rate": 0.0
            }
            
            # Update metrics
            current_data["total_trades"] += 1
            
            if trade_data.get("pnl_percent", 0) > 0:
                current_data["profitable_trades"] += 1
            
            if "pnl_eth" in trade_data:
                current_data["total_pnl_eth"] += trade_data["pnl_eth"]
            
            # Calculate win rate
            if current_data["total_trades"] > 0:
                current_data["win_rate"] = (
                    current_data["profitable_trades"] / current_data["total_trades"]
                ) * 100
            
            # Update timestamp
            current_data["last_updated"] = firestore.SERVER_TIMESTAMP
            
            # Save back
            metrics_ref.set(current_data)
            
        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

# Global Firebase client instance
firebase_client = FirebaseClient()