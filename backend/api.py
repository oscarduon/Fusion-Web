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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FUSION_CHEAT_SHEET = """
REGLAS ESTRICTAS DE FUSION-LTK:
- NO uses -i ni -o. Usa argumentos posicionales.
- Archivos en C:\\FUSION\\. Archivo por defecto: C:\\FUSION\\betera15.las
1. Catalog [switches] datafile
2. GroundFilter [switches] outputfile cellsize datafile
Responde ÚNICAMENTE con el comando en una línea, empezando por C:\\FUSION\\. No expliques nada.
"""

@app.get("/files/{filename}")
async def get_file(filename: str):
    path = os.path.expanduser(f"~/.wine/drive_c/FUSION/{filename}")
    if os.path.exists(path):
        return FileResponse(path)
    return {"error": "File not found"}

@app.post("/api/chat")
async def chat_endpoint(text: str = Form(...), model: str = Form("openai/gpt-oss-120b")):
    prompt_text = text
    sys_prompt = f"Eres un experto topógrafo. Lee esto: {FUSION_CHEAT_SHEET}\nDeduce el comando FUSION pedido. Responde SOLO con el comando crudo."
    chat = client.chat.completions.create(
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt_text}],
        model=model, temperature=0,
    )
    cmd = chat.choices[0].message.content.strip().replace("`", "")
    return {"transcription": prompt_text, "command": cmd}

@app.post("/api/execute")
async def execute_command(command: str = Form(...)):
    full_cmd = f'cd ~/.wine/drive_c/FUSION && xvfb-run wine cmd /c "{command}"'
    start_time = time.time()
    try:
        result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        return {"status": "error", "logs": e.stdout + "\n" + e.stderr}
    
    new_files = []
    base_dir = os.path.expanduser("~/.wine/drive_c/FUSION/")
    for f in glob.glob(os.path.join(base_dir, "*")):
        if os.path.isfile(f) and os.path.getmtime(f) > start_time - 2:
            filename = os.path.basename(f)
            if filename.lower() == "betera15.las": continue
            
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            file_info = {"name": filename, "type": ext, "url": f"/files/{filename}"}
            
            if ext in ["las", "laz"]:
                out_jpg = f + ".jpg"
                subprocess.run(f"/home/oscar/fusion_web/venv/bin/python3 /home/oscar/fusion_web/backend/las_preview.py '{f}' '{out_jpg}'", shell=True)
                if os.path.exists(out_jpg):
                    with open(out_jpg, "rb") as img_f:
                        file_info["preview_b64"] = base64.b64encode(img_f.read()).decode('utf-8')
                    os.remove(out_jpg)
                if os.path.exists(f + "_3d.html"):
                    file_info["html_3d_url"] = f"/files/{filename}_3d.html"
                    
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

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
