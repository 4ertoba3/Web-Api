## Инструкция по запуску

### 1. Создание и активирование виртуального окружения
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Установка зависимостей из requirements.txt
```bash
pip install -r requirements.txt
```

### 3. Запуск сервера
```bash
uvicorn main:app --reload
```

### 4. Проверка работоспособности
Откройте в браузере:
- Документация API: http://localhost:8000/docs

### 5. Проверка работоспособности WebSocket
Напишите в терминале:
```bash
wscat -c ws://127.0.0.1:8000/ws/tasks
```
А далее создайте, обновите или удалите задачу
