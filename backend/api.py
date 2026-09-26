import os, re, json, time, glob, base64, secrets, sqlite3, subprocess, sys, platform

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from dotenv import load_dotenv
import httpx

# ---------------------------------------------------------------------------
# 1. Config / environment loading (FIXED: load BOTH .env files, merge)
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)

# Root .env holds GROQ_API_KEY etc; backend/.env may hold overrides.
load_dotenv(os.path.join(APP_DIR, ".env"))
load_dotenv(os.path.join(BACKEND_DIR, ".env"), override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
OSCAR_EMAIL = os.getenv("OSCAR_EMAIL", "").strip().lower()
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "1") == "1"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))

# ---------------------------------------------------------------------------
# 2. AI clients
# ---------------------------------------------------------------------------
groq_client = None
if GROQ_API_KEY:
    groq_client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

deepseek_client = None
if DEEPSEEK_API_KEY:
    deepseek_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# ---------------------------------------------------------------------------
# 3. Paths
# ---------------------------------------------------------------------------
is_windows = platform.system() == "Windows"
if is_windows:
    fusion_dir = r"C:\FUSION"
    potree_converter = None
else:
    fusion_dir = os.path.expanduser("~/.wine/drive_c/FUSION/")
    potree_converter = os.getenv(
        "POTREE_CONVERTER",
        os.path.expanduser("~/PotreeConverter_2.1.2_x64_linux/PotreeConverter"),
    )

potree_dir = os.path.join(fusion_dir, "potree")
os.makedirs(potree_dir, exist_ok=True)

# ---------------------------------------------------------------------------
# 4. SQLite database
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(BACKEND_DIR, "fusion.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    picture TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at REAL,
    expires_at REAL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT,
    is_pinned INTEGER DEFAULT 0,
    updated_at REAL,
    chat_history TEXT,
    ide_logs TEXT,
    created_at REAL,
    PRIMARY KEY (id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------------------------
# 5. Google auth helpers
# ---------------------------------------------------------------------------
try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
    _google_auth_available = True
except Exception:
    _google_auth_available = False

def verify_google_id_token(token: str) -> dict:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login no configurado (falta GOOGLE_CLIENT_ID).")
    if not _google_auth_available:
        raise HTTPException(status_code=500, detail="google-auth no instalado en el servidor.")
    return google_id_token.verify_oauth2_token(token, google_requests.Request(), audience=GOOGLE_CLIENT_ID)

def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, now + SESSION_TTL_DAYS * 86400),
    )
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str):
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        "SELECT u.id, u.email, u.name, u.picture FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.expires_at > ?",
        (token, time.time()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_session_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.cookies.get("fusion_session", "") or ""

def require_auth(request: Request):
    if not AUTH_REQUIRED:
        return None
    token = get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    return user

# ---------------------------------------------------------------------------
# 6. FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Fusion Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/potree", StaticFiles(directory=potree_dir), name="potree")

# ---------------------------------------------------------------------------
# 7. RAG database (FUSION commands)
# ---------------------------------------------------------------------------
FUSION_DB = {}
_fusion_db_path = os.path.join(BACKEND_DIR, "fusion_commands.json")
if os.path.exists(_fusion_db_path):
    with open(_fusion_db_path, "r", encoding="utf-8") as f:
        FUSION_DB = json.load(f)

FUSION_TOOLS = ", ".join(FUSION_DB.keys())

@app.get("/api/config")
async def get_config():
    return {"google_client_id": GOOGLE_CLIENT_ID, "auth_required": AUTH_REQUIRED}

# ---------------------------------------------------------------------------
# 8. Auth routes
# ---------------------------------------------------------------------------
@app.post("/api/auth/google")
async def auth_google(request: Request):
    body = await request.json()
    credential = body.get("credential") or body.get("id_token")
    if not credential:
        raise HTTPException(status_code=400, detail="Falta el token de Google")
    claims = verify_google_id_token(credential)
    sub = claims.get("sub")
    email = (claims.get("email") or "").lower()
    name = claims.get("name") or email.split("@")[0]
    picture = claims.get("picture") or ""

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE id = ?", (sub,)).fetchone()
    if existing:
        conn.execute("UPDATE users SET email = ?, name = ?, picture = ? WHERE id = ?", (email, name, picture, sub))
    else:
        conn.execute(
            "INSERT INTO users (id, email, name, picture, created_at) VALUES (?, ?, ?, ?, ?)",
            (sub, email, name, picture, time.time()),
        )
    conn.commit()
    conn.close()

    token = create_session(sub)
    return {"token": token, "user": {"id": sub, "email": email, "name": name, "picture": picture}}

@app.get("/api/auth/me")
async def auth_me(user=Depends(require_auth)):
    return {"user": user}

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = get_session_token(request)
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# 9. Projects (per-user chat history)
# ---------------------------------------------------------------------------
def _project_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "is_pinned": bool(row["is_pinned"]),
        "updated_at": row["updated_at"],
        "chat_history": json.loads(row["chat_history"] or "[]"),
        "ide_logs": row["ide_logs"] or "Esperando comandos...",
    }

@app.get("/api/projects")
async def list_projects(user=Depends(require_auth)):
    if user is None:
        return {"projects": []}
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (user["id"],)
    ).fetchall()
    conn.close()
    return {"projects": [_project_to_dict(r) for r in rows]}

@app.post("/api/projects")
async def save_project(request: Request, user=Depends(require_auth)):
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    body = await request.json()
    pid = body.get("id")
    if not pid:
        raise HTTPException(status_code=400, detail="Falta id")
    name = body.get("name") or "Sin título"
    is_pinned = 1 if body.get("is_pinned") else 0
    updated_at = float(body.get("updated_at") or time.time())
    chat_history = json.dumps(body.get("chat_history") or [], ensure_ascii=False)
    ide_logs = body.get("ide_logs") or "Esperando comandos..."

    conn = get_db()
    conn.execute(
        "INSERT INTO projects (id, user_id, name, is_pinned, updated_at, chat_history, ide_logs, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id, user_id) DO UPDATE SET "
        "name=excluded.name, is_pinned=excluded.is_pinned, updated_at=excluded.updated_at, "
        "chat_history=excluded.chat_history, ide_logs=excluded.ide_logs",
        (pid, user["id"], name, is_pinned, updated_at, chat_history, ide_logs, time.time()),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.delete("/api/projects/{pid}")
async def delete_project(pid: str, user=Depends(require_auth)):
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    conn = get_db()
    conn.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (pid, user["id"]))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# 10. Chat (RAG: Librarian -> Retriever -> Foreman)
# ---------------------------------------------------------------------------
def _pick_client(model: str):
    if "deepseek" in model.lower():
        return deepseek_client
    return groq_client

@app.post("/api/chat")
async def chat_endpoint(text: str = Form(...), model: str = Form("llama-3.1-70b-versatile"), user=Depends(require_auth)):
    active_client = _pick_client(model)
    if active_client is None:
        raise HTTPException(status_code=503, detail="Cliente de IA no configurado para este modelo.")

    router_sys = (
        "You are the Master Planner for FUSION LiDAR tasks. The user will give you a request (sometimes specific, sometimes vague like 'recommend an operation').\n"
        "Your job is to analyze their request, design a FUSION workflow to solve it, and output ONLY the names of the tools needed.\n"
        "Here are all the available FUSION tools you can choose from: " + FUSION_TOOLS + "\n\n"
        "RULES:\n"
        "1. If the user asks a vague question (e.g. 'what can I do with a LAS?'), invent a cool workflow (like creating a DTM and DSM) and output the tools for it (e.g. GroundFilter, GridSurfaceCreate, CanopyModel).\n"
        "2. Reply ONLY with a comma-separated list of the tool names. Absolutely no other text.\n"
        "3. If the user is just saying 'hello' or making small talk with no relation to LiDAR, reply with NONE."
    )
    try:
        router_chat = await active_client.chat.completions.create(
            messages=[{"role": "system", "content": router_sys}, {"role": "user", "content": text}],
            model=model, temperature=0.0,
        )
        commands_needed_str = (router_chat.choices[0].message.content or "").strip()
    except Exception as e:
        commands_needed_str = "NONE"
        print(f"[router] error: {e}")

    rag_context = ""
    if commands_needed_str and commands_needed_str.upper() != "NONE":
        requested = [c.strip() for c in commands_needed_str.replace("`", "").split(",")]
        for cmd in requested:
            for db_cmd in FUSION_DB:
                if db_cmd.lower() == cmd.lower():
                    rag_context += f"\n\n=== OFFICIAL MANUAL FOR {db_cmd} ===\n{FUSION_DB[db_cmd]}\n"
                    break

    dynamic_sys_prompt = (
        "Eres un Profesor Experto Catedrático en Topografía LiDAR, Teledetección y en el ecosistema FUSION-LTK.\n"
        "REGLAS DE COMUNICACIÓN (ACTITUD PROFESIONAL):\n"
        "- Tu nivel técnico es altísimo y riguroso. Habla de ingeniero a ingeniero.\n"
        "- ELIMINA por completo las frases genéricas, infantiles o serviciales de IA (PROHIBIDO decir '¡Claro!', '¡Por supuesto!', 'Aquí tienes', 'Espero que te sirva', '¡Éxitos!').\n"
        "- Ve directo al grano. Explica el razonamiento técnico.\n"
        "- Anticípate a errores clásicos: si el usuario no te da la zona UTM, recuérdale con severidad que usar 'Zona 0' generará problemas de proyección en los TIFs (efecto Isla Null en ArcGIS).\n"
        "REGLAS TÉCNICAS Y SINTAXIS FUSION-LTK:\n"
        "- Las ÚNICAS herramientas nativas de FUSION que existen y que puedes usar son: " + FUSION_TOOLS + ". NUNCA inventes nombres de .exe que no estén en esta lista.\n"
        "- FUSION usa extensiones propietarias (.dtm) y archivos (.las). Los ejecutables están en C:\\FUSION\\\n"
        "- NUNCA uses LAStools ni herramientas externas. Usa SOLO los ejecutables oficiales de FUSION.\n"
        "- Para generar un MDT a partir de un LAS: PRIMERO se filtra la nube con GroundFilter y LUEGO se rasteriza con GridSurfaceCreate.\n"
        "- Agrupa todos los comandos a ejecutar en UN ÚNICO BLOQUE DE CÓDIGO BATCH (```bat), uno por línea. NO uses bloques separados. NO uses '#' para comentarios, en Batch los comentarios se escriben con 'REM '.\n\n"
    )
    if rag_context:
        dynamic_sys_prompt += (
            "A CONTINUACIÓN TIENES EXTRACTOS DEL MANUAL OFICIAL DE FUSION PARA ESTA TAREA:\n"
            "LEELOS CUIDADOSAMENTE PARA NO INVENTARTE NINGÚN 'SWITCH' NI PARÁMETRO QUE NO EXISTA.\n"
            f"{rag_context}\n"
        )
    else:
        dynamic_sys_prompt += "NO SE NECESITAN COMANDOS ESPECÍFICOS PARA ESTA TAREA, ACTÚA COMO UN ASISTENTE NORMAL.\n"

    chat = await active_client.chat.completions.create(
        messages=[{"role": "system", "content": dynamic_sys_prompt}, {"role": "user", "content": text}],
        model=model, temperature=0.3,
    )
    reply = (chat.choices[0].message.content or "").strip()
    return {"transcription": text, "text": reply}

# ---------------------------------------------------------------------------
# 11. Audio transcription
# ---------------------------------------------------------------------------
@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), user=Depends(require_auth)):
    if groq_client is None:
        raise HTTPException(status_code=503, detail="Groq no configurado")
    try:
        temp_path = os.path.join("/tmp", audio.filename or "voice.webm")
        data = await audio.read()
        with open(temp_path, "wb") as f:
            f.write(data)
        with open(temp_path, "rb") as f:
            transcription = await groq_client.audio.transcriptions.create(
                file=(audio.filename or "voice.webm", f.read()),
                model="whisper-large-v3",
                prompt="El usuario está hablando sobre LiDAR y topografía en español.",
                response_format="json",
                language="es",
                temperature=0.0,
            )
        os.remove(temp_path)
        return {"text": transcription.text}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------------------------
# 12. Execute FUSION commands
# ---------------------------------------------------------------------------
def _run_preview_script(script_name, *args) -> bool:
    script = os.path.join(BACKEND_DIR, script_name)
    try:
        subprocess.run([sys.executable, script, *args], check=True, capture_output=True, timeout=300)
        return True
    except Exception as e:
        print(f"[preview] {script_name} failed: {e}")
        return False

@app.post("/api/execute")
async def execute_command(command: str = Form(...), user=Depends(require_auth)):
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    bat_name = f"temp_exec_{secrets.token_hex(6)}.bat"
    bat_path = os.path.join(fusion_dir, bat_name)

    win_command = re.sub(r'\\\s*\n', ' ', command)
    win_command = win_command.strip().replace('\r', '').replace('\n', '\r\n')

    with open(bat_path, "w") as f:
        f.write(win_command)

    if is_windows:
        full_cmd = f'cd /d "{fusion_dir}" && {bat_name}'
    else:
        full_cmd = f'cd {fusion_dir} && xvfb-run -a wine cmd /c {bat_name}'

    start_time = time.time()
    result = None
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return {"status": "error", "logs": "Timeout: el comando tardó demasiado (>30 min)."}
    finally:
        try:
            if os.path.exists(bat_path):
                os.remove(bat_path)
        except Exception:
            pass

    new_files = []
    for f in glob.glob(os.path.join(fusion_dir, "*")):
        if not os.path.isfile(f):
            continue
        if os.path.getmtime(f) <= start_time - 2:
            continue
        filename = os.path.basename(f)
        if filename.lower() == "betera15.las" or filename.startswith("temp_exec_"):
            continue

        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        file_info = {"name": filename, "type": ext, "url": f"/files/{filename}"}

        if ext == "dtm":
            out_tif = f + ".tif"
            out_png = f + ".png"
            base_name = os.path.basename(f)
            base_tif = base_name + ".tif"
            try:
                if is_windows:
                    subprocess.run(f'C:\\FUSION\\DTM2TIF.exe "{base_name}" "{base_tif}"', shell=True, cwd=fusion_dir, timeout=300)
                else:
                    subprocess.run(f"xvfb-run -a wine DTM2TIF.exe '{base_name}' '{base_tif}'", shell=True, cwd=fusion_dir, timeout=300)
                if os.path.exists(out_tif):
                    _run_preview_script("tif_preview.py", out_tif, out_png)
            except Exception as e:
                print(f"[dtm preview] {e}")
            if os.path.exists(out_png):
                with open(out_png, "rb") as img_f:
                    file_info["preview_b64"] = base64.b64encode(img_f.read()).decode("utf-8")
                os.remove(out_png)
            if os.path.exists(out_tif):
                os.remove(out_tif)

        elif ext in ["tif", "tiff"]:
            out_png = f + ".png"
            _run_preview_script("tif_preview.py", f, out_png)
            if os.path.exists(out_png):
                with open(out_png, "rb") as img_f:
                    file_info["preview_b64"] = base64.b64encode(img_f.read()).decode("utf-8")
                os.remove(out_png)

        elif ext in ["las", "laz"]:
            out_png = f + ".png"
            _run_preview_script("las_preview.py", f, out_png)
            if os.path.exists(out_png):
                with open(out_png, "rb") as img_f:
                    file_info["preview_b64"] = base64.b64encode(img_f.read()).decode("utf-8")
                os.remove(out_png)

            potree_out = os.path.join(potree_dir, filename)
            if not os.path.exists(os.path.join(potree_out, "index.html")) and not is_windows and potree_converter:
                try:
                    subprocess.Popen(
                        f"'{potree_converter}' '{f}' -o '{potree_out}' --generate-page index",
                        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception as e:
                    print(f"[potree] {e}")
            file_info["html_3d_url"] = f"/potree/{filename}/index.html"

        new_files.append(file_info)

    logs = (result.stdout or "") + "\n" + (result.stderr or "") if result else ""
    return {"status": "success", "logs": logs, "files": new_files}

# ---------------------------------------------------------------------------
# 13. File serving (path traversal FIXED)
# ---------------------------------------------------------------------------
@app.get("/files/{filename}")
async def get_file(filename: str):
    if not filename or filename != os.path.basename(filename) or filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")
    path = os.path.join(fusion_dir, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path)

# ---------------------------------------------------------------------------
# 14. Google Drive (per-user)
# ---------------------------------------------------------------------------
def _is_owner(user) -> bool:
    if not user:
        return False
    return bool(OSCAR_EMAIL) and (user.get("email") or "").lower() == OSCAR_EMAIL

@app.get("/api/drive/status")
async def drive_status(user=Depends(require_auth)):
    if user is None:
        return {"owner": False}
    return {"owner": _is_owner(user), "email": user.get("email")}

@app.post("/api/drive/upload")
async def drive_upload(request: Request, user=Depends(require_auth)):
    if user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    if _is_owner(user):
        try:
            subprocess.run(
                "rclone copy ~/.wine/drive_c/FUSION/ GoogleDriveFusion:fusion_output --max-age 60m --exclude betera15.las",
                shell=True, check=True, timeout=600,
            )
            return {"status": "success", "mode": "owner"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    body = await request.json()
    access_token = body.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Conecta tu cuenta de Google Drive primero.")

    uploaded = []
    errors = []
    cutoff = time.time() - 3600
    for f in glob.glob(os.path.join(fusion_dir, "*")):
        if not os.path.isfile(f):
            continue
        if os.path.getmtime(f) < cutoff:
            continue
        fn = os.path.basename(f)
        if fn.lower() == "betera15.las" or fn.startswith("temp_exec_"):
            continue
        if os.path.getsize(f) > 50 * 1024 * 1024:
            continue
        try:
            with open(f, "rb") as fh:
                content = fh.read()
            metadata = {"name": fn}
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers={"Authorization": f"Bearer {access_token}"},
                    files={
                        "metadata": ("metadata", json.dumps(metadata), "application/json"),
                        "file": (fn, content, "application/octet-stream"),
                    },
                )
            if r.status_code in (200, 201):
                uploaded.append(fn)
            else:
                errors.append(f"{fn}: {r.status_code}")
        except Exception as e:
            errors.append(f"{fn}: {e}")

    return {"status": "success" if uploaded else "error", "mode": "user_drive", "uploaded": uploaded, "errors": errors}

# ---------------------------------------------------------------------------
# 15. Deploy webhook
# ---------------------------------------------------------------------------
@app.post("/api/webhook")
async def github_webhook(request: Request):
    if WEBHOOK_SECRET:
        supplied = request.query_params.get("token", "")
        sig = request.headers.get("X-Hub-Signature-256", "")
        if supplied != WEBHOOK_SECRET and not sig.endswith(WEBHOOK_SECRET):
            raise HTTPException(status_code=403, detail="Secreto inválido")
    subprocess.Popen(["bash", os.path.join(BACKEND_DIR, "deploy.sh")])
    return {"status": "deploying"}

# ---------------------------------------------------------------------------
# 16. Cache headers
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html") or request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# ---------------------------------------------------------------------------
# 17. Serve built frontend
# ---------------------------------------------------------------------------
_dist_dir = os.path.join(APP_DIR, "frontend", "dist")
if os.path.exists(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="static")
