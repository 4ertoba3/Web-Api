##Инструкция по запуску
#Создание и активирование виртуального окружения
-python3 -m venv venv
-source venv/bin/activate

#Установка зависимости из requirements.txt
-pip install -r requirements.txt


#Запуск сервера
-uvicorn main:app --reload
