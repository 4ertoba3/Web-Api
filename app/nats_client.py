import json
import logging
from datetime import datetime
from nats.aio.client import Client as NATS
from app.config import settings
from app.websocket import manager
from app.background import background_task

logger = logging.getLogger(__name__)

class NATSClient:
    def __init__(self):
        self.nc = NATS()
        self.is_connected = False
        self.subs = {}
        
    async def connect(self):
        try:
            await self.nc.connect(
                servers=[settings.nats_url],
                reconnect_time_wait=10,
                max_reconnect_attempts=-1,
                name="weather_api"
            )
            self.is_connected = True
            logger.info(f"NATS подключен: {settings.nats_url}")
            
            await self._subscribe_commands()
            await self._subscribe_weather_updates()
            
        except Exception as e:
            logger.error(f"Ошибка подключения NATS: {e}")
            
    async def disconnect(self):
        if not self.is_connected:
            return
            
        for sub in self.subs.values():
            try:
                await sub.unsubscribe()
            except Exception:
                pass
                
        await self.nc.close()
        self.is_connected = False
        logger.info("NATS отключен")
            
    async def publish(self, subject: str, message: dict):
        if not self.is_connected:
            return
            
        try:
            await self.nc.publish(subject, json.dumps(message).encode())
            logger.debug(f"Опубликовано в {subject}")
        except Exception as e:
            logger.error(f"Ошибка публикации: {e}")
    
    async def publish_weather_event(self, event_type: str, city: str = None, data: dict = None, weather_id: int = None):
        """Универсальный метод для публикации погодных событий"""
        message = {
            "type": f"weather_{event_type}",
            "timestamp": datetime.now().isoformat(),
            "source": "api" if event_type in ["created", "deleted"] else "background"
        }
        
        if city:
            message["city"] = city
        if data:
            message["data"] = data
        if weather_id:
            message["weather_id"] = weather_id
            
        await self.publish(settings.nats_subject_weather, message)
    
    async def publish_system_event(self, event_type: str, data: dict = None):
        message = {
            "type": "system",
            "event": event_type,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        }
        await self.publish(settings.nats_subject_commands, message)
                
    async def _subscribe_commands(self):
        async def handler(msg):
            try:
                data = json.loads(msg.data.decode())
                cmd = data.get("command")
                logger.info(f"[NATS] Команда: {cmd}")
                
                if cmd == "run_background_task":
                    await background_task.run_once()
                    await self.publish_system_event("task_executed", {"status": "success"})
                    
                elif cmd == "get_status":
                    await self.publish_system_event("status_response", {
                        "is_running": background_task.is_running,
                        "task_id": background_task.task_id,
                        "cities": settings.cities
                    })
                    
                elif cmd == "update_cities":
                    new_cities = data.get("cities")
                    if isinstance(new_cities, list):
                        settings.cities = new_cities
                        await self.publish_system_event("cities_updated", {"cities": new_cities})
                        
            except Exception as e:
                logger.error(f"Ошибка обработки команды: {e}")
                
        self.subs["commands"] = await self.nc.subscribe(
            settings.nats_subject_commands,
            cb=handler
        )
        logger.info(f"Подписка на команды: {settings.nats_subject_commands}")
    
    async def _subscribe_weather_updates(self):
        async def handler(msg):
            try:
                data = json.loads(msg.data.decode())
                msg_type = data.get("type", "unknown")
                city = data.get("city", "unknown")
                logger.info(f"[NATS] {msg_type}")
                await manager.broadcast(data)
            except Exception as e:
                logger.error(f"Ошибка обработки обновления: {e}")
                
        self.subs["weather"] = await self.nc.subscribe(
            settings.nats_subject_weather,
            cb=handler
        )
        logger.info(f"Подписка на обновления: {settings.nats_subject_weather}")

nats_client = NATSClient()