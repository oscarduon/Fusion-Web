# Fusion-Web

Aplicación web para ejecutar flujos de trabajo de **FUSION-LTK** sobre archivos LiDAR y visualizar resultados en 2D/3D desde una interfaz moderna.

## Estructura del repositorio

```text
Fusion-Web/
├── backend/
│   ├── api.py
│   ├── las_preview.py
│   └── deploy.sh
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── main.jsx
    │   └── index.css
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── postcss.config.js
```

## Tecnologías clave

### Frontend
- **React 18**: interfaz principal y gestión de estado.
- **Vite**: entorno de desarrollo y build.
- **Tailwind CSS**: estilos utilitarios.
- **lucide-react**: iconografía.

### Backend
- **FastAPI**: API HTTP.
- **Groq API**: generación de comandos de FUSION a partir de texto.
- **Wine + xvfb-run**: ejecución de comandos de FUSION en entorno Linux.
- **laspy + numpy + matplotlib + plotly**: procesamiento y previsualización de nubes de puntos LAS/LAZ.
- **rclone**: subida de outputs a Google Drive.

## Organización del código

### 1) Frontend (`frontend/src`)

### `App.jsx` (archivo principal)
Contiene casi toda la aplicación:
- Layout responsive (desktop con panel redimensionable y mobile con tabs).
- “Proyectos/sesiones” guardados en `localStorage`.
- Chat para enviar prompts al backend (`/api/chat`).
- Ejecución de comandos (`/api/execute`) y consola de logs.
- Visor de archivos generados:
  - Imagen 2D embebida en base64 para LAS/LAZ.
  - Vista 3D vía HTML (`iframe`) cuando existe.
  - Visor de texto plano para CSV/TXT/LOG.
- Acciones de sesión (renombrar, fijar, borrar, nueva sesión).

### `main.jsx`
Punto de entrada de React.

### `index.css`
Carga de capas Tailwind y estilos base globales.

### 2) Backend (`backend`)

### `api.py` (servicio principal)
Expone endpoints:
- `POST /api/chat`: recibe texto y devuelve comando FUSION sugerido por el modelo.
- `POST /api/execute`: ejecuta comando en `~/.wine/drive_c/FUSION`, captura logs y detecta archivos nuevos.
- `GET /files/{filename}`: sirve archivos generados.
- `POST /api/upload`: sube outputs recientes a Google Drive usando rclone.
- `POST /api/webhook`: dispara `deploy.sh`.

También:
- Habilita CORS abierto.
- Sirve frontend compilado desde `frontend/dist` (SPA estática).

### `las_preview.py`
Genera previsualizaciones para LAS/LAZ:
- Render 2D en JPG (matplotlib).
- Render 3D interactivo en HTML (plotly).
- Muestreo de puntos para mantener rendimiento.

### `deploy.sh`
Script de despliegue simple:
- `git pull`
- `npm install`
- `npm run build`

## Flujo funcional (alto nivel)

1. Usuario escribe instrucción en el chat.
2. Frontend envía texto a `/api/chat`.
3. Backend usa Groq para convertir texto en comando FUSION.
4. Frontend ejecuta el comando vía `/api/execute`.
5. Backend corre FUSION (Wine), captura salida y escanea nuevos archivos.
6. Si hay LAS/LAZ, backend genera preview 2D/3D.
7. Frontend muestra logs, archivos y visor multimedia.

## Configuración esperada del entorno

El código asume que existen:
- Carpeta de trabajo FUSION en `~/.wine/drive_c/FUSION/`.
- Variable `GROQ_API_KEY`.
- Dependencias del backend (FastAPI, groq, laspy, numpy, matplotlib, plotly, python-dotenv, etc.).
- Herramientas del sistema: `wine`, `xvfb-run`, `rclone`.

## Scripts disponibles (frontend)

Desde `frontend/`:
- `npm run dev` → desarrollo con Vite.
- `npm run build` → build de producción.
- `npm run preview` → previsualizar build.
## Arquitectura 2.0 (Consultor + Potree)

### 1) Motor 3D - Potree
Las visualizaciones 3D en HTML (Plotly) se sustituyeron por **Potree** para poder manejar nubes de puntos enormes (ej. 3 a 100 millones de puntos) sin colapsar el navegador.
- El servidor Ubuntu tiene instalado PotreeConverter (versión binaria).
- En pi.py, cada vez que se genera un archivo .las válido, se ejecuta:
  PotreeConverter archivo.las -o carpeta_potree --generate-page index
- La web carga el Octree altamente comprimido y optimizado dentro de un iframe en App.jsx, permitiendo medir, recortar y analizar con herramientas nativas profesionales.

### 2) Modo Consultor (Chat conversacional)
En lugar de auto-ejecutar scripts a ciegas:
- El System Prompt (Chuleta) de Groq está configurado como un experto en LiDAR y FUSION.
- La IA puede charlar con el usuario, darle contexto y planificar comandos.
- Si la IA sugiere ejecutar algo, lo envuelve en un bloque Markdown.
- El frontend React (App.jsx) lee los bloques de código y pinta un botón de **[ ▶ Ejecutar Comando ]**. De esta manera el usuario tiene la última palabra.
