# Running the web demo

All commands are run from the project root unless stated otherwise.

## One-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install fastapi uvicorn
```

Create a `.env` file in the project root:

```ini
HELPDESK_MODEL=groq/qwen/qwen3.8-27b
GROQ_API_KEY=your_groq_key
EMBEDDING_BACKEND=local
CORPUS_SOURCE=prebuilt
VECTOR_BACKEND=numpy
TOP_K=3
PASSAGE_MAX_CHARS=1300
MAX_RELEVANT_DISTANCE=0.50
```

Load the document index (once):

```powershell
python -m academic_helpdesk.rag.import_prebuilt
```

## Backend

```powershell
python -m web.backend.service
```

Runs at http://127.0.0.1:8000 (use `--port 8080` to change the port). It also serves
the built frontend, so for normal use this is the only command you need.

## Frontend

The built frontend is already included in `web/frontend/dist/`; nothing to do unless you
change the UI.

To work on the UI (requires Node.js), keep the backend running and, in a second terminal:

```powershell
cd web\frontend
npm install
npm run dev
```

Open http://localhost:5173. To rebuild the bundle the backend serves:

```powershell
npm run build
```
