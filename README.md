## Инструкция по запуску

### 1. Запуск контейнера docker
```bash
docker-compose up -d nats
```

### 2. В другом терминале. Создание и активирование виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка зависимостей из requirements.txt
```bash
pip install -r requirements.txt
```

### 4. Запуск сервера
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Проверка работоспособности
Откройте в браузере:
- Документация API: http://localhost:8000/docs
- Nats: http://localhost:8222

Далее создайте, обновите или удалите задачу

### 6. Проверка работоспособности WebSocket
Напишите в терминале:
```bash
wscat -c ws://127.0.0.1:8000/api/v1/ws/weather
```

### 7. Проверка работоспособности Nats sub
Напишите в терминале:
```bash
nats sub ">"
```


