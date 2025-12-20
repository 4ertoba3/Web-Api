from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import json
import logging

from app.database import get_db
from app import crud, schemas
from app.background import background_task
from app.websocket import manager
from app.config import settings
from app.nats_client import nats_client

router = APIRouter()
logger = logging.getLogger(__name__)

# ========== Вспомогательные функции ==========

def weather_to_dict(db_weather):
    """Преобразование объекта WeatherData в словарь для JSON"""
    return {
        "id": db_weather.id,
        "city": db_weather.city,
        "temperature": db_weather.temperature,
        "feels_like": db_weather.feels_like,
        "humidity": db_weather.humidity,
        "pressure": db_weather.pressure,
        "wind_speed": db_weather.wind_speed,
        "wind_direction": db_weather.wind_direction,
        "condition": db_weather.condition,
        "description": db_weather.description,
        "created_at": db_weather.created_at.isoformat() if db_weather.created_at else None,
        "raw_data": db_weather.raw_data
    }

async def _handle_weather_change(operation, city, data, weather_id=None):
    """Обработка изменений погоды с уведомлениями"""
    # WebSocket уведомление
    if operation == "update" or operation == "create":
        await manager.broadcast_weather_update(city, data)
    elif operation == "delete":
        await manager.broadcast({
            "type": "weather_deleted",
            "weather_id": weather_id,
            "timestamp": datetime.now().isoformat()
        })
    
    # NATS уведомление
    if nats_client.is_connected:
        if operation == "create":
            await nats_client.publish_weather_event("created", city, data)
        elif operation == "update":
            await nats_client.publish_weather_event("updated", city, data)
        elif operation == "delete":
            await nats_client.publish_weather_event("deleted", None, None, weather_id)

# ========== REST API ==========

@router.get("/weather", response_model=list[schemas.WeatherResponse])
async def get_all_weather(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.get_all_weather_data(db, skip=skip, limit=limit)

@router.get("/weather/{weather_id}", response_model=schemas.WeatherResponse)
async def get_weather(weather_id: int, db: AsyncSession = Depends(get_db)):
    weather = await crud.get_weather_data(db, weather_id)
    if weather is None:
        raise HTTPException(status_code=404, detail="Weather data not found")
    return weather

@router.get("/weather/city/{city}", response_model=schemas.WeatherResponse)
async def get_weather_by_city(city: str, db: AsyncSession = Depends(get_db)):
    weather = await crud.get_weather_by_city(db, city)
    if weather is None:
        raise HTTPException(status_code=404, detail=f"Weather data for city '{city}' not found")
    return weather

@router.get("/weather/history/{city}")
async def get_weather_history(city: str, hours: int = 24, db: AsyncSession = Depends(get_db)):
    return await crud.get_weather_history(db, city, hours)

@router.post("/weather", response_model=schemas.WeatherResponse, status_code=201)
async def create_weather(weather: schemas.WeatherCreate, db: AsyncSession = Depends(get_db)):
    db_weather = await crud.create_weather_data(db, weather)
    await _handle_weather_change("create", weather.city, weather_to_dict(db_weather))
    return db_weather

@router.patch("/weather/{weather_id}", response_model=schemas.WeatherResponse)
async def update_weather(weather_id: int, weather_update: schemas.WeatherUpdate, db: AsyncSession = Depends(get_db)):
    db_weather = await crud.update_weather_data(db, weather_id, weather_update)
    if db_weather is None:
        raise HTTPException(status_code=404, detail="Weather data not found")
    await _handle_weather_change("update", db_weather.city, weather_to_dict(db_weather))
    return db_weather

@router.delete("/weather/{weather_id}", status_code=204)
async def delete_weather(weather_id: int, db: AsyncSession = Depends(get_db)):
    success = await crud.delete_weather_data(db, weather_id)
    if not success:
        raise HTTPException(status_code=404, detail="Weather data not found")
    await _handle_weather_change("delete", None, None, weather_id)
    return None

# ========== Фоновые задачи ==========

async def _publish_nats_event(event_type, data=None):
    if nats_client.is_connected:
        await nats_client.publish_system_event(event_type, data or {})

@router.post("/tasks/run", response_model=schemas.TaskResponse)
async def run_background_task():
    try:
        await background_task.run_once()
        await _publish_nats_event("task_manual_run", {"status": "success", "task": "background_task"})
        return schemas.TaskResponse(
            status="success",
            message="Background task executed successfully",
            task_id=background_task.task_id
        )
    except Exception as e:
        logger.error(f"Ошибка запуска фоновой задачи: {e}")
        await _publish_nats_event("task_manual_run", {"status": "error", "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Error executing background task: {str(e)}")

# ========== WebSocket ==========

@router.websocket("/ws/weather")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await manager.connect(websocket)
    
    try:
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "message": "Connected to Weather Monitoring WebSocket",
                "timestamp": datetime.now().isoformat(),
                "nats_connected": nats_client.is_connected
            }),
            websocket
        )
        
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                elif msg_type == "nats_publish" and nats_client.is_connected:
                    subject = message.get("subject", settings.nats_subject_commands)
                    await nats_client.publish(subject, message.get("message", {}))
                    await websocket.send_json({"type": "nats_published", "subject": subject, "timestamp": datetime.now().isoformat()})
                elif msg_type == "get_status":
                    await websocket.send_json({
                        "type": "status",
                        "data": {
                            "websocket_connections": len(manager.active_connections),
                            "background_task_running": background_task.is_running,
                            "nats_connected": nats_client.is_connected,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
                    
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket отключен. Осталось: {len(manager.active_connections)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)