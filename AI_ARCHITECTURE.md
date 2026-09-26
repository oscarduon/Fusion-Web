# Arquitectura y Contexto del Proyecto: Fusion Web AI
**Documento de transferencia de conocimiento para humanos e IAs**

## 1. Visión General del Proyecto
Fusion Web es una plataforma web integral diseñada para ejecutar y automatizar flujos de trabajo de procesamiento de nubes de puntos LiDAR (archivos `.las`, `.laz`) y modelos digitales de terreno (`.dtm`, `.tif`) utilizando la suite de software **FUSION/LDV** del Servicio Forestal de los EE.UU.

El objetivo principal es proporcionar una interfaz web moderna (estilo IDE de programación) gobernada por una Inteligencia Artificial "Catedrático Experto". El usuario interactúa mediante lenguaje natural, y la IA diseña, razona y ejecuta los comandos de FUSION necesarios en el servidor de forma autónoma.

## 2. Stack Tecnológico
*   **Frontend**: React (Vite), TailwindCSS, Lucide-React (iconos).
*   **Backend**: FastAPI (Python), Uvicorn.
*   **Base de Datos / Almacenamiento**: Almacenamiento local temporal y `localStorage` (Pendiente integración de Firebase).
*   **Motor de IA**: Groq API (modelos como Llama-3-70B-Versatile).
*   **Ejecución LiDAR**: FUSION CLI original ejecutado a través de **WINE** (El servidor está en Linux, por lo que los `.exe` de FUSION se corren en Wine).

## 3. Arquitectura del Agente de IA (Plan-and-Solve RAG)
El sistema utiliza una arquitectura Multi-Agente para evitar "alucinaciones" y garantizar que los comandos de FUSION sean sintácticamente perfectos según el manual:

1.  **Agente Enrutador (Planificador)**: Cuando el usuario pide algo (ej. "Recomiéndame cómo limpiar este terreno"), este agente oculto evalúa el *prompt*. Su única misión es trazar un plan y devolver los NOMBRES EXACTOS de las herramientas de FUSION necesarias (ej. `GroundFilter`, `GridSurfaceCreate`).
2.  **Motor RAG (Retriever)**: Con los nombres devueltos por el Planificador, el servidor extrae del manual oficial de FUSION (almacenado en `backend/data/fusion_manual.txt`) las páginas exactas de documentación de esas herramientas.
3.  **Agente Foreman (IA Principal)**: Actúa como el Catedrático Experto. Recibe el *prompt* del usuario + la documentación estricta extraída en el paso anterior. Redacta la respuesta técnica y genera el código en un bloque ````bat`. 
    *   **Regla estricta**: Los comentarios en el bloque de código deben usar `REM` (estándar de Windows), NUNCA `#`, para evitar cuelgues del intérprete de CMD bajo Wine.

## 4. Pipeline de Ejecución de Comandos
El frontend lee el bloque ````bat` devuelto por la IA y lo envía al endpoint `/api/execute`.
*   **Envoltura `.bat`**: El servidor guarda los comandos en un archivo `.bat` temporal dentro del directorio de trabajo.
*   **Entorno Wine**: Se invoca con `xvfb-run -a wine cmd /c archivo.bat`.
*   **Rutas Relativas**: IMPORTANTE. FUSION bajo Wine se corrompe si recibe rutas absolutas de Linux (ej. `/home/oscar/...`). El backend utiliza el parámetro `cwd=fusion_dir` en el subproceso, y los comandos *siempre* se ejecutan referenciando solo los nombres de archivo en el directorio local.

## 5. Visualizadores (Renderizado)
El Frontend actúa como un IDE con un panel derecho que renderiza los resultados generados:
*   **Nubes de puntos (.las / .laz)**: Se detectan automáticamente. El backend ejecuta `PotreeConverter` bajo Linux para generar un visor web 3D. El frontend carga el resultado en un `<iframe src="/potree/index.html">`.
*   **Rasters 2D (.tif / .dtm / .img)**: Se usa `react-zoom-pan-pinch` y una etiqueta `<img>`. El backend tiene un motor de conversión automático `DTM2TIF` que convierte los `.dtm` (formato propietario de PLANS) a `.tif` estándar mediante Gdal/FUSION para que el navegador web pueda pintarlos en pantalla.
*   **Logs y TXT**: El frontend intercepta los archivos `.csv`, `.txt`, y `.log` y realiza un `fetch` directo para mostrarlos en el panel de texto en lugar de forzar una descarga molesta.

## 6. Estado Actual y Tareas Pendientes (Roadmap)
Cualquier IA que retome el proyecto a partir de este punto debe revisar estas tareas:

1.  **Integración de Firebase (Google Login)**: Reemplazar el `localStorage` actual por guardado en la nube (Cloud Firestore) para que los proyectos, historiales de chat y archivos persistan de forma segura por usuario.
2.  **Toggle Avanzado de Potree**: La generación del visor 3D Potree se dispara automáticamente cuando la IA genera un archivo `.las`. Para archivos enormes, esto consume demasiada RAM en el VPS. Se requiere un interruptor (Toggle) en la UI para que el usuario active/desactive la renderización 3D a voluntad.
3.  **Expansión del Conocimiento de IA**: Aunque la IA posee el manual oficial de 140 páginas, carece de intuición empírica avanzada (ej. ajustes GNSS, topografía con RTKLIB). Se planea inyectar más manuales universitarios en la base de datos RAG para ampliar la capacidad del Planificador.
4.  **Manejo de Errores Geográficos (Null Island)**: Históricamente, ArcGIS colocaba los `.tif` generados en África (coordenadas nulas 0,0) porque FUSION asumía "Zone 0". La IA ahora está entrenada para forzar Zonas UTM (ej. EPSG 25830).

## 7. Peculiaridades de la UI Frontend (Histórico de Bugs Resueltos)
*   **Scroll en el Chat**: Se intentaron varios métodos (flexbox + scrollTop, etc.). Finalmente, se resolvió aislando un botón fijo flotante a nivel `App.jsx` que manipula `document.getElementById('chat-scroll-container').scrollTop` a la fuerza bruta, y con un `IntersectionObserver` para ocultarlo automáticamente al llegar al fondo.
*   **Problemas de Caché**: El VPS está configurado con Nginx o FastAPI sirviendo estáticos muy agresivos. Para las actualizaciones de UI, el backend inyecta una cabecera HTTP `Cache-Control: no-store` al `index.html` para forzar a los navegadores a actualizar.

*FIN DEL DOCUMENTO. SI ERES UNA IA, USA ESTO COMO TU MEMORIA CENTRAL.*

## 8. Optimizaciones Responsivas y Mobile (Bugs Resueltos)
*   **Barra de Envío y Botón Flotante en Pantallas Estrechas (ej. Galaxy S10)**: El botón de enviar y el padding del contenedor inferior se desbordaban en dispositivos móviles con anchos inferiores a 360px. Se ajustó el espaciado usando clases de Tailwind (`p-2 md:p-6`, `right-4 md:right-8`) para garantizar que la UI se contraiga adecuadamente sin empujar elementos fuera del Viewport.

## 9. Decisiones de Arquitectura Abiertas (Debates de Diseño)
*   **Retención de Archivos (VPS Storage)**: Para evitar llenar los 100GB del disco del VPS, se implementará un `cronjob` (o lógica de base de datos) que elimine los archivos `.las` y rasters de la carpeta de trabajo del usuario tras **24 horas** de inactividad. Los chats y los metadatos de los proyectos se conservarán indefinidamente en Firebase, pero los binarios pesados serán efímeros.
*   **Alternativa a Leica Infinity (RTKLIB)**: Se ha decidido explorar RTKLIB en línea de comandos como alternativa a herramientas comerciales pesadas (Leica) para la compensación de redes GNSS. RTKLIB es ultra ligero y puede integrarse en el backend Python para ejecutarse de manera autónoma cuando el usuario suba logs de observación RINEX o NMEA.
