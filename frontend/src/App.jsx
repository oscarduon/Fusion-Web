import React, { useState, useEffect, useRef } from 'react';
import { ArrowDown, Menu, Terminal, MessageSquare, Send, X, HardDrive, FileText, Download, Play, ChevronUp, ChevronDown, Check, AlertTriangle, Plus, History, Map, MoreVertical, Edit2, Trash2, Pin, PinOff, Mic, MicOff, LogOut, Cloud } from 'lucide-react';
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

const MODEL_CATEGORIES = [
  {
    category: "Groq (Cerebro Rápido)",
    models: [
      { id: 'llama-3.1-70b-versatile', name: 'Llama 3.1 70B', status: 'ok' },
      { id: 'gemma2-9b-it', name: 'Gemma 2 9B (Google)', status: 'ok' }
    ]
  },
  {
    category: "DeepSeek (Cerebro Analítico Profundo)",
    models: [
      { id: 'deepseek-chat', name: 'DeepSeek V3 (Chat)', status: 'ok' },
      { id: 'deepseek-coder', name: 'DeepSeek Coder V2', status: 'ok' }
    ]
  },
  {
    category: "Modelos Privados",
    models: [
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro (Próximamente)', disabled: true }
    ]
  }
];

const generateId = () => Math.random().toString(36).substr(2, 9) + Date.now().toString(36).slice(-4);

export default function App() {
  // ---- auth state ----
  const [user, setUser] = useState(null);
  const [googleClientId, setGoogleClientId] = useState('');
  const [authRequired, setAuthRequired] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [guestMode, setGuestMode] = useState(false);
  const [driveOwner, setDriveOwner] = useState(false);
  const tokenRef = useRef(localStorage.getItem('fusion_token') || '');

  const apiFetch = (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (tokenRef.current) headers['Authorization'] = `Bearer ${tokenRef.current}`;
    if (options.body && !(options.body instanceof FormData) && typeof options.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    return fetch(url, { ...options, headers });
  };

  // ---- auth boot ----
  useEffect(() => {
    (async () => {
      try {
        const cfg = await fetch('/api/config').then(r => r.json());
        setGoogleClientId(cfg.google_client_id || '');
        setAuthRequired(!!cfg.auth_required);
      } catch (e) { /* ignore */ }

      if (tokenRef.current) {
        try {
          const r = await apiFetch('/api/auth/me');
          const d = await r.json();
          if (d.user) {
            setUser(d.user);
            const ds = await apiFetch('/api/drive/status').then(r => r.json()).catch(() => ({}));
            setDriveOwner(!!ds.owner);
          } else {
            localStorage.removeItem('fusion_token');
            tokenRef.current = '';
          }
        } catch (e) { /* ignore */ }
      }
      setAuthChecked(true);
    })();
  }, []);

  // ---- Google Identity Services ----
  useEffect(() => {
    if (!googleClientId || user || guestMode) return;
    const init = () => {
      if (window.google && window.google.accounts && !window.__gisInit) {
        window.__gisInit = true;
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleGoogleCredential,
          auto_select: false,
        });
      }
    };
    init();
    const tries = setInterval(() => { if (window.google) { init(); clearInterval(tries); } }, 300);
    return () => clearInterval(tries);
  }, [googleClientId, user, guestMode]);

  const handleGoogleCredential = async (response) => {
    if (!response || !response.credential) return;
    try {
      const r = await fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential }),
      });
      const d = await r.json();
      if (d.token && d.user) {
        tokenRef.current = d.token;
        localStorage.setItem('fusion_token', d.token);
        setUser(d.user);
        const ds = await apiFetch('/api/drive/status').then(r => r.json()).catch(() => ({}));
        setDriveOwner(!!ds.owner);
        // load server projects
        const pr = await apiFetch('/api/projects').then(r => r.json()).catch(() => ({ projects: [] }));
        setProjects(pr.projects || []);
        localStorage.removeItem('react_projects');
      } else {
        alert(d.detail || 'No se pudo iniciar sesión con Google.');
      }
    } catch (e) {
      alert('Error de red al iniciar sesión.');
    }
  };

  const handleLoginClick = () => {
    if (window.google && window.google.accounts) {
      window.google.accounts.id.prompt();
    }
  };

  const handleLogout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    tokenRef.current = '';
    localStorage.removeItem('fusion_token');
    setUser(null);
    setProjects([]);
    setCurrentProjectId(null);
  };

  // ---- app state ----
  const [activeTab, setActiveTab] = useState('chat');
  const [isRecording, setIsRecording] = useState(false);
  const [autoExecute, setAutoExecute] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const toggleRecording = async () => {
    if (isRecording) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') mediaRecorderRef.current.stop();
      setIsRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio', audioBlob, 'voice.webm');
        const originalText = inputText;
        setInputText(prev => prev + (prev ? ' ' : '') + '...');
        try {
          const res = await apiFetch('/api/transcribe', { method: 'POST', body: formData });
          const data = await res.json();
          if (data.text) setInputText(originalText + (originalText ? ' ' : '') + data.text);
          else setInputText(originalText);
        } catch (e) {
          setInputText(originalText);
        }
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      alert("No se pudo acceder al micrófono. Da permisos al navegador.");
    }
  };

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputText, setInputText] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [selectedModel, setSelectedModel] = useState(MODEL_CATEGORIES[1].models[0]); // default DeepSeek (works)
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);

  const [projects, setProjects] = useState(() => {
    try {
      const saved = localStorage.getItem('react_projects');
      if (saved) return JSON.parse(saved);
      const legacyChat = JSON.parse(localStorage.getItem('react_chat') || '[]');
      if (legacyChat.length > 0) {
        return [{
          id: generateId(), name: 'Sesión anterior', isPinned: false, updatedAt: Date.now(),
          chatHistory: legacyChat,
          ideLogs: localStorage.getItem('react_logs') || 'Esperando comandos...',
          visorFiles: JSON.parse(localStorage.getItem('react_files') || '[]')
        }];
      }
    } catch (e) { /* ignore */ }
    return [];
  });
  const [currentProjectId, setCurrentProjectId] = useState(() => localStorage.getItem('react_current_project') || null);
  const [selectedMedia, setSelectedMedia] = useState(null);
  const [is3DMode, setIs3DMode] = useState(false);
  const [textContent, setTextContent] = useState(null);
  const [showConsole, setShowConsole] = useState(true);
  const [showDriveMenu, setShowDriveMenu] = useState(false);
  const [menuOpenProjectId, setMenuOpenProjectId] = useState(null);
  const [chatWidth, setChatWidth] = useState(600);
  const isDragging = useRef(false);

  const currentProject = projects.find(p => p.id === currentProjectId) || { chatHistory: [], ideLogs: 'Esperando comandos...', visorFiles: [] };
  const chatHistory = currentProject.chatHistory || [];
  const ideLogs = currentProject.ideLogs || 'Esperando comandos...';
  const visorFiles = currentProject.visorFiles || [];

  const chatEndRef = useRef(null);
  const chatContainerRef = useRef(null);

  // ---- persistence (guest -> localStorage, authed -> server) ----
  const syncTimer = useRef(null);
  useEffect(() => {
    if (!user) {
      // guest: localStorage
      localStorage.setItem('react_projects', JSON.stringify(projects));
      if (currentProjectId) localStorage.setItem('react_current_project', currentProjectId);
      else localStorage.removeItem('react_current_project');
      return;
    }
    // authed: debounced server sync
    if (syncTimer.current) clearTimeout(syncTimer.current);
    syncTimer.current = setTimeout(async () => {
      for (const p of projects) {
        const payload = {
          id: p.id, name: p.name, is_pinned: !!p.isPinned, updated_at: p.updatedAt,
          chat_history: p.chatHistory || [], ide_logs: p.ideLogs || ''
        };
        await apiFetch('/api/projects', { method: 'POST', body: payload }).catch(() => {});
      }
    }, 900);
    return () => { if (syncTimer.current) clearTimeout(syncTimer.current); };
  }, [projects, user, currentProjectId]);

  useEffect(() => {
    if (window.innerWidth >= 768) setSidebarOpen(true);
  }, []);

  useEffect(() => {
    setTimeout(() => {
      const container = document.getElementById('chat-scroll-container');
      if (container) container.scrollTop = container.scrollHeight + 5000;
      const endRef = document.getElementById('chat-end-marker');
      if (endRef) endRef.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, 100);
  }, [chatHistory, activeTab, isTyping]);

  useEffect(() => {
    const handleClick = () => setMenuOpenProjectId(null);
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, []);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === 'Escape') { setSelectedMedia(null); setIs3DMode(false); } };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, []);

  useEffect(() => {
    if (selectedMedia && !selectedMedia.preview_b64 && selectedMedia.type !== 'html') {
      const ext = (selectedMedia.type || '').toLowerCase();
      const binaryExts = ['tif', 'tiff', 'las', 'laz', 'shp', 'shx', 'dbf', 'prj', 'exe', 'dll', 'dtm', 'img', 'tfw'];
      if (binaryExts.includes(ext)) {
        setTextContent(`[ Archivo Binario: ${selectedMedia.name} ]\n\nEste tipo de archivo no se puede previsualizar en texto.\nUsa el botón de descarga para abrirlo en QGIS o herramientas similares.`);
        return;
      }
      setTextContent('Cargando datos del archivo...');
      fetch(selectedMedia.url)
        .then(res => { if (!res.ok) throw new Error('Network response was not ok'); return res.text(); })
        .then(text => setTextContent(text))
        .catch(err => setTextContent(`Error al cargar el archivo: ${err.message}`));
    } else {
      setTextContent(null);
    }
  }, [selectedMedia]);

  const updateCurrentProject = (updates) => {
    setProjects(prev => prev.map(p => p.id === currentProjectId ? { ...p, ...updates, updatedAt: Date.now() } : p));
  };

  const handleNewSession = () => {
    setCurrentProjectId(null);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleDeleteProject = async (id, e) => {
    e.stopPropagation();
    setProjects(prev => prev.filter(p => p.id !== id));
    if (currentProjectId === id) setCurrentProjectId(null);
    setMenuOpenProjectId(null);
    if (user) await apiFetch(`/api/projects/${id}`, { method: 'DELETE' }).catch(() => {});
  };

  const handleRenameProject = (id, e) => {
    e.stopPropagation();
    const p = projects.find(x => x.id === id);
    const newName = prompt("Nuevo nombre para el proyecto:", p.name);
    if (newName && newName.trim()) setProjects(prev => prev.map(x => x.id === id ? { ...x, name: newName.trim() } : x));
    setMenuOpenProjectId(null);
  };

  const handleTogglePin = (id, e) => {
    e.stopPropagation();
    setProjects(prev => prev.map(x => x.id === id ? { ...x, isPinned: !x.isPinned } : x));
    setMenuOpenProjectId(null);
  };

  const executeCommand = async (cmd, targetProjectId) => {
    setProjects(prev => prev.map(p => {
      if (p.id === targetProjectId) {
        const newLogs = (p.ideLogs + `\n\n--- Ejecutando ---\n${cmd}\nProcesando...`).split('\n').slice(-100).join('\n');
        return { ...p, ideLogs: newLogs, visorFiles: [{ status: 'loading' }] };
      }
      return p;
    }));
    try {
      const execData = new FormData();
      execData.append('command', cmd);
      const execRes = await apiFetch('/api/execute', { method: 'POST', body: execData });
      const execResult = await execRes.json();
      setProjects(prev => prev.map(p => {
        if (p.id === targetProjectId) {
          const resultLogs = execResult.logs || 'Sin salida de consola.';
          const newLogs = (p.ideLogs + '\n' + resultLogs).split('\n').slice(-100).join('\n');
          return { ...p, ideLogs: newLogs, visorFiles: execResult.files || [] };
        }
        return p;
      }));
    } catch (e) {
      setProjects(prev => prev.map(p => {
        if (p.id === targetProjectId) {
          const newLogs = (p.ideLogs + `\nError de red: ${e}`).split('\n').slice(-100).join('\n');
          return { ...p, ideLogs: newLogs };
        }
        return p;
      }));
    }
  };

  const handleSend = async () => {
    if (!inputText.trim()) return;
    const txt = inputText.trim();
    let targetProjectId = currentProjectId;

    if (!targetProjectId) {
      targetProjectId = generateId();
      const newProj = {
        id: targetProjectId, name: txt.slice(0, 20) + (txt.length > 20 ? '...' : ''),
        isPinned: false, updatedAt: Date.now(), chatHistory: [{ text: txt, isUser: true }],
        ideLogs: 'Esperando comandos...', visorFiles: []
      };
      setProjects(prev => [newProj, ...prev]);
      setCurrentProjectId(targetProjectId);
    } else {
      setProjects(prev => prev.map(p => p.id === targetProjectId ? { ...p, chatHistory: [...p.chatHistory, { text: txt, isUser: true }], updatedAt: Date.now() } : p));
    }

    setInputText('');
    setIsTyping(true);

    try {
      const formData = new FormData();
      formData.append('text', txt);
      formData.append('model', selectedModel.id);
      const chatRes = await apiFetch('/api/chat', { method: 'POST', body: formData });
      const chatData = await chatRes.json();
      const aiText = chatData.text || chatData.command || "Error: No se recibió respuesta del agente.";

      setProjects(prev => prev.map(p => p.id === targetProjectId ? { ...p, chatHistory: [...p.chatHistory, { text: aiText, isUser: false, modelName: selectedModel.name }] } : p));

      if (autoExecute) {
        const parts = (aiText || "").split(/(```[\s\S]*?```)/g);
        for (const part of parts) {
          if (part.startsWith('```')) {
            const code = part.replace(/```[a-zA-Z]*\n?/i, '').replace(/```$/, '').trim();
            if (code) await executeCommand(code, targetProjectId);
          }
        }
      }
    } catch (e) {
      setProjects(prev => prev.map(p => p.id === targetProjectId ? { ...p, chatHistory: [...p.chatHistory, { text: `Error: ${e}`, isUser: false }] } : p));
    } finally {
      setIsTyping(false);
    }
  };

  const handleDriveUpload = async () => {
    setShowDriveMenu(false);
    updateCurrentProject({ ideLogs: ideLogs + '\n\nSubiendo a Google Drive...' });
    try {
      if (driveOwner) {
        const res = await apiFetch('/api/drive/upload', { method: 'POST', body: {} });
        const data = await res.json();
        updateCurrentProject({ ideLogs: ideLogs + (data.status === 'success' ? '\n✅ ¡Subida completada!' : '\n❌ Error al subir.') });
      } else {
        // non-owner: request a Drive access token via Google OAuth2 token client
        if (!window.google || !window.google.accounts || !window.google.accounts.oauth2) {
          updateCurrentProject({ ideLogs: ideLogs + '\n❌ No se pudo conectar con Google.' });
          return;
        }
        const tokenClient = window.google.accounts.oauth2.initTokenClient({
          client_id: googleClientId,
          scope: 'https://www.googleapis.com/auth/drive.file',
          callback: async (resp) => {
            if (resp.access_token) {
              const res = await apiFetch('/api/drive/upload', { method: 'POST', body: { access_token: resp.access_token } });
              const data = await res.json();
              updateCurrentProject({ ideLogs: ideLogs + (data.status === 'success' ? '\n✅ ¡Subida a tu Drive completada!' : '\n❌ Error al subir.') });
            } else {
              updateCurrentProject({ ideLogs: ideLogs + '\n❌ Permiso de Drive denegado.' });
            }
          },
        });
        tokenClient.requestAccessToken();
      }
    } catch (e) {
      updateCurrentProject({ ideLogs: ideLogs + '\n❌ Error de red.' });
    }
  };

  const sortedProjects = [...projects].sort((a, b) => {
    if (a.isPinned === b.isPinned) return (b.updatedAt || 0) - (a.updatedAt || 0);
    return a.isPinned ? -1 : 1;
  });

  const firstName = user ? (user.name || '').split(' ')[0] : '';

  const ModelSelectorButton = ({ mobile = false }) => (
    <div className={`relative ${mobile ? 'flex justify-center flex-1' : ''}`} onClick={(e) => e.stopPropagation()}>
      <button onClick={() => setIsModelSelectorOpen(!isModelSelectorOpen)} className={`flex items-center gap-2 bg-transparent hover:bg-neutral-800/50 px-3 py-1.5 rounded-xl text-sm font-medium transition ${mobile ? 'text-neutral-200' : 'text-neutral-300 border border-neutral-800 bg-neutral-900/80 backdrop-blur-md shadow-sm'}`}>
        {selectedModel.name} <ChevronDown size={14} className="text-neutral-500"/>
      </button>
      {isModelSelectorOpen && (
        <div className={`absolute top-full mt-2 ${mobile ? 'left-1/2 -translate-x-1/2' : 'right-0'} w-64 bg-neutral-900 border border-neutral-800 rounded-2xl shadow-2xl overflow-hidden z-[60]`}>
          <div className="py-2 max-h-80 overflow-y-auto hide-scrollbar">
            {MODEL_CATEGORIES.map((cat, i) => (
              <div key={i}>
                <div className="px-4 py-1.5 text-[10px] font-bold text-neutral-500 uppercase tracking-wider">{cat.category}</div>
                {cat.models.map(m => (
                  <button key={m.id} onClick={() => { if(!m.disabled) { setSelectedModel(m); setIsModelSelectorOpen(false); } }} className={`w-full flex items-center justify-between px-4 py-2.5 hover:bg-neutral-800 transition text-left ${m.disabled ? 'opacity-40 cursor-not-allowed' : ''}`} disabled={m.disabled}>
                    <span className="text-sm font-medium text-neutral-200">{m.name}</span>
                    {selectedModel.id === m.id && <Check size={14} className="text-white"/>}
                  </button>
                ))}
                {i < MODEL_CATEGORIES.length - 1 && <div className="h-px bg-neutral-800 mx-2 my-1"></div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const renderChatMessage = (msg, i) => {
    if (msg.isUser) {
      return <div key={i} className="max-w-[85%] p-4 rounded-2xl whitespace-pre-wrap shadow-sm text-[15px] leading-relaxed self-end bg-blue-600 text-white ml-auto">{msg.text}</div>;
    }
    const parts = msg.text.split(/(```[\s\S]*?```)/g);
    return (
      <div key={i} className="max-w-[85%] p-4 rounded-2xl shadow-sm text-[15px] leading-relaxed self-start bg-neutral-900 border border-neutral-800 text-neutral-100 flex flex-col gap-3">
        {msg.modelName && <div className="text-[10px] font-bold text-neutral-500 uppercase tracking-wider mb-1">{msg.modelName}</div>}
        {parts.map((part, idx) => {
          if (part.startsWith('```')) {
            const code = part.replace(/```[a-z]*\n?/i, '').replace(/```$/, '').trim();
            return (
              <div key={idx} className="bg-black border border-neutral-700 rounded-xl overflow-hidden flex flex-col">
                <div className="bg-neutral-800 px-3 py-1.5 flex justify-between items-center border-b border-neutral-700">
                  <span className="text-xs font-mono text-neutral-400">Comando sugerido</span>
                </div>
                <pre className="p-3 text-xs font-mono text-green-400 overflow-x-auto whitespace-pre-wrap">{code}</pre>
                <div className="p-2 border-t border-neutral-800 bg-neutral-950 flex justify-end">
                  <button onClick={() => executeCommand(code, currentProjectId)} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-full shadow-lg flex items-center gap-2 transition"><Play size={14} /> Ejecutar Comando</button>
                </div>
              </div>
            );
          }
          return <span key={idx} className="whitespace-pre-wrap">{part}</span>;
        })}
      </div>
    );
  };

  const ChatContent = (
    <div className="flex flex-col h-full relative bg-neutral-950">
      <header className="hidden md:flex absolute top-0 left-0 right-0 p-4 justify-between items-center z-20 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-2">
          {!sidebarOpen && (
            <button onClick={() => setSidebarOpen(true)} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-full transition"><Menu size={24} /></button>
          )}
        </div>
        <div className="pointer-events-auto flex items-center gap-2">
          {user && (
            <div className="flex items-center gap-2 bg-neutral-900/80 border border-neutral-800 rounded-full pl-1 pr-3 py-1 backdrop-blur-md">
              {user.picture ? <img src={user.picture} className="w-7 h-7 rounded-full" alt="" /> : <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">{firstName[0] || 'U'}</div>}
              <span className="text-sm text-neutral-200">{firstName}</span>
              <button onClick={handleLogout} className="text-neutral-500 hover:text-white" title="Cerrar sesión"><LogOut size={15} /></button>
            </div>
          )}
          <ModelSelectorButton />
        </div>
      </header>

      <header className="md:hidden w-full p-3 flex items-center justify-between shrink-0 bg-neutral-950 z-20 border-b border-neutral-900">
        <button onClick={() => setSidebarOpen(true)} className="p-2 text-neutral-300 hover:text-white"><Menu size={24} /></button>
        <div className="flex-1 flex justify-center"><ModelSelectorButton mobile={true} /></div>
        {user ? (
          <button onClick={handleLogout} className="p-2 text-neutral-400 hover:text-white" title="Cerrar sesión"><LogOut size={20} /></button>
        ) : <div className="w-10"></div>}
      </header>

      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 hide-scrollbar flex flex-col min-h-0 pt-16 md:pt-20 relative" ref={chatContainerRef} id="chat-scroll-container" onScroll={(e) => setShowScrollButton(e.target.scrollHeight - e.target.scrollTop - e.target.clientHeight > 50)}>
        {chatHistory.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-neutral-500 space-y-6">
            <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-2xl opacity-80"><Map size={32} /></div>
            <h2 className="text-2xl font-semibold text-neutral-300 text-center max-w-sm leading-tight">
              {currentProjectId ? currentProject.name : (user ? `Manos a la obra, ${firstName}` : 'Ahora tú, Asgeirr')}
            </h2>
            {!currentProjectId && <p className="text-sm">Envía un comando para empezar.</p>}
          </div>
        )}
        {chatHistory.map((msg, i) => renderChatMessage(msg, i))}
        {isTyping && (
          <div className="max-w-[85%] p-4 rounded-2xl shadow-sm text-[15px] leading-relaxed self-start bg-neutral-900 border border-neutral-800 text-neutral-300 mr-auto flex items-center gap-4">
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
              <div className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
            </div>
            <span className="text-sm font-medium bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent animate-pulse">Procesando con {selectedModel?.name || 'IA'}...</span>
          </div>
        )}
        <div ref={chatEndRef} id="chat-end-marker" className="h-4 shrink-0" />
      </div>

      {showScrollButton && (
        <button onClick={() => {
          const container = document.getElementById('chat-scroll-container');
          if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'auto' });
          const endRef = document.getElementById('chat-end-marker');
          if (endRef) endRef.scrollIntoView({ behavior: 'auto', block: 'end' });
          window.scrollTo(0, document.body.scrollHeight);
        }} className="absolute bottom-24 right-4 md:bottom-28 md:right-8 bg-blue-600 hover:bg-blue-500 text-white rounded-full p-3 shadow-2xl transition-all z-[50] flex items-center justify-center animate-bounce border border-blue-400" title="Bajar al final"><ArrowDown size={24} /></button>
      )}

      <div className="shrink-0 p-2 md:p-6 bg-neutral-950 flex justify-center z-10 border-t border-neutral-900/50 relative">
        <div className="w-full max-w-3xl flex flex-col gap-2 relative">
          <div className="flex items-end bg-[#1e1e1f] p-1.5 md:p-2 rounded-[32px] shadow-2xl focus-within:bg-[#252526] transition-all border border-neutral-800">
            <button className="p-3 text-neutral-400 hover:text-white rounded-full transition-colors shrink-0"><Plus size={20} /></button>
            <input type="text" value={inputText} onChange={e => setInputText(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()} placeholder="Pregunta a LiDAR..." className="flex-1 bg-transparent px-2 py-3.5 text-[15px] text-white focus:outline-none placeholder-neutral-500" />
            <button onClick={toggleRecording} className={`p-3 rounded-full shadow-md transition-transform active:scale-95 shrink-0 ml-2 ${isRecording ? 'bg-red-500 hover:bg-red-600 animate-pulse text-white' : 'bg-neutral-800 hover:bg-neutral-700 text-neutral-400'}`} title="Dictar por voz">{isRecording ? <MicOff size={18} /> : <Mic size={18} />}</button>
            <button onClick={handleSend} className="p-3 bg-blue-600 hover:bg-blue-500 text-white rounded-full shadow-md transition-transform active:scale-95 shrink-0 ml-2"><Send size={18} /></button>
          </div>
          <p className="text-center text-[10px] text-neutral-600 mt-2 hidden md:block">La IA puede cometer errores topográficos. Verifica los datos generados.</p>
        </div>
      </div>
    </div>
  );

  const IdeContent = (
    <div className="flex flex-col h-full bg-neutral-900 overflow-hidden">
      <div className="flex-1 min-h-0 bg-black relative border-b border-neutral-800 p-4 overflow-y-auto flex flex-col gap-4">
        {visorFiles.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-neutral-600 font-mono text-xs">(No hay archivos recientes)</div>
        ) : visorFiles[0].status === 'loading' ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-blue-500 font-mono text-xs space-y-4">
            <div className="w-8 h-8 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
            <span>Escaneando y renderizando...</span>
          </div>
        ) : (
          visorFiles.map((file, i) => (
            <div key={i} className="bg-neutral-900 border border-neutral-800 rounded-2xl p-4 flex flex-col gap-3 shadow-lg">
              <div className="flex justify-between items-center">
                <span className="font-bold text-sm text-neutral-200 truncate pr-4 flex items-center gap-2">
                  {file.type === 'las' || file.type === 'laz' ? <Play size={16} className="text-green-400"/> : file.type === 'html' ? <FileText size={16} className="text-blue-400"/> : <Download size={16} className="text-neutral-400"/>}
                  {file.name}
                </span>
                <button onClick={() => setSelectedMedia(file)} className="px-4 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition shadow-sm bg-neutral-700 hover:bg-neutral-600 text-white">Abrir Visor</button>
              </div>
              {(file.type === 'las' || file.type === 'laz') && file.preview_b64 && (
                <div onClick={() => setSelectedMedia(file)} className="rounded-xl overflow-hidden border border-neutral-700 mt-2 bg-black flex justify-center p-2 cursor-pointer hover:border-neutral-500 transition-colors group relative">
                  <img src={`data:image/png;base64,${file.preview_b64}`} className="max-w-full max-h-64 object-contain rounded-lg group-hover:opacity-80 transition-opacity" alt="Point Cloud Render" />
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="bg-black/60 text-white px-3 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 backdrop-blur-sm"><Play size={14}/> Ampliar</div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className={`flex flex-col bg-neutral-900 border-t border-neutral-800 transition-all duration-300 ${showConsole ? 'flex-[0.8] min-h-[150px]' : 'flex-none h-[52px] overflow-hidden'}`}>
        <div className="flex items-center justify-between p-3.5 shrink-0 cursor-pointer select-none hover:bg-neutral-800 transition" onClick={() => setShowConsole(!showConsole)}>
          <h3 className="text-xs font-bold tracking-wider text-neutral-500 uppercase flex items-center gap-2"><Terminal size={14}/> Consola de Wine</h3>
          <div className="flex items-center gap-3">
            <div className="relative" onClick={(e) => e.stopPropagation()}>
              <button onClick={() => setShowDriveMenu(!showDriveMenu)} className="w-8 h-8 bg-neutral-800 text-white rounded-full flex items-center justify-center hover:bg-neutral-700 transition shadow-sm border border-neutral-700" title="Opciones de Drive"><HardDrive size={14}/></button>
              {showDriveMenu && (
                <div className="absolute bottom-full right-0 mb-2 w-56 bg-neutral-800 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden z-50 py-1">
                  <button onClick={handleDriveUpload} className="w-full px-3 py-2 text-left text-sm text-neutral-200 hover:bg-neutral-700 flex items-center gap-2">
                    <Cloud size={14} /> {driveOwner ? 'Subir a mi Drive' : 'Guardar en tu Drive'}
                  </button>
                </div>
              )}
            </div>
            <button className="text-neutral-400 hover:text-white p-1 rounded-md hover:bg-neutral-700">{showConsole ? <ChevronDown size={16}/> : <ChevronUp size={16}/>}</button>
          </div>
        </div>
        {showConsole && (
          <div className="flex-1 min-h-0 bg-black border border-neutral-800 rounded-2xl mx-4 mb-4 p-4 text-[11px] font-mono text-green-400 overflow-y-auto whitespace-pre-wrap shadow-inner leading-relaxed">{ideLogs}</div>
        )}
      </div>
    </div>
  );

  const renderProjectItem = (p) => (
    <div key={p.id} className="relative group mt-1">
      <button onClick={() => { setCurrentProjectId(p.id); if(window.innerWidth < 768) setSidebarOpen(false); }} className={`w-full text-left text-sm px-3 py-2.5 rounded-xl transition flex items-center justify-between ${currentProjectId === p.id ? 'bg-[#282a2c] text-white' : 'text-neutral-300 hover:bg-[#282a2c]'}`}>
        <span className="truncate pr-2 flex items-center gap-2">
          {p.isPinned && <Pin size={12} className="text-blue-500 shrink-0"/>}
          <span className="truncate">{p.name}</span>
        </span>
      </button>
      <button onClick={(e) => { e.stopPropagation(); setMenuOpenProjectId(menuOpenProjectId === p.id ? null : p.id); }} className={`absolute right-1 top-1/2 -translate-y-1/2 p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-600 transition ${menuOpenProjectId === p.id ? 'opacity-100' : 'opacity-100 md:opacity-0 md:group-hover:opacity-100'}`}>
        <MoreVertical size={16} />
      </button>
      {menuOpenProjectId === p.id && (
        <div className="absolute right-0 top-full mt-1 w-40 bg-neutral-800 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden z-50 py-1">
          <button onClick={(e) => handleRenameProject(p.id, e)} className="w-full px-3 py-2 text-left text-sm text-neutral-200 hover:bg-neutral-700 flex items-center gap-2"><Edit2 size={14} /> Renombrar</button>
          <button onClick={(e) => handleTogglePin(p.id, e)} className="w-full px-3 py-2 text-left text-sm text-neutral-200 hover:bg-neutral-700 flex items-center gap-2">{p.isPinned ? <PinOff size={14} /> : <Pin size={14} />} {p.isPinned ? 'Desfijar' : 'Fijar'}</button>
          <div className="h-px bg-neutral-700 my-1"></div>
          <button onClick={(e) => handleDeleteProject(p.id, e)} className="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-neutral-700 flex items-center gap-2"><Trash2 size={14} /> Eliminar</button>
        </div>
      )}
    </div>
  );

  // ---- LOGIN SCREEN ----
  if (authChecked && !user && !guestMode && googleClientId) {
    return (
      <div className="fixed inset-0 bg-neutral-950 text-neutral-50 flex items-center justify-center p-6">
        <div className="w-full max-w-sm flex flex-col items-center gap-6">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-2xl"><Map size={32} /></div>
          <div className="text-center space-y-2">
            <h1 className="text-2xl font-bold text-white">LiDAR Fusion</h1>
            <p className="text-sm text-neutral-400">Procesa nubes de puntos LiDAR con FUSION-LTK, guiado por IA.</p>
          </div>
          <button onClick={handleLoginClick} className="w-full flex items-center justify-center gap-3 bg-white text-neutral-800 hover:bg-neutral-200 font-semibold rounded-full px-5 py-3.5 shadow-lg transition">
            <svg width="20" height="20" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 18.9 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.3 5.7l6.2 5.2C36.8 36.4 44 31 44 24c0-1.3-.1-2.6-.4-3.9z"/></svg>
            Continuar con Google
          </button>
          {!authRequired && (
            <button onClick={() => setGuestMode(true)} className="text-sm text-neutral-500 hover:text-neutral-300 transition">Continuar como invitado</button>
          )}
          <p className="text-[11px] text-neutral-600 text-center">Tu historial se guarda en tu cuenta de Google.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col w-full bg-neutral-950 font-sans text-neutral-50 overflow-hidden">
      {selectedMedia && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center p-2 md:p-8">
          <div className="absolute inset-0 bg-black/90 backdrop-blur-md cursor-zoom-out" onClick={() => { setSelectedMedia(null); setIs3DMode(false); }}></div>
          <div className="relative z-10 w-full max-w-6xl flex justify-end gap-3 mb-3 pointer-events-auto shrink-0">
            {selectedMedia.type === 'las' || selectedMedia.type === 'laz' ? (
              <button onClick={() => setIs3DMode(!is3DMode)} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-full font-bold shadow-lg flex items-center gap-2"><Map size={16} /> {is3DMode ? 'Ver en 2D' : 'Ver en 3D'}</button>
            ) : null}
            <a href={selectedMedia.url} download className="w-10 h-10 bg-neutral-800 hover:bg-neutral-700 text-white rounded-full flex items-center justify-center transition shadow-lg border border-neutral-700"><Download size={20} /></a>
            <button onClick={() => { setSelectedMedia(null); setIs3DMode(false); }} className="w-10 h-10 bg-neutral-800 hover:bg-red-500 text-white rounded-full flex items-center justify-center transition shadow-lg border border-neutral-700"><X size={20} /></button>
          </div>
          <div className="relative z-10 w-full max-w-6xl h-full max-h-[85vh] flex flex-col items-center justify-center pointer-events-none">
            {selectedMedia.type === 'las' || selectedMedia.type === 'laz' ? (
              is3DMode ? (
                selectedMedia.html_3d_url ? (
                  <div className="w-full h-full bg-[#131314] rounded-xl shadow-2xl overflow-hidden pointer-events-auto flex flex-col border border-neutral-700">
                    <div className="bg-neutral-800 text-neutral-300 text-xs px-4 py-2 border-b border-neutral-700 flex items-center justify-between"><span>Visor 3D Interactivo (Potree)</span></div>
                    <iframe src={selectedMedia.html_3d_url} className="flex-1 w-full bg-[#131314]" title="3D Viewer"></iframe>
                  </div>
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-neutral-900 rounded-xl border border-neutral-800 pointer-events-auto"><span className="text-neutral-500 text-sm">Modelo 3D no disponible para este archivo.</span></div>
                )
              ) : (
                selectedMedia.preview_b64 ? (
                  <img src={`data:image/png;base64,${selectedMedia.preview_b64}`} className="max-w-full max-h-full object-contain rounded-lg shadow-2xl pointer-events-auto" alt="Fullscreen Render" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-neutral-900 rounded-xl border border-neutral-800 pointer-events-auto"><span className="text-neutral-500 text-sm">Vista previa 2D no disponible para este archivo.</span></div>
                )
              )
            ) : ['tif', 'tiff', 'dtm', 'img'].includes(selectedMedia.type) ? (
              selectedMedia.preview_b64 ? (
                <div className="w-full h-full flex items-center justify-center pointer-events-auto overflow-hidden bg-black rounded-xl border border-neutral-800">
                  <TransformWrapper initialScale={1} minScale={0.1} maxScale={10} centerOnInit={true}>
                    <TransformComponent wrapperStyle={{width: '100%', height: '100%'}} contentStyle={{width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
                      <img src={`data:image/png;base64,${selectedMedia.preview_b64}`} className="max-w-full max-h-full object-contain shadow-2xl" alt="Preview" />
                    </TransformComponent>
                  </TransformWrapper>
                </div>
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-neutral-900 rounded-xl border border-neutral-800 pointer-events-auto"><span className="text-neutral-500 text-sm">Cargando miniatura o formato no soportado...</span></div>
              )
            ) : selectedMedia.type === 'html' ? (
              <div className="w-full h-full bg-white rounded-xl shadow-2xl overflow-hidden pointer-events-auto flex flex-col">
                <div className="bg-neutral-800 text-neutral-300 text-xs px-4 py-2 border-b border-neutral-700 flex items-center justify-between"><span>Visor Web</span></div>
                <iframe src={selectedMedia.url} className="flex-1 w-full bg-white" title={selectedMedia.name}></iframe>
              </div>
            ) : (
              <div className="w-full h-full bg-neutral-900 border border-neutral-700 rounded-xl shadow-2xl overflow-hidden pointer-events-auto flex flex-col">
                <div className="bg-neutral-800 text-neutral-300 text-xs px-4 py-2 border-b border-neutral-700 flex items-center justify-between shrink-0"><span>Visor de Documentos (Texto Plano)</span></div>
                <div className="flex-1 overflow-auto p-6 text-left"><pre className="text-xs font-mono text-neutral-300 whitespace-pre-wrap leading-relaxed">{textContent}</pre></div>
              </div>
            )}
            <div className="absolute -bottom-10 bg-neutral-900/80 px-4 py-2 rounded-full border border-neutral-700 backdrop-blur-sm pointer-events-auto">
              <span className="text-sm font-semibold text-white">{selectedMedia.name} {is3DMode ? '(Modo 3D)' : ''}</span>
            </div>
          </div>
        </div>
      )}

      {sidebarOpen && <div className="md:hidden fixed inset-0 bg-black/60 z-40 backdrop-blur-sm transition-opacity" onClick={() => setSidebarOpen(false)}></div>}

      <div className={`md:hidden fixed inset-y-0 left-0 w-[80vw] max-w-[320px] bg-[#131314] z-50 transform transition-transform duration-300 ease-in-out flex flex-col ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold ml-2">LiDAR Fusion</h2>
          <button onClick={() => setSidebarOpen(false)} className="p-2 text-neutral-400 hover:text-white"><X size={24} /></button>
        </div>
        {user && (
          <div className="px-4 pb-3 flex items-center gap-3">
            {user.picture ? <img src={user.picture} className="w-9 h-9 rounded-full" alt="" /> : <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">{firstName[0] || 'U'}</div>}
            <div className="min-w-0">
              <div className="text-sm font-medium text-neutral-100 truncate">{user.name}</div>
              <div className="text-xs text-neutral-500 truncate">{user.email}</div>
            </div>
          </div>
        )}
        <div className="px-4 mt-1">
          <button onClick={handleNewSession} className="w-full bg-[#1e1e1f] hover:bg-[#282a2c] text-neutral-200 rounded-full px-4 py-3.5 text-sm font-medium transition flex items-center gap-3"><Plus size={18} /> Nueva conversación</button>
        </div>
        <div className="mt-6 px-4 flex-1 overflow-y-auto hide-scrollbar pb-6">
          <h3 className="text-xs font-semibold text-neutral-500 mb-2 px-2">Reciente</h3>
          <div className="flex flex-col">
            {sortedProjects.length === 0 ? <div className="text-xs text-neutral-600 px-2 mt-2 italic">Sin proyectos.</div> : sortedProjects.map(renderProjectItem)}
          </div>
        </div>
        <div className="p-4 border-t border-neutral-800/50 flex flex-col gap-1">
          {!user && googleClientId && (
            <button onClick={handleLoginClick} className="w-full text-left text-sm text-neutral-300 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><Cloud size={16} /> Iniciar sesión con Google</button>
          )}
          {user && (
            <button onClick={handleLogout} className="text-left text-sm text-neutral-400 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><LogOut size={16} /> Cerrar sesión</button>
          )}
          {!user && (
            <button onClick={() => { if(confirm('¿Borrar todo de este navegador?')) { localStorage.clear(); window.location.reload(); } }} className="text-left text-sm text-neutral-400 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><History size={16} /> Borrar Todo</button>
          )}
        </div>
      </div>

      <div className="hidden md:flex flex-1 overflow-hidden relative">
        <div className={`${sidebarOpen ? 'w-[260px]' : 'w-[0px] opacity-0 overflow-hidden'} transition-all duration-300 shrink-0 bg-[#131314] flex-col flex relative z-10`}>
          <div className="p-4 flex items-center gap-3">
            <button onClick={() => setSidebarOpen(false)} className="p-2 text-neutral-400 hover:text-white hover:bg-neutral-800 rounded-full transition"><Menu size={24} /></button>
          </div>
          {user && (
            <div className="px-4 pb-3 flex items-center gap-3">
              {user.picture ? <img src={user.picture} className="w-9 h-9 rounded-full" alt="" /> : <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">{firstName[0] || 'U'}</div>}
              <div className="min-w-0">
                <div className="text-sm font-medium text-neutral-100 truncate">{user.name}</div>
                <div className="text-xs text-neutral-500 truncate">{user.email}</div>
              </div>
            </div>
          )}
          <div className="px-3 mt-1">
            <button onClick={handleNewSession} className="w-full bg-[#1e1e1f] hover:bg-[#282a2c] text-neutral-200 rounded-full px-4 py-3 text-sm font-medium transition flex items-center gap-3"><Plus size={18} /> Nueva sesión</button>
          </div>
          <div className="mt-8 px-4 flex-1 overflow-y-auto hide-scrollbar">
            <h3 className="text-xs font-semibold text-neutral-500 mb-2 px-2">Recientes</h3>
            <div className="flex flex-col">
              {sortedProjects.length === 0 ? <div className="text-xs text-neutral-600 px-2 mt-2 italic">No hay proyectos.</div> : sortedProjects.map(renderProjectItem)}
            </div>
          </div>
          <div className="p-4 flex flex-col gap-1 border-t border-neutral-800/50">
            {!user && googleClientId && (
              <button onClick={handleLoginClick} className="text-left text-sm text-neutral-300 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><Cloud size={16} /> Iniciar sesión con Google</button>
            )}
            {user && (
              <button onClick={handleLogout} className="text-left text-sm text-neutral-400 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><LogOut size={16} /> Cerrar sesión</button>
            )}
            {!user && (
              <button onClick={() => { if(confirm('¿Borrar todo de este navegador?')) { localStorage.clear(); window.location.reload(); } }} className="text-left text-sm text-neutral-400 hover:bg-neutral-800 px-3 py-2.5 rounded-xl transition flex items-center gap-3"><History size={16} /> Borrar Todo</button>
            )}
          </div>
        </div>

        <div className="shrink-0 h-full overflow-hidden flex flex-col border-r border-neutral-800 relative z-10 bg-neutral-950" style={{ width: chatWidth, minWidth: '350px' }}>
          {ChatContent}
          <div className="absolute top-0 -right-1 bottom-0 w-2 cursor-col-resize hover:bg-blue-500 transition-colors z-50" onMouseDown={() => { isDragging.current = true; document.body.style.cursor = 'col-resize'; }}></div>
        </div>

        <div className="flex-1 shrink-0 h-full overflow-hidden bg-neutral-900 border-l border-neutral-800/50">{IdeContent}</div>
      </div>

      <main className="md:hidden flex-1 flex flex-col relative overflow-hidden bg-neutral-950">
        <div className={`absolute inset-0 flex flex-col ${activeTab !== 'chat' ? 'hidden' : 'flex'}`}>{ChatContent}</div>
        <div className={`absolute inset-0 flex flex-col ${activeTab !== 'visor' ? 'hidden' : 'flex'}`}>{IdeContent}</div>
      </main>

      <nav className="md:hidden bg-neutral-900/90 backdrop-blur-xl border-t border-neutral-800 flex h-[70px] pb-safe z-30 shrink-0 relative">
        <button onClick={() => setActiveTab('chat')} className={`flex-1 flex flex-col items-center justify-center gap-1.5 transition-colors ${activeTab === 'chat' ? 'text-blue-500' : 'text-neutral-500 hover:text-neutral-300'}`}>
          <MessageSquare size={20} className={activeTab === 'chat' ? 'fill-blue-500/20' : ''}/><span className="text-[10px] font-bold">Chat</span>
        </button>
        <button onClick={() => setActiveTab('visor')} className={`flex-1 flex flex-col items-center justify-center gap-1.5 transition-colors ${activeTab === 'visor' ? 'text-blue-500' : 'text-neutral-500 hover:text-neutral-300'}`}>
          <Terminal size={20} className={activeTab === 'visor' ? 'fill-blue-500/20' : ''}/><span className="text-[10px] font-bold">IDE</span>
        </button>
      </nav>
    </div>
  );
}
