"""
Real-time mempool monitoring for Base L2.
Detects contract creations and liquidity additions before they hit blocks.
"""
import asyncio
import json
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import aiohttp
from web3 import Web3
from web3.exceptions import TransactionNotFound

from config import CONFIG, logger
from firebase_client import firebase_client

class MempoolStreamer:
    """WebSocket-based mempool monitoring with multi-RPC redundancy"""
    
    def __init__(self):
        self.w3_connections: Dict[str, Web3] = {}
        self.active_streams: Dict[str, asyncio.Task] = {}
        self._shutdown = False
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self) -> bool:
        """Initialize Web3 connections to multiple RPC endpoints"""
        try:
            # Create Web3 instances for each RPC URL
            for i, rpc_url in enumerate(CONFIG.BASE_RPC_URLS):
                try:
                    # Skip empty URLs
                    if not rpc_url or "your_api_key" in rpc_url:
                        continue
                        
                    # Initialize Web3 with timeout
                    w3 = Web3(Web3.HTTPProvider(
                        rpc_url,
                        request_kwargs={'timeout': 30}
                    ))
                    
                    # Test connection
                    if w3.is_connected():
                        self.w3_connections[f"provider_{i}"] = w3
                        logger.info(f"Connected to RPC {i}: {rpc_url[:50]}...")
                    else:
                        logger.warning(f"Failed to connect to RPC {i}")
                        
                except Exception as e:
                    logger.error(f"Error connecting to RPC {i}: {e}")
            
            if not self.w3_connections:
                logger.error("No valid RPC connections established")
                return False
                
            # Initialize aiohttp session
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing mempool streamer: {e}")
            return False
    
    async def start_streaming(self, 
                            tx_callback: Callable[[Dict[str, Any]], None],
                            block_callback: Optional[Callable[[int], None]] = None) -> bool:
        """Start streaming mempool transactions"""
        if not self.w3_connections:
            logger.error("Cannot stream: No RPC connections")
            return False
        
        try:
            # Start streaming from primary provider
            primary_provider = next(iter(self.w3_connections.keys()))
            w3 = self.w3_connections[primary_provider]
            
            # Start mempool monitoring task
            self.active_streams["mempool"] = asyncio.create_task(
                self._stream_pending_transactions(w3, tx_callback)
            )
            
            # Start block monitoring if callback provided
            if block_callback:
                self.active_streams["blocks"] = asyncio.create_task(
                    self._monitor_new_blocks(w3, block_callback)
                )
            
            logger.info("Mempool streaming started")
            return True
            
        except Exception as e:
            logger.error(f"Error starting mempool stream: {e}")
            return False
    
    async def _stream_pending_transactions(self, 
                                         w3: Web3, 
                                         callback: Callable[[Dict[str, Any]], None]) -> None:
        """Monitor pending transactions via WebSocket subscription"""
        while not self._shutdown:
            try:
                # Create filter for pending transactions
                pending_filter = w3.eth.filter('pending')
                
                # Check for new pending transactions
                pending_txs = pending_filter.get_new_entries()
                
                for tx_hash in pending_txs:
                    try:
                        # Get transaction details
                        tx = w3.eth.get_transaction(tx_hash)
                        
                        # Check if it's a contract creation
                        if not tx.get('to'):  # 'to' is None for contract creation
                            tx_data = {
                                'hash': tx_hash.hex(),
                                'from': tx['from'],
                                'value': str(tx['value']),
                                'gas': tx['gas'],
                                'gas_price': str(tx['gasPrice']),
                                'input': tx['