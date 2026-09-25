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
REGLAS ESTRICTAS DE SINTAXIS FUSION-LTK:
- NO inventes archivos que no existan. Si el usuario no da nombre de archivo de entrada, usa el que haya: C:\FUSION\betera15.las
- Los ejecutables están en C:\FUSION\
- La sintaxis NO usa -i ni -o, usa argumentos posicionales según el manual oficial.
- Responde ÚNICAMENTE con el comando en una línea. Nada de explicaciones ni comillas.

HERRAMIENTAS Y SINTAXIS:
1. GroundFilter
Uso: Extraer puntos del terreno (bare-earth).
Sintaxis: C:\FUSION\GroundFilter [switches] outputfile cellsize datafile
Ejemplo: C:\FUSION\GroundFilter C:\FUSION\ground.las 1 C:\FUSION\betera15.las

2. GridSurfaceCreate
Uso: Crear Modelo Digital del Terreno (MDT/DTM).
Sintaxis: C:\FUSION\GridSurfaceCreate [switches] surfacefile cellsize xyunits zunits coordsys zone horizdatum vertdatum datafile
Ejemplo: C:\FUSION\GridSurfaceCreate C:\FUSION\terreno.dtm 1 M M 0 0 0 0 C:\FUSION\ground.las

3. ClipData
Uso: Recortar un bounding box rectangular.
Sintaxis: C:\FUSION\ClipData [switches] InputSpecifier SampleFile MinX MinY MaxX MaxY
Ejemplo: C:\FUSION\ClipData C:\FUSION\betera15.las C:\FUSION\recorte.las 720000 4382000 721000 4383000

4. PolyClipData
Uso: Recortar usando un shapefile poligonal de máscara.
Sintaxis: C:\FUSION\PolyClipData [switches] PolyFile OutputFile InputDataFile
Ejemplo: C:\FUSION\PolyClipData C:\FUSION\mascara.shp C:\FUSION\recorte_poly.las C:\FUSION\betera15.las

Si el usuario pide algo genérico y no tienes los parámetros, usa parámetros lógicos estándar de topografía.
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
                # 1. Gen 2D Thumbnail
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

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
