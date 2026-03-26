# Chat P2P (FastAPI + React)

Aplicacion de chat privado en tiempo real con arquitectura P2P (WebRTC DataChannel).

## Estado actual

- Solo modo P2P.
- El backend se usa para señalizacion WebRTC.
- El intercambio de mensajes y archivos ocurre entre peers por DataChannel.

## Arquitectura

1. El usuario abre el frontend y se registra en señalizacion.
2. El frontend se conecta a `WS /signal/ws?username=...`.
3. El backend publica lista de peers y enruta mensajes de señalizacion (`offer`, `answer`, `ice`).
4. Los clientes establecen `RTCPeerConnection` + `DataChannel`.
5. Mensajes de texto y archivos viajan por P2P, no por relay backend.

## Endpoints

- `GET /health`: estado del servicio, usuarios conectados y contrato.
- `WS /signal/ws?username=...`: canal de señalizacion WebRTC.

## Variables de entorno

Frontend (`frontend/.env`):

- `VITE_SIGNALING_WS_URL` (opcional): URL explicita de señalizacion. Si no existe, se resuelve automaticamente segun el host actual.
- `VITE_DEBUG_P2P` (opcional): `true` para logs detallados de P2P.
- `VITE_ICE_STUN_SERVERS`, `VITE_ICE_TURN_SERVER`, `VITE_ICE_TURN_USERNAME`, `VITE_ICE_TURN_PASSWORD` (opcionales): configuracion ICE.

Backend:

- `CHAT_HOST` (opcional, default `0.0.0.0`)
- `CHAT_PORT` (opcional, default `8000`)

## Ejecucion local

### Backend

```powershell
cd "D:\UTP\SEMESTRE 6\SISTEMAS DISTRIBUIDOS\chat_web_sockets"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ws_server.py
```

Alternativa:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (desarrollo)

```powershell
cd "D:\UTP\SEMESTRE 6\SISTEMAS DISTRIBUIDOS\chat_web_sockets\frontend"
npm install
npm run dev
```

Abre `http://localhost:5173`.

### Build integrado

```powershell
cd "D:\UTP\SEMESTRE 6\SISTEMAS DISTRIBUIDOS\chat_web_sockets\frontend"
npm install
npm run build

cd ..
.\.venv\Scripts\Activate.ps1
python ws_server.py
```

Abre `http://localhost:8000`.

## Verificacion rapida

1. Levanta backend y frontend.
2. Abre dos clientes con usuarios distintos.
3. Envía texto y archivo.
4. Verifica que aparezca estado de conexion P2P activa entre peers.
