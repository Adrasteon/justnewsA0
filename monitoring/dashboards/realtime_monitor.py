"""
Real-Time Monitor for JustNews Dashboard System

This module provides real-time data streaming and live visualization updates
for the JustNews monitoring dashboard. It handles WebSocket connections,
live data aggregation, and real-time metric streaming.

Author: JustNews Development Team
Date: October 22, 2025
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import websockets
from pydantic import BaseModel, Field
from websockets.exceptions import ConnectionClosedError, WebSocketException

# Configure logging
logger = logging.getLogger(__name__)


class StreamConfig(BaseModel):
    """Configuration for real-time data streams"""

    name: str = Field(..., description="Stream name")
    topics: list[str] = Field(
        default_factory=list, description="Kafka/PubSub topics to monitor"
    )
    metrics: list[str] = Field(
        default_factory=list, description="Prometheus metrics to stream"
    )
    update_interval: float = Field(1.0, description="Update interval in seconds")
    buffer_size: int = Field(
        1000, description="Maximum buffer size for historical data"
    )
    retention_period: int = Field(3600, description="Data retention period in seconds")


class ClientConnection(BaseModel):
    """WebSocket client connection information"""

    client_id: str = Field(..., description="Unique client identifier")
    websocket: Any = Field(..., description="WebSocket connection object")
    subscribed_streams: set[str] = Field(
        default_factory=set, description="Subscribed stream names"
    )
    connected_at: datetime = Field(
        default_factory=datetime.now, description="Connection timestamp"
    )
    last_activity: datetime = Field(
        default_factory=datetime.now, description="Last activity timestamp"
    )


class StreamData(BaseModel):
    """Real-time stream data structure"""

    stream_name: str = Field(..., description="Name of the data stream")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Data timestamp"
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Stream data payload"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


@dataclass
class RealTimeMonitor:
    """
    Real-time monitor for live data streaming and visualization updates.

    This class manages WebSocket connections, handles real-time data streams,
    and provides live updates to dashboard clients. It supports multiple
    streaming protocols and data sources.
    """

    # WebSocket server configuration
    host: str = field(default="0.0.0.0")
    port: int = field(default=8765)
    max_connections: int = field(default=1000)

    # Stream configurations
    streams: dict[str, StreamConfig] = field(default_factory=dict)

    # Active client connections
    clients: dict[str, ClientConnection] = field(default_factory=dict)

    # Data buffers for each stream
    data_buffers: dict[str, list[StreamData]] = field(default_factory=dict)

    # Stream update tasks
    update_tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    # Event handlers
    event_handlers: dict[str, list[Callable]] = field(default_factory=dict)

    # Server instance
    server: Any | None = field(default=None, init=False)

    # Monitoring stats
    stats: dict[str, Any] = field(
        default_factory=lambda: {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "errors": 0,
            "uptime": 0,
        }
    )

    def __post_init__(self):
        """Initialize real-time monitor"""
        self._setup_default_streams()
        self.start_time = datetime.now()

    def _setup_default_streams(self):
        """Setup default real-time streams"""
        self.streams.update(
            {
                "system_metrics": StreamConfig(
                    name="system_metrics",
                    metrics=[
                        "cpu_usage_percent",
                        "memory_usage_percent",
                        "disk_usage_percent",
                        "network_io_bytes",
                    ],
                    update_interval=5.0,
                    buffer_size=500,
                ),
                "agent_performance": StreamConfig(
                    name="agent_performance",
                    metrics=[
                        "agent_response_time",
                        "agent_throughput",
                        "agent_error_rate",
                        "agent_queue_length",
                    ],
                    update_interval=2.0,
                    buffer_size=1000,
                ),
                "content_processing": StreamConfig(
                    name="content_processing",
                    metrics=[
                        "articles_processed",
                        "content_quality_score",
                        "fact_check_results",
                        "processing_latency",
                    ],
                    update_interval=10.0,
                    buffer_size=200,
                ),
                "security_events": StreamConfig(
                    name="security_events",
                    topics=["security.alerts", "auth.events"],
                    update_interval=1.0,
                    buffer_size=1000,
                ),
                "business_metrics": StreamConfig(
                    name="business_metrics",
                    metrics=[
                        "active_users",
                        "revenue_total",
                        "engagement_score",
                        "conversion_rate",
                    ],
                    update_interval=30.0,
                    buffer_size=100,
                ),
            }
        )

        # Initialize data buffers
        for stream_name in self.streams.keys():
            self.data_buffers[stream_name] = []

    async def start_server(self):
        """Start the WebSocket server"""
        try:
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                max_size=2**20,  # 1MB max message size
                max_queue=1000,
                ping_interval=30,
                ping_timeout=10,
            )

            logger.info(f"Real-time monitor server started on {self.host}:{self.port}")

            # Start stream update tasks
            await self._start_stream_updates()

            # Start cleanup task
            asyncio.create_task(self._cleanup_inactive_clients())

            return self.server

        except Exception as e:
            logger.error(f"Failed to start real-time monitor server: {e}")
            raise

    async def stop_server(self):
        """Stop the WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Real-time monitor server stopped")

        # Cancel all update tasks
        for task in self.update_tasks.values():
            task.cancel()

        # Clear all tasks
        self.update_tasks.clear()

    async def _handle_client(self, websocket, path: str):
        """Handle individual WebSocket client connections"""
        client_id = str(uuid.uuid4())
        client = ClientConnection(client_id=client_id, websocket=websocket)

        self.clients[client_id] = client
        self.stats["total_connections"] += 1
        self.stats["active_connections"] += 1

        logger.info(f"Client {client_id} connected from {websocket.remote_address}")

        try:
            # Send welcome message
            await self._send_to_client(
                client_id,
                {
                    "type": "welcome",
                    "client_id": client_id,
                    "available_streams": list(self.streams.keys()),
                    "timestamp": datetime.now().isoformat(),
                },
            )

            # Handle client messages
            async for message in websocket:
                try:
                    await self._handle_client_message(client_id, message)
                except Exception as e:
                    logger.error(f"Error handling message from client {client_id}: {e}")
                    self.stats["errors"] += 1

        except ConnectionClosedError:
            logger.info(f"Client {client_id} disconnected normally")
        except WebSocketException as e:
            logger.warning(f"WebSocket error for client {client_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error for client {client_id}: {e}")
        finally:
            # Clean up client
            if client_id in self.clients:
                del self.clients[client_id]
            self.stats["active_connections"] -= 1
            logger.info(f"Client {client_id} cleanup completed")

    async def _handle_client_message(self, client_id: str, message: str):
        """Handle incoming client message"""
        try:
            data = json.loads(message)
            message_type = data.get("type", "unknown")

            self.stats["messages_received"] += 1

            if message_type == "subscribe":
                await self._handle_subscribe(client_id, data)
            elif message_type == "unsubscribe":
                await self._handle_unsubscribe(client_id, data)
            elif message_type == "ping":
                await self._handle_ping(client_id)
            elif message_type == "get_history":
                await self._handle_get_history(client_id, data)
            else:
                logger.warning(
                    f"Unknown message type '{message_type}' from client {client_id}"
                )

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message from client {client_id}")
        except Exception as e:
            logger.error(f"Error processing message from client {client_id}: {e}")

    async def _handle_subscribe(self, client_id: str, data: dict[str, Any]):
        """Handle stream subscription request"""
        stream_names = data.get("streams", [])
        if not isinstance(stream_names, list):
            stream_names = [stream_names]

        client = self.clients.get(client_id)
        if not client:
            return

        subscribed = []
        for stream_name in stream_names:
            if stream_name in self.streams:
                client.subscribed_streams.add(stream_name)
                subscribed.append(stream_name)
                logger.info(f"Client {client_id} subscribed to stream '{stream_name}'")
            else:
                logger.warning(
                    f"Client {client_id} requested unknown stream '{stream_name}'"
                )

        await self._send_to_client(
            client_id,
            {
                "type": "subscribed",
                "streams": subscribed,
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def _handle_unsubscribe(self, client_id: str, data: dict[str, Any]):
        """Handle stream unsubscription request"""
        stream_names = data.get("streams", [])
        if not isinstance(stream_names, list):
            stream_names = [stream_names]

        client = self.clients.get(client_id)
        if not client:
            return

        unsubscribed = []
        for stream_name in stream_names:
            if stream_name in client.subscribed_streams:
                client.subscribed_streams.remove(stream_name)
                unsubscribed.append(stream_name)
                logger.info(
                    f"Client {client_id} unsubscribed from stream '{stream_name}'"
                )

        await self._send_to_client(
            client_id,
            {
                "type": "unsubscribed",
                "streams": unsubscribed,
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def _handle_ping(self, client_id: str):
        """Handle ping message"""
        await self._send_to_client(
            client_id, {"type": "pong", "timestamp": datetime.now().isoformat()}
        )

    async def _handle_get_history(self, client_id: str, data: dict[str, Any]):
        """Handle historical data request"""
        stream_name = data.get("stream")
        limit = min(data.get("limit", 100), 1000)  # Max 1000 records

        if stream_name not in self.data_buffers:
            await self._send_to_client(
                client_id,
                {
                    "type": "error",
                    "message": f"Unknown stream '{stream_name}'",
                    "timestamp": datetime.now().isoformat(),
                },
            )
            return

        buffer = self.data_buffers[stream_name]
        history_data = buffer[-limit:] if len(buffer) > limit else buffer

        await self._send_to_client(
            client_id,
            {
                "type": "history",
                "stream": stream_name,
                "data": [item.model_dump() for item in history_data],
                "timestamp": datetime.now().isoformat(),
            },
        )

    async def _send_to_client(self, client_id: str, data: dict[str, Any]):
        """Send message to specific client"""
        client = self.clients.get(client_id)
        if not client:
            return

        try:
            message = json.dumps(data, default=str)
            await client.websocket.send(message)
            self.stats["messages_sent"] += 1
            client.last_activity = datetime.now()
        except Exception as e:
            logger.error(f"Failed to send message to client {client_id}: {e}")
            # Client might be disconnected, will be cleaned up later

    async def broadcast_to_stream(self, stream_name: str, data: dict[str, Any]):
        """Broadcast data to all clients subscribed to a stream"""
        if stream_name not in self.streams:
            logger.warning(f"Attempted to broadcast to unknown stream '{stream_name}'")
            return

        # Add stream metadata
        message_data = {
            "type": "stream_data",
            "stream": stream_name,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }

        # Send to all subscribed clients
        sent_count = 0
        for client in self.clients.values():
            if stream_name in client.subscribed_streams:
                await self._send_to_client(client.client_id, message_data)
                sent_count += 1

        logger.debug(f"Broadcasted {stream_name} data to {sent_count} clients")

    async def _start_stream_updates(self):
        """Start background tasks for stream data updates"""
        for stream_name, config in self.streams.items():
            task = asyncio.create_task(
                self._stream_update_loop(stream_name, config),
                name=f"stream_update_{stream_name}",
            )
            self.update_tasks[stream_name] = task
            logger.info(f"Started update task for stream '{stream_name}'")

    async def _stream_update_loop(self, stream_name: str, config: StreamConfig):
        """Background loop for updating stream data"""
        while True:
            try:
                # Collect data for this stream
                data = await self._collect_stream_data(stream_name, config)

                if data:
                    # Create stream data object
                    stream_data = StreamData(
                        stream_name=stream_name,
                        data=data,
                        metadata={"source": "realtime_monitor"},
                    )

                    # Add to buffer
                    buffer = self.data_buffers[stream_name]
                    buffer.append(stream_data)

                    # Maintain buffer size
                    if len(buffer) > config.buffer_size:
                        buffer.pop(0)

                    # Broadcast to subscribers
                    await self.broadcast_to_stream(stream_name, data)

                    # Trigger event handlers
                    await self._trigger_event_handlers(stream_name, stream_data)

                # Wait for next update
                await asyncio.sleep(config.update_interval)

            except asyncio.CancelledError:
                logger.info(f"Stream update loop for '{stream_name}' cancelled")
                break
            except Exception as e:
                logger.error(f"Error in stream update loop for '{stream_name}': {e}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def _collect_stream_data(
        self, stream_name: str, config: StreamConfig
    ) -> dict[str, Any] | None:
        """Collect data for a specific stream"""
        try:
            if stream_name == "system_metrics":
                return await self._collect_system_metrics()
            elif stream_name == "agent_performance":
                return await self._collect_agent_performance()
            elif stream_name == "content_processing":
                return await self._collect_content_processing()
            elif stream_name == "security_events":
                return await self._collect_security_events()
            elif stream_name == "business_metrics":
                return await self._collect_business_metrics()
            else:
                # Custom stream - try to collect from registered handlers
                return await self._collect_custom_stream_data(stream_name)

        except Exception as e:
            logger.error(f"Error collecting data for stream '{stream_name}': {e}")
            return None

    async def _collect_system_metrics(self) -> dict[str, Any]:
        """Collect system-level metrics"""
        # This would integrate with Prometheus or direct system monitoring
        # For now, return mock data
        return {
            "cpu_usage_percent": 45.2,
            "memory_usage_percent": 67.8,
            "disk_usage_percent": 23.4,
            "network_io_bytes": 1250000,
            "timestamp": datetime.now().isoformat(),
        }

    async def _collect_agent_performance(self) -> dict[str, Any]:
        """Collect agent performance metrics"""
        # This would query agent metrics from Prometheus/monitoring system
        return {
            "agent_response_time": 0.234,
            "agent_throughput": 125.5,
            "agent_error_rate": 0.02,
            "agent_queue_length": 3,
            "timestamp": datetime.now().isoformat(),
        }

    async def _collect_content_processing(self) -> dict[str, Any]:
        """Collect content processing metrics"""
        return {
            "articles_processed": 1250,
            "content_quality_score": 8.7,
            "fact_check_results": {"passed": 1180, "failed": 70},
            "processing_latency": 2.1,
            "timestamp": datetime.now().isoformat(),
        }

    async def _collect_security_events(self) -> dict[str, Any]:
        """Collect security event data"""
        return {
            "alerts": 2,
            "auth_failures": 0,
            "suspicious_activity": 1,
            "timestamp": datetime.now().isoformat(),
        }

    async def _collect_business_metrics(self) -> dict[str, Any]:
        """Collect business metrics"""
        return {
            "active_users": 15420,
            "revenue_total": 45230.50,
            "engagement_score": 7.8,
            "conversion_rate": 0.034,
            "timestamp": datetime.now().isoformat(),
        }

    async def _collect_custom_stream_data(
        self, stream_name: str
    ) -> dict[str, Any] | None:
        """Collect data for custom streams"""
        # This would be implemented by custom stream handlers
        return None

    async def _trigger_event_handlers(self, stream_name: str, data: StreamData):
        """Trigger event handlers for stream data"""
        handlers = self.event_handlers.get(stream_name, [])
        for handler in handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"Error in event handler for stream '{stream_name}': {e}")

    async def _cleanup_inactive_clients(self):
        """Clean up inactive client connections"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                current_time = datetime.now()
                inactive_clients = []

                for client_id, client in self.clients.items():
                    # Consider client inactive if no activity for 5 minutes
                    if (current_time - client.last_activity).total_seconds() > 300:
                        inactive_clients.append(client_id)

                for client_id in inactive_clients:
                    logger.info(f"Removing inactive client {client_id}")
                    del self.clients[client_id]
                    self.stats["active_connections"] -= 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in client cleanup: {e}")

    def add_event_handler(self, stream_name: str, handler: Callable):
        """Add event handler for a stream"""
        if stream_name not in self.event_handlers:
            self.event_handlers[stream_name] = []
        self.event_handlers[stream_name].append(handler)
        logger.info(f"Added event handler for stream '{stream_name}'")

    def remove_event_handler(self, stream_name: str, handler: Callable):
        """Remove event handler for a stream"""
        if stream_name in self.event_handlers:
            try:
                self.event_handlers[stream_name].remove(handler)
                logger.info(f"Removed event handler for stream '{stream_name}'")
            except ValueError:
                logger.warning(f"Handler not found for stream '{stream_name}'")

    def add_custom_stream(self, config: StreamConfig):
        """Add a custom stream configuration"""
        self.streams[config.name] = config
        self.data_buffers[config.name] = []

        # Start update task for new stream
        task = asyncio.create_task(
            self._stream_update_loop(config.name, config),
            name=f"stream_update_{config.name}",
        )
        self.update_tasks[config.name] = task

        logger.info(f"Added custom stream '{config.name}'")

    def get_stream_data(
        self, stream_name: str, limit: int | None = None
    ) -> list[StreamData]:
        """Get historical data for a stream"""
        if stream_name not in self.data_buffers:
            return []

        buffer = self.data_buffers[stream_name]
        if limit is None:
            return buffer.copy()
        return buffer[-limit:] if len(buffer) > limit else buffer.copy()

    def get_stats(self) -> dict[str, Any]:
        """Get real-time monitor statistics"""
        current_time = datetime.now()
        self.stats["uptime"] = (current_time - self.start_time).total_seconds()

        return {
            **self.stats,
            "active_streams": len(self.streams),
            "total_clients": len(self.clients),
            "stream_buffers": {
                name: len(buffer) for name, buffer in self.data_buffers.items()
            },
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check"""
        return {
            "status": "healthy"
            if self.server and not self.server.is_serving()
            else "unhealthy",
            "active_connections": len(self.clients),
            "active_streams": len(
                [t for t in self.update_tasks.values() if not t.done()]
            ),
            "total_messages_sent": self.stats["messages_sent"],
            "total_messages_received": self.stats["messages_received"],
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
        }
