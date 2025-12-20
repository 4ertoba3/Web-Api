from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class WeatherBase(BaseModel):
    city: str = Field(..., example="Москва")
    temperature: float = Field(..., example=20.5)
    feels_like: Optional[float] = Field(None, example=19.8)
    humidity: Optional[int] = Field(None, example=65)
    pressure: Optional[float] = Field(None, example=1013.2)
    wind_speed: Optional[float] = Field(None, example=5.2)
    wind_direction: Optional[str] = Field(None, example="северо-западный")
    condition: Optional[str] = Field(None, example="ясно")
    description: Optional[str] = Field(None, example="Ясная погода")

class WeatherCreate(WeatherBase):
    raw_data: Optional[dict] = None

class WeatherUpdate(BaseModel):
    temperature: Optional[float] = None
    feels_like: Optional[float] = None
    humidity: Optional[int] = None
    pressure: Optional[float] = None
    wind_speed: Optional[float] = None
    condition: Optional[str] = None

class WeatherResponse(WeatherBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class TaskResponse(BaseModel):
    status: str = Field(..., example="success")
    message: str = Field(..., example="Background task started")
    task_id: Optional[str] = None

class WebSocketMessage(BaseModel):
    type: str = Field(..., example="weather_update")
    data: dict
    timestamp: datetime = Field(default_factory=datetime.now)