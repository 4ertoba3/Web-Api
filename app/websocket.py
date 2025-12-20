import json
import logging
from typing import List
from fastapi import WebSocket
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        """Подключение клиента"""
        self.active_connections.append(websocket)
        logger.info(f"WebSocket подключен. Всего: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """Отключение клиента"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket отключен. Всего: {len(self.active_connections)}")
            
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Отправка сообщения конкретному клиенту"""
        await websocket.send_text(message)
        
    async def broadcast(self, message: dict):
        """Отправка сообщения всем подключенным клиентам"""
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
                
        for connection in disconnected:
            self.disconnect(connection)
            
    async def broadcast_weather_update(self, city: str, data: dict):
        """Типизированное сообщение об обновлении погоды"""
        message = {
            "type": "weather_update",
            "city": city,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message)
        
    async def broadcast_system_message(self, message: str):
        """Системное сообщение"""
        msg = {
            "type": "system",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(msg)

manager = ConnectionManager()