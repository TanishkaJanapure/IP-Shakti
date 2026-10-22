# IP-SAKTI Sahayak — Updated Project

A React/Vite frontend and FastAPI backend for Ayurveda IPR and regulatory research using a multilingual hybrid RAG corpus.

## Included changes
- SQLite-backed registration/login endpoints with salted PBKDF2 password hashing.
- Account profile is loaded from `/auth/me`; session token is held in `sessionStorage`.
- Global language selector in the top-right corner (English, Marathi, Hindi, Tamil, Telugu, Bengali).
- UI text translations for common navigation and account controls; selected language is persisted locally.
- Chat API language enum extended to Marathi, Hindi, Tamil, Telugu, and Bengali in addition to English.
- Legal Sources / Prior-Art search now calls the real `/search` endpoint instead of showing fabricated sample records.
- Existing hybrid retrieval and evidence-aware chat pipeline retained.
- `.env` secrets are not included. Configure your own backend key.

## Requirements
- Node.js 20+ and npm (Node 22 recommended)
- Python 3.11+
- A Gemini API key for generated answers (retrieval/search works without a key; `/chat` needs the key).

## Start backend (Windows PowerShell)
```powershell
cd Backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY to your own rotated key
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Swagger: http://127.0.0.1:8000/docs

## Start frontend (new terminal)
```powershell
cd <project-folder>
npm install
npm run dev
```
Open the Vite URL printed in the terminal (normally http://localhost:5173).

## Environment variables
`Backend/.env.example` is a template. Never commit `.env`, never put API keys in frontend code, and rotate any key that has been shared publicly.

## Data and persistence
- Corpus chunks and FAISS index are included under `Backend/data/vector_store`.
- Extracted source records are included under `Backend/data/processed`.
- User accounts and query history are stored in `Backend/data/users.sqlite3`, created automatically at runtime.
- The API's in-memory session tokens expire on backend restart; users can sign in again.
- Query history endpoints exist at `/auth/history`; only save history if the client explicitly sends it.

## Multilingual note
The answer-generation prompt supports all six languages. The retrieval pipeline uses a multilingual embedding model and English query expansion for non-English queries. Legal accuracy still depends on the indexed source coverage. The frontend dictionary currently translates common UI labels, not every paragraph or every legal excerpt; untranslated specialist text can remain in English.

## Tests and limitations
Run backend syntax check:
```powershell
python -m compileall .
```
Run tests:
```powershell
python -m unittest discover -v
```
Run frontend production build:
```powershell
npm run build
```

Backend — Terminal 1
Open PowerShell and run:
    cd S:\Downloads\IP-SAKTI-Sahayak-Updated\IP-SAKTI-Sahayak-Updated\Backend

Activate your virtual environment if you have one. Then start the backend:
    python -m uvicorn main:app --host 127.0.0.1 --port 8001

Open the API documentation: http://127.0.0.1:8001/docs
Keep this terminal running.



Frontend — Terminal 2
Open a second PowerShell terminal and run:
  cd S:\Downloads\IP-SAKTI-Sahayak-Updated\IP-SAKTI-Sahayak-Updated
  npm install
  npm run dev -- --port 8443



Run backend tests
Open another terminal:
   cd S:\Downloads\IP-SAKTI-Sahayak-Updated\IP-SAKTI-Sahayak-Updated\Backend
   python -m pytest -q

   
The archive was assembled and Python files passed syntax compilation in the build environment. A full npm production build could not be confirmed because package installation did not complete in the build environment; run the commands above locally and share any error output for a targeted fix.
"# IP-Shakti" 
