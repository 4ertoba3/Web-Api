from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from app import models, schemas

async def create_weather_data(db: AsyncSession, weather: schemas.WeatherCreate):
    stmt = select(models.WeatherData).where(models.WeatherData.city == weather.city)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        history = models.WeatherHistory(
            city=existing.city,
            temperature=existing.temperature,
            feels_like=existing.feels_like,
            humidity=existing.humidity,
            pressure=existing.pressure,
            wind_speed=existing.wind_speed,
            wind_direction=existing.wind_direction,
            condition=existing.condition
        )
        db.add(history)
        
        for key, value in weather.dict(exclude_unset=True).items():
            setattr(existing, key, value)
        await db.commit()
        await db.refresh(existing)
        return existing
    
    db_weather = models.WeatherData(**weather.dict())
    db.add(db_weather)
    await db.commit()
    await db.refresh(db_weather)
    return db_weather

async def get_weather_data(db: AsyncSession, weather_id: int):
    stmt = select(models.WeatherData).where(models.WeatherData.id == weather_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_all_weather_data(db: AsyncSession, skip: int = 0, limit: int = 100):
    stmt = select(models.WeatherData).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_weather_by_city(db: AsyncSession, city: str):
    stmt = select(models.WeatherData).where(models.WeatherData.city == city)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_weather_data(db: AsyncSession, weather_id: int, weather_update: schemas.WeatherUpdate):
    stmt = select(models.WeatherData).where(models.WeatherData.id == weather_id)
    result = await db.execute(stmt)
    db_weather = result.scalar_one_or_none()
    
    if db_weather:
        history = models.WeatherHistory(
            city=db_weather.city,
            temperature=db_weather.temperature,
            feels_like=db_weather.feels_like,
            humidity=db_weather.humidity,
            pressure=db_weather.pressure,
            wind_speed=db_weather.wind_speed,
            wind_direction=db_weather.wind_direction,
            condition=db_weather.condition
        )
        db.add(history)
        
        update_data = weather_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_weather, key, value)
        
        await db.commit()
        await db.refresh(db_weather)
    
    return db_weather

async def delete_weather_data(db: AsyncSession, weather_id: int):
    stmt = delete(models.WeatherData).where(models.WeatherData.id == weather_id)
    await db.execute(stmt)
    await db.commit()
    return True

async def get_weather_history(db: AsyncSession, city: str, hours: int = 24):
    time_threshold = datetime.now() - timedelta(hours=hours)
    stmt = select(models.WeatherHistory).where(
        models.WeatherHistory.city == city,
        models.WeatherHistory.recorded_at >= time_threshold
    ).order_by(models.WeatherHistory.recorded_at.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()