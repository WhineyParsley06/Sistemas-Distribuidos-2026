import argparse
import asyncio
import base64
import hashlib
import json
import socket
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import websockets
from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


MAX_IMAGE_SIZE_BYTES = 4 * 1024 * 1024  # 4 MB


HTML_PAGE = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Chat P2P LAN Seguro + Videollamada + Imágenes + WebSocket</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 16px; background:#f5f7fb; color:#222; }
    .row { display:flex; gap:12px; flex-wrap:wrap; }
    .card { background:#fff; border:1px solid #ddd; border-radius:14px; padding:14px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
    .card h3 { margin:0 0 10px; }
    #log { height:320px; overflow:auto; border:1px solid #ddd; border-radius:12px; padding:10px; background:#fafafa; }
    .msg { margin:8px 0; padding:8px 10px; border-radius:10px; max-width:85%; }
    .msg.me { background:#d9ecff; margin-left:auto; }
    .msg.other { background:#eee; }
    .meta { font-size:12px; color:#555; margin-bottom:4px; }
    .controls { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    input, button, select {
      padding:10px; border-radius:10px; border:1px solid #ccc; font-size:14px;
    }
    input[type="text"] { flex:1; min-width:220px; }
    button { cursor:pointer; }
    button.primary { background:#111; color:#fff; border-color:#111; }
    button.danger { background:#8b1e1e; color:#fff; border-color:#8b1e1e; }
    .pill {
      display:inline-block; padding:6px 10px; border:1px solid #ddd;
      border-radius:999px; background:#fff; font-size:13px;
    }
    #peers { display:flex; flex-wrap:wrap; gap:8px; }
    .peer-btn {
      border:1px solid #ddd; background:#fff; border-radius:999px;
      padding:8px 12px; cursor:pointer;
    }
    .peer-btn.active { border-color:#111; font-weight:bold; background:#eef6ff; }
    .small { font-size:12px; color:#666; }
    .status-ok { color:#0a7f31; font-weight:bold; }
    .status-warn { color:#b45309; font-weight:bold; }
    .status-error { color:#b91c1c; font-weight:bold; }
    .secure { color:#0a7f31; font-weight:bold; }
    .warning-box {
      background:#fff8e1; border:1px solid #f2d38c; padding:10px; border-radius:10px; margin-bottom:12px;
    }
    .code {
      font-family: Consolas, monospace; font-size:12px; background:#f1f5f9; padding:2px 6px; border-radius:6px;
    }
    .video-grid {
      display:grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap:12px;
      margin-top:10px;
    }
    video {
      width:100%;
      background:#111;
      border-radius:12px;
      border:1px solid #ddd;
      min-height:220px;
    }
    .chat-image {
      display:block;
      max-width:260px;
      margin-top:6px;
      border-radius:10px;
      border:1px solid #d1d5db;
    }
    .file-row {
      display:flex;
      gap:8px;
      flex-wrap:wrap;
      align-items:center;
      margin-top:8px;
    }
  </style>
</head>
<body>
  <h2>Chat P2P LAN Seguro + Videollamada + Imágenes</h2>

  <div class="warning-box">
    <b>Seguridad activa:</b> el chat, las imágenes y la señalización WebRTC viajan por tu canal P2P cifrado con
    <span class="secure">RSA + cifrado simétrico</span>. El medio de WebRTC se protege aparte por el navegador.
  </div>

  <div class="row">
    <div class="card" style="flex:1; min-width:320px">
      <h3>Mi nodo</h3>
      <div class="controls">
        <span class="pill">Nombre: <b id="meName">...</b></span>
        <span class="pill">IP: <b id="meIp">...</b></span>
        <span class="pill">TCP: <b id="meTcp">...</b></span>
        <span class="pill">HTTP: <b id="meHttp">...</b></span>
        <span class="pill">WS local: <b id="meWs">...</b></span>
      </div>
      <div style="margin-top:10px" class="small">
        Este equipo es cliente y servidor al mismo tiempo.
      </div>
      <div style="margin-top:8px">
        Estado de red: <span id="netStatus" class="status-ok">Buscando peers...</span>
      </div>
      <div style="margin-top:8px" class="small">
        Huella pública RSA: <span class="code" id="meFingerprint">...</span>
      </div>
      <div style="margin-top:8px" class="small">
        WebSocket local: <span id="wsStatus" class="status-warn">conectando...</span>
      </div>
    </div>

    <div class="card" style="flex:1; min-width:320px">
      <h3>Peers detectados</h3>
      <div id="peers"></div>
      <div style="margin-top:10px" class="small">
        Se descubren automáticamente en la misma WiFi por broadcast UDP.
      </div>
      <div style="margin-top:10px">
        Chat activo: <span class="pill"><b id="activePeer">—</b></span>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:12px">
    <h3>Videollamada</h3>
    <div class="controls">
      <label>Codec preferido:</label>
      <select id="codec">
        <option value="h264" selected>H.264</option>
        <option value="av1">AV1</option>
        <option value="h265">H.265 / HEVC</option>
      </select>
      <button class="primary" id="btnStartCall">Iniciar llamada</button>
      <button class="danger" id="btnHangup">Colgar</button>
      <button id="btnToggleCamera">Activar cámara</button>
      <button id="btnToggleMic">Activar micrófono</button>
      <span class="pill">Estado: <b id="callStatus">sin llamada</b></span>
      <span class="pill">Cámara: <b id="cameraStatus">sin iniciar</b></span>
      <span class="pill">Micrófono: <b id="micStatus">sin iniciar</b></span>
    </div>

    <div class="video-grid">
      <div>
        <div class="small" style="margin-bottom:6px">Tu cámara</div>
        <video id="localVideo" autoplay playsinline muted></video>
      </div>
      <div>
        <div class="small" style="margin-bottom:6px">Peer remoto</div>
        <video id="remoteVideo" autoplay playsinline></video>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:12px">
    <h3>Conversación</h3>
    <div id="log"></div>

    <div class="controls" style="margin-top:12px">
      <input id="text" type="text" placeholder="Escribe un mensaje..." />
      <button class="primary" id="btnSend">Enviar</button>
    </div>

    <div class="file-row">
      <input id="imageFile" type="file" accept="image/*" />
      <button id="btnSendImage">Enviar imagen</button>
      <span class="small">Máximo recomendado: 4 MB</span>
    </div>
  </div>

<script>
let activePeer = null;
let lastRenderHash = "";
let pc = null;
let localStream = null;
let remoteStream = null;
let controlWs = null;
let wsReconnectTimer = null;
let cameraEnabled = false;
let micEnabled = false;

const WS_URL = `ws://${location.hostname}:__WS_PORT__/ws`;
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  return String(str)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");
}

function setCallStatus(text, cls="status-warn") {
  $("callStatus").textContent = text;
  $("callStatus").className = cls;
}

function setWsStatus(text, cls="status-warn") {
  $("wsStatus").textContent = text;
  $("wsStatus").className = cls;
}

function getVideoTrack() {
  return localStream ? (localStream.getVideoTracks()[0] || null) : null;
}

function getAudioTrack() {
  return localStream ? (localStream.getAudioTracks()[0] || null) : null;
}

function updateMediaButtons() {
  const videoTrack = getVideoTrack();
  const audioTrack = getAudioTrack();

  if (videoTrack) {
    cameraEnabled = videoTrack.enabled;
    $("btnToggleCamera").textContent = cameraEnabled ? "Apagar cámara" : "Encender cámara";
    $("cameraStatus").textContent = cameraEnabled ? "encendida" : "apagada";
  } else {
    cameraEnabled = false;
    $("btnToggleCamera").textContent = "Activar cámara";
    $("cameraStatus").textContent = "sin iniciar";
  }

  if (audioTrack) {
    micEnabled = audioTrack.enabled;
    $("btnToggleMic").textContent = micEnabled ? "Silenciar micrófono" : "Activar micrófono";
    $("micStatus").textContent = micEnabled ? "activo" : "silenciado";
  } else {
    micEnabled = false;
    $("btnToggleMic").textContent = "Activar micrófono";
    $("micStatus").textContent = "sin iniciar";
  }
}

async function toggleCamera() {
  try {
    await ensureLocalMedia();
    const videoTrack = getVideoTrack();

    if (!videoTrack) {
      alert("No se encontró una cámara disponible.");
      return;
    }

    videoTrack.enabled = !videoTrack.enabled;
    updateMediaButtons();
  } catch (err) {
    alert("No fue posible cambiar el estado de la cámara: " + err.message);
  }
}

async function toggleMic() {
  try {
    await ensureLocalMedia();
    const audioTrack = getAudioTrack();

    if (!audioTrack) {
      alert("No se encontró un micrófono disponible.");
      return;
    }

    audioTrack.enabled = !audioTrack.enabled;
    updateMediaButtons();
  } catch (err) {
    alert("No fue posible cambiar el estado del micrófono: " + err.message);
  }
}

function renderPeers(peers) {
  const cont = $("peers");
  cont.innerHTML = "";

  if (!peers.length) {
    cont.innerHTML = `<span class="small">No se detectaron otros peers todavía.</span>`;
    $("netStatus").textContent = "Esperando peers...";
    $("netStatus").className = "status-warn";
    if (activePeer && !peers.some(p => p.name === activePeer)) {
      activePeer = null;
      $("activePeer").textContent = "—";
    }
    return;
  }

  $("netStatus").textContent = "Peers detectados en la red";
  $("netStatus").className = "status-ok";

  peers.forEach(peer => {
    const btn = document.createElement("button");
    btn.className = "peer-btn" + (peer.name === activePeer ? " active" : "");
    btn.innerHTML = `
      <div>${escapeHtml(peer.name)} (${escapeHtml(peer.ip)})</div>
      <div class="small">RSA: ${escapeHtml(peer.fingerprint || "sin clave")}</div>
    `;
    btn.onclick = () => {
      activePeer = peer.name;
      $("activePeer").textContent = peer.name;
      refreshState();
    };
    cont.appendChild(btn);
  });

  if (!activePeer && peers.length > 0) {
    activePeer = peers[0].name;
    $("activePeer").textContent = activePeer;
  }
}

function renderMessages(messages) {
  const hash = JSON.stringify(messages);
  if (hash === lastRenderHash) return;
  lastRenderHash = hash;

  const log = $("log");
  log.innerHTML = "";

  if (!activePeer) {
    log.innerHTML = `<div class="small">Selecciona un peer para iniciar el chat.</div>`;
    return;
  }

  if (!messages.length) {
    log.innerHTML = `<div class="small">Aún no hay mensajes con ${escapeHtml(activePeer)}.</div>`;
    return;
  }

  messages.forEach(m => {
    const div = document.createElement("div");
    div.className = "msg " + (m.direction === "out" ? "me" : "other");
    const secureBadge = m.secure ? `<span class="secure">🔒 seguro</span>` : `<span class="status-error">sin seguridad</span>`;

    if (m.kind === "image") {
      const mime = m.mime || "image/*";
      const filename = m.filename || "imagen";
      const dataUrl = `data:${mime};base64,${m.data || ""}`;

      div.innerHTML = `
        <div class="meta">
          ${m.direction === "out" ? "Yo" : escapeHtml(m.from)} · ${escapeHtml(m.timestamp)} · ${secureBadge}
        </div>
        <div>📷 ${escapeHtml(filename)}</div>
        <img class="chat-image" src="${dataUrl}" alt="${escapeHtml(filename)}" />
        <div style="margin-top:6px">
          <a download="${escapeHtml(filename)}" href="${dataUrl}">Descargar imagen</a>
        </div>
      `;
    } else {
      div.innerHTML = `
        <div class="meta">
          ${m.direction === "out" ? "Yo" : escapeHtml(m.from)} · ${escapeHtml(m.timestamp)} · ${secureBadge}
        </div>
        <div>${escapeHtml(m.text || "")}</div>
      `;
    }

    log.appendChild(div);
  });

  log.scrollTop = log.scrollHeight;
}

async function refreshState() {
  try {
    const url = activePeer
      ? `/api/state?active=${encodeURIComponent(activePeer)}`
      : "/api/state";

    const res = await fetch(url);
    const data = await res.json();

    $("meName").textContent = data.me.name;
    $("meIp").textContent = data.me.ip;
    $("meTcp").textContent = data.me.tcp_port;
    $("meHttp").textContent = data.me.http_port;
    $("meWs").textContent = data.me.ws_port;
    $("meFingerprint").textContent = data.me.fingerprint || "...";

    renderPeers(data.peers || []);

    if (activePeer && data.active_peer !== activePeer) {
      activePeer = data.active_peer || activePeer;
      $("activePeer").textContent = activePeer || "—";
    }

    renderMessages(data.messages || []);
  } catch (err) {
    $("netStatus").textContent = "Error consultando el estado local";
    $("netStatus").className = "status-error";
  }
}

async function sendText() {
  const text = $("text").value.trim();
  if (!activePeer) {
    alert("Selecciona un peer.");
    return;
  }
  if (!text) return;

  const res = await fetch("/api/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to: activePeer, text })
  });

  const data = await res.json();
  if (!data.ok) {
    alert(data.error || "No se pudo enviar el mensaje.");
    return;
  }

  $("text").value = "";
  await refreshState();
}

async function sendImage() {
  if (!activePeer) {
    alert("Selecciona un peer.");
    return;
  }

  const file = $("imageFile").files[0];
  if (!file) {
    alert("Selecciona una imagen.");
    return;
  }

  if (!file.type.startsWith("image/")) {
    alert("El archivo debe ser una imagen.");
    return;
  }

  if (file.size > 4 * 1024 * 1024) {
    alert("La imagen es demasiado grande. Usa una menor a 4 MB.");
    return;
  }

  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const result = reader.result;
      const base64Data = String(result).split(",")[1];

      const res = await fetch("/api/send-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to: activePeer,
          filename: file.name,
          mime: file.type || "image/png",
          data: base64Data
        })
      });

      const data = await res.json();
      if (!data.ok) {
        alert(data.error || "No se pudo enviar la imagen.");
        return;
      }

      $("imageFile").value = "";
      await refreshState();
    } catch (err) {
      alert("Error enviando imagen: " + err.message);
    }
  };

  reader.readAsDataURL(file);
}

function codecAliases(preferred) {
  if (preferred === "h264") return ["video/h264"];
  if (preferred === "av1") return ["video/av1"];
  if (preferred === "h265") return ["video/h265", "video/hevc"];
  return [];
}

function reorderVideoCodecs(codecs, preferred) {
  const aliases = codecAliases(preferred);
  const media = codecs.filter(c => {
    const mt = (c.mimeType || "").toLowerCase();
    return mt.startsWith("video/") &&
           !mt.includes("rtx") &&
           !mt.includes("red") &&
           !mt.includes("ulpfec") &&
           !mt.includes("flexfec");
  });
  const aux = codecs.filter(c => !media.includes(c));

  const wanted = [];
  const rest = [];

  for (const c of media) {
    const mt = (c.mimeType || "").toLowerCase();
    if (aliases.some(a => mt === a)) wanted.push(c);
    else rest.push(c);
  }

  return [...wanted, ...rest, ...aux];
}

function applyPreferredCodec(peerConnection, preferred) {
  try {
    const caps = RTCRtpSender.getCapabilities("video");
    if (!caps || !caps.codecs) return;

    const codecs = reorderVideoCodecs(caps.codecs, preferred);
    for (const transceiver of peerConnection.getTransceivers()) {
      const senderTrack = transceiver.sender && transceiver.sender.track;
      if (senderTrack && senderTrack.kind === "video" && transceiver.setCodecPreferences) {
        transceiver.setCodecPreferences(codecs);
      }
    }
  } catch (err) {
    console.warn("No fue posible ajustar preferencias de codec:", err);
  }
}

async function ensureLocalMedia() {
  if (localStream) {
    updateMediaButtons();
    return localStream;
  }

  localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
  $("localVideo").srcObject = localStream;
  updateMediaButtons();
  return localStream;
}

async function postSignal(signal, forcedPeer=null) {
  const to = forcedPeer || activePeer;
  if (!to) throw new Error("No hay peer activo para señalización");

  const res = await fetch("/api/webrtc/signal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to, signal })
  });

  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "No se pudo enviar la señal");
}

async function createPeerConnection(preferredCodec) {
  if (pc) {
    try { pc.close(); } catch {}
    pc = null;
  }

  remoteStream = new MediaStream();
  $("remoteVideo").srcObject = remoteStream;

  pc = new RTCPeerConnection({
    iceServers: []
  });

  pc.onicecandidate = async (event) => {
    if (event.candidate) {
      try {
        await postSignal({ type: "candidate", candidate: event.candidate });
      } catch (err) {
        console.error(err);
      }
    }
  };

  pc.ontrack = (event) => {
    for (const track of event.streams[0].getTracks()) {
      remoteStream.addTrack(track);
    }
  };

  pc.onconnectionstatechange = () => {
    const state = pc.connectionState;
    if (state === "connected") setCallStatus("conectada", "status-ok");
    else if (state === "connecting") setCallStatus("conectando...", "status-warn");
    else if (state === "failed") setCallStatus("fallida", "status-error");
    else if (state === "disconnected") setCallStatus("desconectada", "status-error");
    else if (state === "closed") setCallStatus("cerrada", "status-error");
    else setCallStatus(state, "status-warn");
  };

  await ensureLocalMedia();
  for (const track of localStream.getTracks()) {
    pc.addTrack(track, localStream);
  }

  applyPreferredCodec(pc, preferredCodec);
  updateMediaButtons();
  return pc;
}

async function startCall() {
  if (!activePeer) {
    alert("Selecciona un peer antes de llamar.");
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Este navegador no soporta captura de cámara/micrófono.");
    return;
  }

  const preferredCodec = $("codec").value;

  try {
    setCallStatus("preparando...", "status-warn");
    await createPeerConnection(preferredCodec);

    const offer = await pc.createOffer({
      offerToReceiveAudio: true,
      offerToReceiveVideo: true
    });

    await pc.setLocalDescription(offer);

    await postSignal({
      type: "offer",
      sdp: pc.localDescription,
      preferredCodec
    });

    setCallStatus("oferta enviada", "status-warn");
  } catch (err) {
    console.error(err);
    setCallStatus("error al iniciar", "status-error");
    alert("No se pudo iniciar la llamada: " + err.message);
  }
}

async function hangup(sendRemote=true) {
  const peerSnapshot = activePeer;

  if (sendRemote && peerSnapshot) {
    try {
      await postSignal({ type: "hangup" }, peerSnapshot);
    } catch (err) {
      console.warn(err);
    }
  }

  if (pc) {
    try { pc.close(); } catch {}
    pc = null;
  }

  if ($("remoteVideo").srcObject) {
    try {
      $("remoteVideo").srcObject.getTracks().forEach(t => t.stop && t.stop());
    } catch {}
  }
  $("remoteVideo").srcObject = null;
  remoteStream = null;
  setCallStatus("sin llamada", "status-warn");
  updateMediaButtons();
}

async function handleSignalEnvelope(ev) {
  const from = ev.from;
  const signal = ev.signal || {};

  if (!signal.type) return;

  if (signal.type === "offer") {
    activePeer = from;
    $("activePeer").textContent = activePeer;

    try {
      setCallStatus("llamada entrante...", "status-warn");
      await createPeerConnection(signal.preferredCodec || $("codec").value);

      await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      await postSignal({
        type: "answer",
        sdp: pc.localDescription
      }, from);

      setCallStatus("respuesta enviada", "status-warn");
    } catch (err) {
      console.error(err);
      setCallStatus("error en llamada entrante", "status-error");
    }
    return;
  }

  if (signal.type === "answer") {
    try {
      if (pc) {
        await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));
        setCallStatus("respuesta recibida", "status-warn");
      }
    } catch (err) {
      console.error(err);
      setCallStatus("error al aplicar answer", "status-error");
    }
    return;
  }

  if (signal.type === "candidate") {
    try {
      if (pc && signal.candidate) {
        await pc.addIceCandidate(signal.candidate);
      }
    } catch (err) {
      console.warn("ICE candidate no aplicado:", err);
    }
    return;
  }

  if (signal.type === "hangup") {
    await hangup(false);
    setCallStatus("el peer colgó", "status-error");
  }
}

function connectLocalWebSocket() {
  try {
    controlWs = new WebSocket(WS_URL);
  } catch (err) {
    setWsStatus("error local", "status-error");
    scheduleWsReconnect();
    return;
  }

  controlWs.onopen = () => {
    setWsStatus("conectado", "status-ok");
  };

  controlWs.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);

      if (msg.kind === "ws_ready") {
        setWsStatus("conectado", "status-ok");
        return;
      }

      if (msg.kind === "signal_event") {
        await handleSignalEnvelope(msg.event);
        return;
      }

      if (msg.kind === "system") {
        console.log(msg.message || "evento local");
        return;
      }
    } catch (err) {
      console.warn("Mensaje WS inválido:", err);
    }
  };

  controlWs.onerror = () => {
    setWsStatus("error", "status-error");
  };

  controlWs.onclose = () => {
    setWsStatus("reconectando...", "status-warn");
    scheduleWsReconnect();
  };
}

function scheduleWsReconnect() {
  if (wsReconnectTimer) return;
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    connectLocalWebSocket();
  }, 1500);
}

$("btnSend").onclick = sendText;
$("btnSendImage").onclick = sendImage;
$("btnToggleCamera").onclick = toggleCamera;
$("btnToggleMic").onclick = toggleMic;
$("text").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendText();
});
$("btnStartCall").onclick = startCall;
$("btnHangup").onclick = () => hangup(true);

setInterval(refreshState, 1000);
refreshState();
connectLocalWebSocket();
setCallStatus("sin llamada", "status-warn");
updateMediaButtons();
</script>
</body>
</html>
"""


def now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("utf-8"))


def get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


class ChatNode:
    def __init__(self, name: str, http_port: int, tcp_port: int, discovery_port: int, ws_port: int):
        self.name = name
        self.http_port = http_port
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.ws_port = ws_port
        self.ip = get_local_ip()

        self.lock = threading.RLock()
        self.peers = {}
        self.conversations = {}
        self.stop_event = threading.Event()
        self.http_ready = threading.Event()
        self.ws_ready = threading.Event()

        self.ws_loop = None
        self.ws_clients = set()

        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.public_key = self.private_key.public_key()
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        self.public_fingerprint = self.compute_fingerprint(self.public_key_pem)

    def compute_fingerprint(self, public_key_pem: str) -> str:
        digest = hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()
        return digest[:16]

    def get_peers(self):
        with self.lock:
            peers = []
            for name, info in self.peers.items():
                if name == self.name:
                    continue
                peers.append({
                    "name": info["name"],
                    "ip": info["ip"],
                    "tcp_port": info["tcp_port"],
                    "last_seen": info["last_seen"],
                    "fingerprint": info.get("fingerprint"),
                })
            peers.sort(key=lambda x: x["name"].lower())
            return peers

    def get_messages(self, peer_name: str):
        with self.lock:
            return list(self.conversations.get(peer_name, []))

    def add_message(
        self,
        peer_name: str,
        direction: str,
        sender: str,
        text: str = "",
        secure: bool = True,
        kind: str = "text",
        filename: str | None = None,
        mime: str | None = None,
        data: str | None = None,
    ):
        with self.lock:
            self.conversations.setdefault(peer_name, []).append({
                "direction": direction,
                "from": sender,
                "text": text,
                "timestamp": now_str(),
                "secure": secure,
                "kind": kind,
                "filename": filename,
                "mime": mime,
                "data": data,
            })
            if len(self.conversations[peer_name]) > 300:
                self.conversations[peer_name] = self.conversations[peer_name][-300:]

    def upsert_peer(self, name: str, ip: str, tcp_port: int, public_key_pem=None):
        if name == self.name:
            return

        with self.lock:
            prev = self.peers.get(name, {})
            resolved_key = public_key_pem or prev.get("public_key")
            fingerprint = self.compute_fingerprint(resolved_key) if resolved_key else prev.get("fingerprint")
            self.peers[name] = {
                "name": name,
                "ip": ip,
                "tcp_port": tcp_port,
                "last_seen": time.time(),
                "public_key": resolved_key,
                "fingerprint": fingerprint,
            }

    def cleanup_stale_peers(self, ttl_seconds: int = 8):
        while not self.stop_event.is_set():
            time.sleep(2)
            now = time.time()
            with self.lock:
                stale = [
                    name for name, info in self.peers.items()
                    if now - info["last_seen"] > ttl_seconds
                ]
                for name in stale:
                    self.peers.pop(name, None)

    def discovery_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", self.discovery_port))
        except OSError as e:
            print(f"[ERROR] No se pudo abrir el puerto UDP {self.discovery_port}: {e}")
            return

        while not self.stop_event.is_set():
            try:
                data, addr = sock.recvfrom(65535)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("type") != "hello":
                    continue

                peer_name = msg.get("name")
                peer_ip = msg.get("ip") or addr[0]
                peer_tcp = int(msg.get("tcp_port"))
                peer_public_key = msg.get("public_key")

                self.upsert_peer(peer_name, peer_ip, peer_tcp, peer_public_key)
            except Exception:
                continue

    def discovery_broadcaster(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        while not self.stop_event.is_set():
            payload = json.dumps({
                "type": "hello",
                "name": self.name,
                "ip": self.ip,
                "tcp_port": self.tcp_port,
                "public_key": self.public_key_pem,
            }).encode("utf-8")

            try:
                sock.sendto(payload, ("255.255.255.255", self.discovery_port))
            except Exception:
                pass

            time.sleep(2)

    def build_secure_packet(self, peer_public_key_pem: str, payload_obj: dict) -> dict:
        peer_public_key = serialization.load_pem_public_key(peer_public_key_pem.encode("utf-8"))

        plaintext_bytes = json.dumps(
            payload_obj,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        fernet_key = Fernet.generate_key()
        ciphertext = Fernet(fernet_key).encrypt(plaintext_bytes)

        encrypted_key = peer_public_key.encrypt(
            fernet_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        signed_body = json.dumps(
            {
                "from": self.name,
                "enc_key": b64e(encrypted_key),
                "ciphertext": b64e(ciphertext),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        signature = self.private_key.sign(
            signed_body,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

        return {
            "type": "secure_packet",
            "from": self.name,
            "sender_tcp_port": self.tcp_port,
            "sender_public_key": self.public_key_pem,
            "enc_key": b64e(encrypted_key),
            "ciphertext": b64e(ciphertext),
            "signature": b64e(signature),
        }

    def decrypt_secure_packet(self, data: dict):
        try:
            sender = data.get("from", "?")
            sender_public_key_pem = data.get("sender_public_key")

            if not sender_public_key_pem:
                return None, "Falta la clave pública del remitente"

            with self.lock:
                known = self.peers.get(sender)

            if known and known.get("public_key") and known["public_key"] != sender_public_key_pem:
                return None, "La clave pública del remitente no coincide con la ya registrada"

            sender_public_key = serialization.load_pem_public_key(
                sender_public_key_pem.encode("utf-8")
            )

            signed_body = json.dumps(
                {
                    "from": sender,
                    "enc_key": data["enc_key"],
                    "ciphertext": data["ciphertext"],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

            sender_public_key.verify(
                b64d(data["signature"]),
                signed_body,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )

            fernet_key = self.private_key.decrypt(
                b64d(data["enc_key"]),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            plaintext = Fernet(fernet_key).decrypt(
                b64d(data["ciphertext"])
            ).decode("utf-8")

            return json.loads(plaintext), None

        except InvalidSignature:
            return None, "Firma RSA inválida"
        except Exception as e:
            return None, str(e)

    def notify_browser_signal(self, sender: str, signal: dict):
        if not self.ws_loop:
            return

        message = {
            "kind": "signal_event",
            "event": {
                "from": sender,
                "signal": signal,
                "timestamp": now_str(),
            }
        }

        async def _broadcast():
            dead = []
            data = json.dumps(message, ensure_ascii=False)
            for ws in list(self.ws_clients):
                try:
                    await ws.send(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.ws_clients.discard(ws)

        try:
            asyncio.run_coroutine_threadsafe(_broadcast(), self.ws_loop)
        except Exception:
            pass

    def handle_peer_connection(self, conn: socket.socket, addr):
        with conn:
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                    if b"\n" in raw:
                        break

                data = json.loads(raw.decode("utf-8").strip())

                if data.get("type") != "secure_packet":
                    conn.sendall(
                        json.dumps({"ok": False, "error": "Solo se acepta secure_packet"}).encode("utf-8") + b"\n"
                    )
                    return

                sender = data.get("from", addr[0])
                sender_tcp_port = int(data.get("sender_tcp_port", 0) or 0)
                sender_public_key = data.get("sender_public_key")

                if sender_public_key and sender_tcp_port:
                    self.upsert_peer(sender, addr[0], sender_tcp_port, sender_public_key)

                payload, err = self.decrypt_secure_packet(data)
                if err:
                    conn.sendall(json.dumps({"ok": False, "error": err}).encode("utf-8") + b"\n")
                    return

                kind = payload.get("kind")

                if kind == "text":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        conn.sendall(json.dumps({"ok": False, "error": "Mensaje vacío"}).encode("utf-8") + b"\n")
                        return

                    self.add_message(sender, "in", sender, text, secure=True, kind="text")
                    conn.sendall(json.dumps({"ok": True}).encode("utf-8") + b"\n")
                    return

                if kind == "image":
                    filename = str(payload.get("filename", "imagen")).strip() or "imagen"
                    mime = str(payload.get("mime", "image/png")).strip() or "image/png"
                    image_b64 = str(payload.get("data", "")).strip()

                    if not image_b64:
                        conn.sendall(json.dumps({"ok": False, "error": "Imagen vacía"}).encode("utf-8") + b"\n")
                        return

                    try:
                        image_bytes = b64d(image_b64)
                    except Exception:
                        conn.sendall(json.dumps({"ok": False, "error": "Imagen en base64 inválida"}).encode("utf-8") + b"\n")
                        return

                    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                        conn.sendall(json.dumps({"ok": False, "error": "La imagen supera el tamaño permitido"}).encode("utf-8") + b"\n")
                        return

                    self.add_message(
                        sender,
                        "in",
                        sender,
                        "",
                        secure=True,
                        kind="image",
                        filename=filename,
                        mime=mime,
                        data=image_b64,
                    )
                    conn.sendall(json.dumps({"ok": True}).encode("utf-8") + b"\n")
                    return

                if kind == "signal":
                    signal = payload.get("signal")
                    if not isinstance(signal, dict):
                        conn.sendall(json.dumps({"ok": False, "error": "Signal inválida"}).encode("utf-8") + b"\n")
                        return

                    self.notify_browser_signal(sender, signal)
                    conn.sendall(json.dumps({"ok": True}).encode("utf-8") + b"\n")
                    return

                conn.sendall(json.dumps({"ok": False, "error": "kind no soportado"}).encode("utf-8") + b"\n")

            except Exception as e:
                try:
                    conn.sendall(json.dumps({"ok": False, "error": str(e)}).encode("utf-8") + b"\n")
                except Exception:
                    pass

    def tcp_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.tcp_port))
        server.listen()

        print(f"[TCP] Escuchando en 0.0.0.0:{self.tcp_port}")

        while not self.stop_event.is_set():
            try:
                conn, addr = server.accept()
                threading.Thread(
                    target=self.handle_peer_connection,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except Exception:
                continue

    def send_payload_to_peer(self, peer_name: str, payload_obj: dict):
        with self.lock:
            peer = self.peers.get(peer_name)

        if not peer:
            return False, "Peer no encontrado. Espera a que aparezca en la lista."

        peer_public_key = peer.get("public_key")
        if not peer_public_key:
            return False, "El peer aún no ha compartido su clave pública RSA."

        try:
            packet = self.build_secure_packet(peer_public_key, payload_obj)
            payload = json.dumps(packet).encode("utf-8") + b"\n"

            with socket.create_connection((peer["ip"], peer["tcp_port"]), timeout=15) as sock:
                sock.sendall(payload)

                raw = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                    if b"\n" in raw:
                        break

                if raw:
                    response = json.loads(raw.decode("utf-8").strip())
                    if not response.get("ok"):
                        return False, response.get("error", "Error remoto")

            return True, None

        except Exception as e:
            return False, f"No se pudo conectar con {peer_name} ({peer['ip']}:{peer['tcp_port']}): {e}"

    def send_text_to_peer(self, peer_name: str, text: str):
        ok, err = self.send_payload_to_peer(peer_name, {
            "kind": "text",
            "text": text,
        })
        if ok:
            self.add_message(peer_name, "out", self.name, text, secure=True, kind="text")
        return ok, err

    def send_image_to_peer(self, peer_name: str, filename: str, mime: str, data_b64: str):
        try:
            raw_bytes = b64d(data_b64)
        except Exception:
            return False, "La imagen enviada no tiene base64 válido."

        if len(raw_bytes) > MAX_IMAGE_SIZE_BYTES:
            return False, "La imagen supera el tamaño permitido de 4 MB."

        ok, err = self.send_payload_to_peer(peer_name, {
            "kind": "image",
            "filename": filename,
            "mime": mime,
            "data": data_b64,
        })
        if ok:
            self.add_message(
                peer_name,
                "out",
                self.name,
                "",
                secure=True,
                kind="image",
                filename=filename,
                mime=mime,
                data=data_b64,
            )
        return ok, err

    def send_signal_to_peer(self, peer_name: str, signal: dict):
        return self.send_payload_to_peer(peer_name, {
            "kind": "signal",
            "signal": signal,
        })

    async def ws_handler(self, websocket):
        self.ws_clients.add(websocket)
        try:
            await websocket.send(json.dumps({
                "kind": "ws_ready",
                "message": "WebSocket local conectado"
            }))

            async for _message in websocket:
                pass
        finally:
            self.ws_clients.discard(websocket)

    def websocket_server(self):
        async def _main():
            async with websockets.serve(
                self.ws_handler,
                "0.0.0.0",
                self.ws_port,
                max_size=8 * 1024 * 1024,
            ):
                self.ws_ready.set()
                print(f"[WS] WebSocket local disponible en ws://127.0.0.1:{self.ws_port}/ws")
                while not self.stop_event.is_set():
                    await asyncio.sleep(0.5)

        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)
        try:
            self.ws_loop.run_until_complete(_main())
        finally:
            self.ws_loop.close()

    def make_handler(self):
        node = self

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, obj, status=200):
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_html(self, html, status=200):
                html = html.replace("__WS_PORT__", str(node.ws_port))
                data = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path in ("/", "/index.html"):
                    self._send_html(HTML_PAGE)
                    return

                if parsed.path == "/api/state":
                    qs = parse_qs(parsed.query)
                    active = qs.get("active", [""])[0].strip()

                    peers = node.get_peers()
                    active_exists = any(p["name"] == active for p in peers)
                    messages = node.get_messages(active) if active and active_exists else []

                    self._send_json({
                        "me": {
                            "name": node.name,
                            "ip": node.ip,
                            "tcp_port": node.tcp_port,
                            "http_port": node.http_port,
                            "ws_port": node.ws_port,
                            "fingerprint": node.public_fingerprint,
                        },
                        "peers": peers,
                        "active_peer": active if active_exists else (peers[0]["name"] if peers else None),
                        "messages": messages,
                    })
                    return

                self._send_json({"ok": False, "error": "Not Found"}, 404)

            def do_POST(self):
                parsed = urlparse(self.path)

                if parsed.path == "/api/send":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        body = self.rfile.read(length)
                        payload = json.loads(body.decode("utf-8"))
                        peer_name = str(payload.get("to", "")).strip()
                        text = str(payload.get("text", "")).strip()

                        if not peer_name:
                            self._send_json({"ok": False, "error": "Falta el peer destino"}, 400)
                            return
                        if not text:
                            self._send_json({"ok": False, "error": "El mensaje está vacío"}, 400)
                            return

                        ok, err = node.send_text_to_peer(peer_name, text)
                        if ok:
                            self._send_json({"ok": True})
                        else:
                            self._send_json({"ok": False, "error": err}, 500)
                    except Exception as e:
                        self._send_json({"ok": False, "error": str(e)}, 500)
                    return

                if parsed.path == "/api/send-image":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        body = self.rfile.read(length)
                        payload = json.loads(body.decode("utf-8"))

                        peer_name = str(payload.get("to", "")).strip()
                        filename = str(payload.get("filename", "imagen")).strip() or "imagen"
                        mime = str(payload.get("mime", "image/png")).strip() or "image/png"
                        data_b64 = str(payload.get("data", "")).strip()

                        if not peer_name:
                            self._send_json({"ok": False, "error": "Falta el peer destino"}, 400)
                            return
                        if not data_b64:
                            self._send_json({"ok": False, "error": "La imagen está vacía"}, 400)
                            return
                        if not mime.startswith("image/"):
                            self._send_json({"ok": False, "error": "El archivo no es una imagen válida"}, 400)
                            return

                        ok, err = node.send_image_to_peer(peer_name, filename, mime, data_b64)
                        if ok:
                            self._send_json({"ok": True})
                        else:
                            self._send_json({"ok": False, "error": err}, 500)
                    except Exception as e:
                        self._send_json({"ok": False, "error": str(e)}, 500)
                    return

                if parsed.path == "/api/webrtc/signal":
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        body = self.rfile.read(length)
                        payload = json.loads(body.decode("utf-8"))

                        peer_name = str(payload.get("to", "")).strip()
                        signal = payload.get("signal")

                        if not peer_name:
                            self._send_json({"ok": False, "error": "Falta el peer destino"}, 400)
                            return
                        if not isinstance(signal, dict):
                            self._send_json({"ok": False, "error": "Signal inválida"}, 400)
                            return

                        ok, err = node.send_signal_to_peer(peer_name, signal)
                        if ok:
                            self._send_json({"ok": True})
                        else:
                            self._send_json({"ok": False, "error": err}, 500)
                    except Exception as e:
                        self._send_json({"ok": False, "error": str(e)}, 500)
                    return

                self._send_json({"ok": False, "error": "Not Found"}, 404)

            def log_message(self, format, *args):
                return

        return Handler

    def http_server(self):
        handler = self.make_handler()
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", self.http_port), handler)
            self.http_ready.set()
            print(f"[HTTP] Interfaz disponible en http://127.0.0.1:{self.http_port}")
            httpd.serve_forever()
        except OSError as e:
            print(f"[ERROR] No se pudo abrir el servidor HTTP en el puerto {self.http_port}: {e}")

    def start(self):
        threads = [
            threading.Thread(target=self.http_server, daemon=True),
            threading.Thread(target=self.websocket_server, daemon=True),
            threading.Thread(target=self.tcp_server, daemon=True),
            threading.Thread(target=self.discovery_listener, daemon=True),
            threading.Thread(target=self.discovery_broadcaster, daemon=True),
            threading.Thread(target=self.cleanup_stale_peers, daemon=True),
        ]

        for t in threads:
            t.start()

        return threads


def main():
    ap = argparse.ArgumentParser(description="Chat P2P LAN seguro con videollamada WebRTC, imágenes y WebSocket local")
    ap.add_argument("--name", required=True, help="Nombre único del peer, ejemplo: PC1")
    ap.add_argument("--http-port", type=int, default=8081, help="Puerto HTTP de la interfaz web")
    ap.add_argument("--ws-port", type=int, default=8765, help="Puerto WebSocket local para señalización hacia el navegador")
    ap.add_argument("--tcp-port", type=int, default=9100, help="Puerto TCP P2P del chat y señalización")
    ap.add_argument("--discovery-port", type=int, default=9999, help="Puerto UDP broadcast para descubrir peers")
    ap.add_argument("--no-browser", action="store_true", help="No abrir navegador automáticamente")
    args = ap.parse_args()

    node = ChatNode(
        name=args.name,
        http_port=args.http_port,
        tcp_port=args.tcp_port,
        discovery_port=args.discovery_port,
        ws_port=args.ws_port,
    )
    node.start()

    url = f"http://127.0.0.1:{args.http_port}/"
    print(f"[INFO] Peer: {args.name}")
    print(f"[INFO] IP local: {node.ip}")
    print(f"[INFO] UI local: {url}")
    print(f"[INFO] WS local: ws://127.0.0.1:{args.ws_port}/ws")
    print(f"[INFO] TCP P2P: {node.tcp_port}")
    print(f"[INFO] UDP discovery: {node.discovery_port}")
    print(f"[INFO] RSA fingerprint local: {node.public_fingerprint}")
    print("[INFO] Chat, imágenes y señalización WebRTC activos sobre canal P2P cifrado.")
    print("[INFO] La recepción de señales hacia el navegador ahora usa WebSocket local real.")

    if not args.no_browser:
        time.sleep(1)
        if node.http_ready.is_set():
            try:
                webbrowser.open(url)
            except Exception:
                pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop_event.set()
        print("\n[INFO] Cerrando nodo...")


if __name__ == "__main__":
    main()