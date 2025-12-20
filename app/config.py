import os
import json
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API settings
    app_title: str = "Weather Monitoring API"
    app_version: str = "1.0.0"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./weather.db"
    
    # NATS
    nats_url: str = os.getenv("NATS_URL", "nats://localhost:4222")
    nats_subject_weather: str = "weather.updates"
    nats_subject_commands: str = "weather.commands"
    
    # Background task
    background_interval_seconds: int = 300
    cities: list[str] = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург"]
    
    gismeteo_base_url: str = "https://www.gismeteo.ru"
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    
    @classmethod
    def parse_cities(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [city.strip() for city in v.split(",") if city.strip()]
        return v
    
    class Config:
        env_file = ".env"
        json_encoders = {
            list: lambda v: json.dumps(v)
        }

settings = Settings()