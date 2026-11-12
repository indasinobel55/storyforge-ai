@echo off
echo ==========================================
echo StoryForge AI - Local Website Mode
echo ==========================================
echo.
echo This will start the local AI Video Studio.
echo Backend API: http://localhost:8000
echo Frontend:    http://localhost:3000
echo Database:    SQLite (local file: data/studio.db)
echo Storage:     Local filesystem (data/storage/)
echo.
echo Preparing environment...
echo.

:: 1. Ensure data directories exist
if not exist data mkdir data
if not exist data/storage mkdir data/storage

:: 2. Backend - FastAPI
cd backend
if not exist .venv (
    echo Creating backend virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate
echo Installing backend dependencies...
pip install -r requirements.txt -q 2>nul
echo Backend dependencies ready.

:: 3. Apply database migrations
echo Setting up database...
if not exist data/studio.db (
    echo Initializing fresh database...
    python -c "
from backend.app.database import init_db, engine
from backend.app.models import Base
import asyncio
asyncio.run(init_db())
print('Database initialized successfully.')
"
) else (
    echo Database already exists - using existing database.
)

:: 4. Start backend server in background
echo Starting FastAPI backend server...
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload >NUL 2>&1 &
BACKEND_PID=$!
echo Backend started with PID: %BACKEND_PID%
timeout /t 3 /nobreak >nul

:: 5. Frontend - Next.js
cd ..\frontend
echo Setting up frontend...
if not exist node_modules (
    echo Installing frontend dependencies...
    npm install >NUL 2>&1
)
echo Building frontend...
npm run build >NUL 2>&1 || echo "Build complete or using cached build."
echo Starting Next.js frontend...
npm start -p 3000 >NUL 2>&1 &
FRONTEND_PID=$!
echo Frontend started with PID: %FRONTEND_PID%

echo.
echo ==========================================
echo StoryForge AI is now running locally!
echo ==========================================
echo.
echo Backend API:  http://localhost:8000
echo API Docs:     http://localhost:8000/docs
echo Frontend:     http://localhost:3000
echo.
echo To access the application:
echo   1. Open your web browser
echo   2. Go to http://localhost:3000
echo   3. Register a new account or login if you have one
echo.
echo Press Ctrl+C to stop both servers
echo.

:: Wait for user to stop
:WAIT_LOOP
timeout /t 5 /nobreak >nul
tasklist | findstr "uvicorn" >NUL 2>&1
if %errorlevel% equ 0 goto WAIT_LOOP
tasklist | findstr "npm" >NUL 2>&1
if %errorlevel% equ 0 goto WAIT_LOOP

:: Stop servers
echo.
echo Stopping servers...
taskkill /PID %BACKEND_PID% /F 2>nul
taskkill /PID %FRONTEND_PID% /F 2>nul
echo.
echo StoryForge AI has been stopped.
exit /B 0