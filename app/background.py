import asyncio
import httpx
import logging
from datetime import datetime
from typing import Optional
import random
import uuid

from app.config import settings
from app.database import get_db
from app import crud, schemas

logger = logging.getLogger(__name__)

class BackgroundTask:
    def __init__(self):
        self.is_running = False
        self.task = None
        self.http_client = None
        self.nats_client = None
        self.task_id = uuid.uuid4().hex[:8]
        
    async def start(self, nats_client=None):
        if self.is_running:
            return
            
        self.is_running = True
        self.nats_client = nats_client
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.task = asyncio.create_task(self._run_periodically())
        logger.info(f"✅ Задача {self.task_id} запущена")
        
    async def stop(self):
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
                
        if self.http_client:
            await self.http_client.aclose()
            
        logger.info(f"✅ Задача {self.task_id} остановлена")
        
    async def _run_periodically(self):
        while self.is_running:
            try:
                await self.fetch_weather_data()
                await asyncio.sleep(settings.background_interval_seconds)
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                await asyncio.sleep(60)
                
    async def fetch_weather_data(self):
        """Получение данных о погоде"""
        updated = []
        
        for city in settings.cities:
            try:
                weather_data = await self._get_weather_for_city(city)
                
                if weather_data:
                    async for db in get_db():
                        db_weather = await crud.create_weather_data(db, schemas.WeatherCreate(**weather_data))
                        updated.append(city)
                        
                        if self.nats_client and self.nats_client.is_connected:
                            try:
                                await self.nats_client.publish_weather_event("updated", city, weather_data)
                            except Exception as e:
                                logger.debug(f"Ошибка NATS: {e}")
            except Exception as e:
                logger.debug(f"Ошибка {city}: {e}")
        
        if updated:
            logger.info(f"🌤️  Обновлено: {', '.join(updated)}")

    
    async def _get_weather_for_city(self, city: str) -> Optional[dict]:
        """Получение данных о погоде с приоритетом источников"""
        if weather := await self._fetch_openweather_data(city):
            return weather
        if weather := await self._parse_gismeteo_data(city):
            return weather
        return await self._emulate_weather_data(city)
    
    async def _fetch_openweather_data(self, city: str) -> Optional[dict]:
        """Получение данных из OpenWeatherMap"""
        api_key = settings.openweather_api_key
        if not api_key:
            return None
            
        try:
            async with httpx.AsyncClient() as client:
                geo_url = "http://api.openweathermap.org/geo/1.0/direct"
                geo_resp = await client.get(geo_url, params={"q": city, "limit": 1, "appid": api_key})
                
                if geo_resp.status_code != 200 or not geo_resp.json():
                    return None
                
                geo_data = geo_resp.json()[0]
                
                weather_url = "https://api.openweathermap.org/data/2.5/weather"
                weather_resp = await client.get(weather_url, params={
                    "lat": geo_data["lat"],
                    "lon": geo_data["lon"],
                    "appid": api_key,
                    "units": "metric",
                    "lang": "ru"
                })
                
                if weather_resp.status_code != 200:
                    return None
                
                data = weather_resp.json()
                
                return {
                    "city": city,
                    "temperature": data["main"]["temp"],
                    "feels_like": data["main"]["feels_like"],
                    "humidity": data["main"]["humidity"],
                    "pressure": data["main"]["pressure"],
                    "wind_speed": data["wind"]["speed"],
                    "wind_direction": self._degrees_to_direction(data["wind"].get("deg", 0)),
                    "condition": data["weather"][0]["description"],
                    "description": f"🌤️ {data['weather'][0]['description']}",
                    "raw_data": {
                        "source": "openweathermap",
                        "data": data,
                        "parsed_at": datetime.now().isoformat()
                    }
                }
        except Exception as e:
            logger.debug(f"OpenWeatherMap ошибка для {city}: {e}")
            return None
    
    async def _parse_gismeteo_data(self, city: str) -> Optional[dict]:
        """Заглушка для парсинга Gismeteo"""
        return None
    
    async def _emulate_weather_data(self, city: str) -> dict:
        """Эмуляция данных о погоде"""
        base_temps = {"Москва": 15.0, "Санкт-Петербург": 12.0, "Новосибирск": 10.0, "Екатеринбург": 11.0}
        conditions = [
            {"name": "ясно", "emoji": "☀️"},
            {"name": "пасмурно", "emoji": "☁️"},
            {"name": "небольшой дождь", "emoji": "🌦️"},
            {"name": "снег", "emoji": "❄️"},
            {"name": "туман", "emoji": "🌫️"},
            {"name": "переменная облачность", "emoji": "⛅"}
        ]
        
        base_temp = base_temps.get(city, 15.0)
        temp_var = random.uniform(-3, 3)
        condition = random.choice(conditions)
        
        return {
            "city": city,
            "temperature": round(base_temp + temp_var, 1),
            "feels_like": round(base_temp + temp_var - random.uniform(0, 2), 1),
            "humidity": random.randint(40, 95),
            "pressure": round(random.uniform(980, 1030), 1),
            "wind_speed": round(random.uniform(0, 15), 1),
            "wind_direction": random.choice(["север", "юг", "запад", "восток"]),
            "condition": condition["name"],
            "description": f"{condition['emoji']} {condition['name']}",
            "raw_data": {
                "source": "emulation", 
                "parsed_at": datetime.now().isoformat(),
                "note": "Реальные API недоступны"
            }
        }
    
    def _degrees_to_direction(self, degrees: float) -> str:
        """Преобразование градусов в направление ветра"""
        directions = ["север", "северо-восток", "восток", "юго-восток", 
                      "юг", "юго-запад", "запад", "северо-запад"]
        return directions[round(degrees / 45) % 8]
        
    async def run_once(self):
        await self.fetch_weather_data()

background_task = BackgroundTask()