from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import subprocess
import time
import glob
import base64
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv('GROQ_API_KEY'))

app = FastAPI()

import os
import platform
is_windows = platform.system() == "Windows"

if is_windows:
    fusion_dir = r"C:\FUSION"
else:
    fusion_dir = os.path.expanduser('~/.wine/drive_c/FUSION/')

potree_dir = os.path.join(fusion_dir, 'potree')
os.makedirs(potree_dir, exist_ok=True)
app.mount('/potree', StaticFiles(directory=potree_dir), name='potree')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FUSION_CHEAT_SHEET = r"""
ERES UN EXPERTO EN TOPOGRAFÍA Y FUSION-LTK.
Tu objetivo es ayudar al usuario a procesar datos LiDAR. Puedes conversar en español, explicar tus pasos y sugerir flujos de trabajo.

REGLASÍ:
- NO inventes archivos que no existan. Si el usuario no da nombre de archivo de entrada, usa el que haya: C:\FUSION\betera15.las
- Los ejecutables están en C:\FUSION\
- La sintaxis NO usa -i ni -o, usa argumentos posicionales según el manual oficial.

CÓDIGO BASÍ:
```bash
C:\FUSION\GroundFilter C:\FUSION\ground.las 1 C:\FUSION\betera15.las
```

HERRAMIENTASÍ:
1. GroundFilter
Uso: Extraer puntos del terreno (bare-earth).
Sintaxis: C:\FUSION\GroundFilter [switches] outputfile cellsize datafile

2. GridSurfaceCreate
Uso: Crear Modelo Digital del Terreno (MDT/DTM).
Sintaxis: C:\FUSION\GridSurfaceCreate [switches] surfacefile cellsize xyunits zunits coordsys zone horizdatum vertdatum datafile

3. ClipData
Uso: Recortar un bounding box rectangular.
Sintaxis: C:\FUSION\ClipData [switches] InputSpecifier SampleFile MinX MinY MaxX MaxY

4. PolyClipData
Uso: Recortar usando un shapefile poligonal de máscara.
Sintaxis: C:\FUSION\PolyClipData [switches] PolyFile OutputFile InputDataFile

Si el usuario pide algo genérico y no tienes los parámetros, usa parámetros lógicos estándar de topografía.
"""

@app.get("/files/{filename}")
async def get_file(filename: str):
    path = os.path.join(fusion_dir, filename)
    if os.path.exists(path):
        return FileResponse(path)
    return {"error": "File not found"}


import json
import os

# Load the RAG DB once
fusion_db_path = os.path.join(os.path.dirname(__file__), "fusion_commands.json")
FUSION_DB = {}
if os.path.exists(fusion_db_path):
    with open(fusion_db_path, "r", encoding="utf-8") as f:
        FUSION_DB = json.load(f)

@app.post("/api/chat")
async def chat_endpoint(text: str = Form(...), model: str = Form("openai/gpt-oss-120b")):
    prompt_text = text
    
    # 1. THE LIBRARIAN AGENT (Router)
    # Ask the LLM to identify which FUSION commands are needed for this task.
    router_sys = (
        "You are an expert FUSION LiDAR routing agent. The available commands are: " + 
        ", ".join(list(FUSION_DB.keys())) + 
        "\nBased on the user's request, reply ONLY with a comma-separated list of the command names needed to solve it. (Hint: MDT/DTM = GridSurfaceCreate & GroundFilter). "
        "Do not include any other text. If no specific command is needed, reply with NONE."
    )
    
    try:
        router_chat = client.chat.completions.create(
            messages=[
                {"role": "system", "content": router_sys},
                {"role": "user", "content": prompt_text}
            ],
            model="openai/gpt-oss-120b", 
            temperature=0.0
        )
        commands_needed_str = router_chat.choices[0].message.content.strip()
    except Exception as e:
        commands_needed_str = "NONE"
        
    print(f"Router identified commands: {commands_needed_str}")
    
    # 2. RETRIEVE KNOWLEDGE
    rag_context = ""
    if commands_needed_str and commands_needed_str.upper() != "NONE":
        requested_cmds = [cmd.strip() for cmd in commands_needed_str.replace("`", "").split(",")]
        for cmd in requested_cmds:
            # Case insensitive match
            for db_cmd in FUSION_DB:
                if db_cmd.lower() == cmd.lower():
                    rag_context += f"\n\n=== OFFICIAL MANUAL FOR {db_cmd} ===\n{FUSION_DB[db_cmd]}\n"
                    break

    # 3. THE FOREMAN AGENT (Executor)
    # Overwrite the FUSION_CHEAT_SHEET with the dynamic RAG context
    dynamic_sys_prompt = (
        "ERES UN EXPERTO EN TOPOGRAFÍA Y FUSION-LTK.\n"
        "Tu objetivo es ayudar al usuario a procesar datos LiDAR. Puedes conversar en español.\n"
        "REGLAS ESTRICTAS DE SINTAXIS FUSION-LTK:\n"
        "- NO inventes archivos que no existan. Si el usuario no da nombre de archivo de entrada, usa el que haya: C:\\FUSION\\betera15.las\n"
        "- Los ejecutables están en C:\\FUSION\\\n"
        "- NUNCA uses LAStools ni herramientas externas (como las2txt). Usa SOLO los comandos nativos de FUSION.\n"
        "- Para crear un MDT / modelo de superficie a partir de un LAS, usa SIEMPRE GridSurfaceCreate.\n"
        "- CUANDO SUGIERAS UN COMANDO, DEBES ENVOLVERLO EN UN BLOQUE DE CÓDIGO BASH (```bash).\n"
        "- Si necesitas ejecutar VARIOS comandos para lograr el objetivo, ponlos TODOS JUNTOS EN UN ÚNICO BLOQUE DE CÓDIGO BASH (```bash), uno por línea. NO crees bloques separados, el usuario quiere automatización con un solo click.\n"
        "\n"
    )
    
    if rag_context:
        dynamic_sys_prompt += (
            "A CONTINUACIÓN TIENES EXTRACTOS DEL MANUAL OFICIAL DE FUSION PARA ESTA TAREA:\n"
            "LEELOS CUIDADOSAMENTE PARA NO INVENTARTE NINGÚN 'SWITCH' NI PARÁMETRO QUE NO EXISTA.\n"
            f"{rag_context}\n"
        )
    else:
        dynamic_sys_prompt += (
            "NO SE NECESITAN COMANDOS ESPECÍFICOS PARA ESTA TAREA, ACTÚA COMO UN ASISTENTE NORMAL.\n"
        )
        
    chat = client.chat.completions.create(
        messages=[{"role": "system", "content": dynamic_sys_prompt}, {"role": "user", "content": prompt_text}],
        model="openai/gpt-oss-120b", 
        temperature=0.3,
    )
    reply = chat.choices[0].message.content.strip()
    return {"transcription": prompt_text, "text": reply}


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    try:
        # Save temp file
        temp_path = f"/tmp/{audio.filename}"
        with open(temp_path, "wb") as buffer:
            buffer.write(await audio.read())
        
        # Transcribe with Groq Whisper
        with open(temp_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio.filename, file.read()),
                model="whisper-large-v3",
                prompt="El usuario está hablando sobre LiDAR y topografía en español.",
                response_format="json",
                language="es",
                temperature=0.0
            )
        
        os.remove(temp_path)
        return {"text": transcription.text}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/execute")
async def execute_command(command: str = Form(...)):
    import tempfile
    
    # Save the command to a bat file to handle multi-line and quotes correctly
    bat_filename = "temp_exec.bat"
    bat_path = os.path.join(fusion_dir, bat_filename)
    
    import re
    # Remove bash-style line continuations if the AI used them
    win_command = re.sub(r'\\\s*\n', ' ', command)
    # Ensure Windows CRLF line endings for the bat file
    win_command = win_command.strip().replace('\r', '').replace('\n', '\r\n')
    
    with open(bat_path, "w") as f:
        f.write(win_command)
        
    if is_windows:
        full_cmd = f'cd /d "{fusion_dir}" && {bat_filename}'
    else:
        full_cmd = f'cd {fusion_dir} && xvfb-run -a wine cmd /c {bat_filename}'
        
    start_time = time.time()
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        return {"status": "error", "logs": e.stdout + "\n" + e.stderr}
    
    new_files = []
    base_dir = fusion_dir
    for f in glob.glob(os.path.join(base_dir, "*")):
        if os.path.isfile(f) and os.path.getmtime(f) > start_time - 2:
            filename = os.path.basename(f)
            if filename.lower() == "betera15.las": continue
            
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            file_info = {"name": filename, "type": ext, "url": f"/files/{filename}"}
            
            if ext == "dtm":
                out_tif = f + ".tif"
                out_jpg = f + ".jpg"
                base_name = os.path.basename(f)
                base_tif = base_name + ".tif"
                if is_windows:
                    subprocess.run(f'C:\\FUSION\\DTM2TIF.exe "{base_name}" "{base_tif}"', shell=True, cwd=fusion_dir)
                    if os.path.exists(out_tif):
                        subprocess.run(f'python backend/tif_preview.py "{out_tif}" "{out_jpg}"', shell=True)
                else:
                    subprocess.run(f"xvfb-run -a wine DTM2TIF.exe '{base_name}' '{base_tif}'", shell=True, cwd=fusion_dir)
                    if os.path.exists(out_tif):
                        subprocess.run(f"/home/oscar/fusion_web/venv/bin/python3 /home/oscar/fusion_web/backend/tif_preview.py '{out_tif}' '{out_jpg}'", shell=True)
                if os.path.exists(out_jpg):
                    with open(out_jpg, "rb") as img_f:
                        file_info["preview_b64"] = base64.b64encode(img_f.read()).decode('utf-8')
                    os.remove(out_jpg)
                if os.path.exists(out_tif):
                    os.remove(out_tif)
            if ext in ["tif", "tiff"]:
                out_jpg = f + ".jpg"
                if is_windows:
                    subprocess.run(f'python backend/tif_preview.py "{f}" "{out_jpg}"', shell=True)
                else:
                    subprocess.run(f"/home/oscar/fusion_web/venv/bin/python3 /home/oscar/fusion_web/backend/tif_preview.py '{f}' '{out_jpg}'", shell=True)
                if os.path.exists(out_jpg):
                    with open(out_jpg, "rb") as img_f:
                        file_info["preview_b64"] = base64.b64encode(img_f.read()).decode('utf-8')
                    os.remove(out_jpg)
            if ext in ["las", "laz"]:
                out_jpg = f + ".jpg"
                # 1. Gen 2D Thumbnail
                if is_windows:
                    subprocess.run(f'python backend/las_preview.py "{f}" "{out_jpg}"', shell=True)
                else:
                    subprocess.run(f"/home/oscar/fusion_web/venv/bin/python3 /home/oscar/fusion_web/backend/las_preview.py '{f}' '{out_jpg}'", shell=True)
                if os.path.exists(out_jpg):
                    with open(out_jpg, "rb") as img_f:
                        file_info["preview_b64"] = base64.b64encode(img_f.read()).decode('utf-8')
                    os.remove(out_jpg)
                
                # 2. Gen Potree 3D
                potree_out = os.path.join(potree_dir, filename)
                if not os.path.exists(os.path.join(potree_out, "index.html")):
                    # Trigger PotreeConverter in background so it doesn't block
                    # For windows dev fallback it will just fail silently
                    if not is_windows:
                        subprocess.Popen(f"/home/oscar/PotreeConverter_2.1.2_x64_linux/PotreeConverter '{f}' -o '{potree_out}' --generate-page index", shell=True)
                
                # We assume it will exist soon or already exists
                file_info["html_3d_url"] = f"/potree/{filename}/index.html"
                    
            new_files.append(file_info)

    return {"status": "success", "logs": result.stdout + "\n" + result.stderr, "files": new_files}

@app.post("/api/upload")
async def upload_drive():
    try:
        subprocess.run("rclone copy ~/.wine/drive_c/FUSION/ GoogleDriveFusion:fusion_output --max-age 60m --exclude betera15.las", shell=True, check=True)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/webhook")
async def github_webhook():
    # Run the deploy script in the background
    subprocess.Popen(["bash", "/home/oscar/fusion_web/backend/deploy.sh"])
    return {"status": "deploying"}

if os.path.exists("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
