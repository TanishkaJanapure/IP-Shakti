@echo off
echo Start the IP-SAKTI Sahayak backend in a separate terminal first:
echo   cd Backend
echo   .venv\Scripts\activate
echo   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
echo.
echo Then install frontend dependencies and start Vite:
echo   npm install
echo   npm run dev
pause
