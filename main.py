from typing import List, Dict, Any
import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi import Depends
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy import Column, Integer, String, Boolean, Text, select
from sqlalchemy.orm import declarative_base

import httpx

DATABASE_URL = "sqlite+aiosqlite:///./todo.db"
FETCH_SOURCE = "https://jsonplaceholder.typicode.com/todos"
BACKGROUND_INTERVAL = 60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("todo_app")

Base = declarative_base()

class TaskDB(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    done = Column(Boolean, default=False)
    external_id = Column(Integer, nullable=True)

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    done: bool = False

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    done: bool | None = None

class TaskRead(BaseModel):
    id: int
    title: str
    description: str | None
    done: bool

    model_config = {
        "from_attributes": True
    }

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.active_connections.append(websocket)
        logger.info("WebSocket connected: %s", websocket.client)

    async def disconnect(self, websocket: WebSocket):
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected: %s", websocket.client)

    async def broadcast(self, message: Dict[str, Any]):
        data = json.dumps(message, default=str)
        async with self.lock:
            conns = list(self.active_connections)
        for conn in conns:
            try:
                await conn.send_text(data)
            except Exception as e:
                logger.warning("Failed to send to websocket %s: %s", conn.client, e)

manager = ConnectionManager()

app = FastAPI(title="TODO API with WebSocket and Background Task")

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.bg_task = asyncio.create_task(background_worker())
    logger.info("Background worker started")

@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "bg_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Background worker cancelled")

@app.get("/tasks", response_model=List[TaskRead])
async def list_tasks(
    skip: int = 0, 
    limit: int = 100,
    session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        select(TaskDB).offset(skip).limit(limit)
    )
    tasks = result.scalars().all()
    return tasks

@app.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(TaskDB, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, session: AsyncSession = Depends(get_session)):
    db_task = TaskDB(
        title=payload.title, 
        description=payload.description, 
        done=payload.done
    )
    session.add(db_task)
    await session.commit()
    await session.refresh(db_task)
    
    await manager.broadcast({
        "event": "task_created", 
        "task": TaskRead.model_validate(db_task).model_dump()
    })
    return db_task

@app.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int, 
    payload: TaskUpdate, 
    session: AsyncSession = Depends(get_session)
):
    task = await session.get(TaskDB, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        for field, value in update_data.items():
            setattr(task, field, value)
        await session.commit()
        await session.refresh(task)
        
        await manager.broadcast({
            "event": "task_updated", 
            "task": TaskRead.model_validate(task).model_dump()
        })
    return task

@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, session: AsyncSession = Depends(get_session)):
    task = await session.get(TaskDB, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await session.delete(task)
    await session.commit()
    
    await manager.broadcast({
        "event": "task_deleted", 
        "task_id": task_id
    })

@app.post("/task-generator/run")
async def run_task_generator(session: AsyncSession = Depends(get_session)):
    created = await run_background_fetch_once(session)
    return {"created": created}

@app.websocket("/ws/tasks")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        await manager.disconnect(websocket)

async def fetch_external_tasks() -> List[Dict[str, Any]]:
    """Fetch tasks from external HTTP source."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(FETCH_SOURCE)
            resp.raise_for_status()
            data = resp.json()
            
            if not isinstance(data, list):
                logger.error("Expected list from external API, got %s", type(data))
                return []
            
            tasks = []
            for item in data:
                title = item.get("title")
                if not title or not isinstance(title, str):
                    continue
                    
                tasks.append({
                    "external_id": item.get("id"),
                    "title": title[:255],
                    "description": None,
                    "done": bool(item.get("completed", False)),
                })
            return tasks
            
        except Exception as e:
            logger.error("Failed to fetch external tasks: %s", e)
            return []

async def run_background_fetch_once(session: AsyncSession) -> int:
    """Fetch and insert new tasks; returns number of created tasks."""
    try:
        external_tasks = await fetch_external_tasks()
    except Exception as e:
        logger.error("Error fetching tasks: %s", e)
        return 0
    
    if not external_tasks:
        return 0

    result = await session.execute(
        select(TaskDB.external_id).where(TaskDB.external_id.isnot(None))
    )
    existing_ids = {row[0] for row in result.fetchall()}
    
    created_tasks = []
    created_count = 0
    
    for item in external_tasks:
        ext_id = item.get("external_id")
        if ext_id is None or ext_id in existing_ids:
            continue
            
        new_task = TaskDB(
            title=item["title"],
            description=item["description"],
            done=item["done"],
            external_id=ext_id,
        )
        session.add(new_task)
        created_tasks.append(new_task)
        created_count += 1
    
    if created_count > 0:
        await session.commit()
        tasks_data = [
            TaskRead.model_validate(task).model_dump() 
            for task in created_tasks
        ]
        await manager.broadcast({
            "event": "tasks_generated", 
            "tasks": tasks_data,
            "count": created_count
        })
        logger.info("Created %d new tasks from external source", created_count)
    
    return created_count

async def background_worker():
    """Runs forever, periodically fetching tasks and inserting into DB."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await run_background_fetch_once(session)
        except asyncio.CancelledError:
            logger.info("Background worker cancelled")
            raise
        except Exception as e:
            logger.error("Error in background worker: %s", e)
        
        await asyncio.sleep(BACKGROUND_INTERVAL)

@app.get("/health")
async def health():
    return {"status": "ok", "websocket_connections": len(manager.active_connections)}
