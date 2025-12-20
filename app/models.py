from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base

class WeatherData(Base):
    __tablename__ = "weather_data"
    
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    temperature = Column(Float)
    feels_like = Column(Float)
    humidity = Column(Integer)
    pressure = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(String)
    condition = Column(String)
    description = Column(String)
    raw_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"WeatherData(city={self.city}, temp={self.temperature})"

class WeatherHistory(Base):
    __tablename__ = "weather_history"
    
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, index=True)
    temperature = Column(Float)
    feels_like = Column(Float)
    humidity = Column(Integer)
    pressure = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(String)
    condition = Column(String)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())