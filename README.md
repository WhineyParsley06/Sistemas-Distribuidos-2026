# Chat P2P (FastAPI + React)

Aplicacion de chat privado en tiempo real con arquitectura P2P (WebRTC DataChannel).

---

## Explicacion general de la logica

Este proyecto implementa un **chat privado peer-to-peer (P2P)**. A diferencia de un chat tradicional donde todos los mensajes pasan por el servidor, aqui el servidor actua solo como **intermediario de señalizacion** para que los navegadores se encuentren entre si. Una vez establecida la conexion, **los mensajes y archivos viajan directamente entre navegadores** sin pasar por el servidor.

### Flujo completo paso a paso

```
Usuario A (navegador)                  Backend (FastAPI)              Usuario B (navegador)
        |                                      |                               |
        |-- WS /signal/ws?username=A --------->|                               |
        |<-- signal_registered {username:"A"} -|                               |
        |                                      |<-- WS /signal/ws?username=B --|
        |                                      |-- signal_registered --------->|
        |<-- signal_peer_list {users:[A,B]} ----|-- signal_peer_list {users:[A,B]} -->|
        |                                      |                               |
        |-- (Usuario A quiere hablar con B)    |                               |
        |   crea RTCPeerConnection + DataChannel                               |
        |-- signal_offer {to:"B", payload:SDP} ->                              |
        |                                      |-- signal_offer {from:"A"} --->|
        |                                      |   (B crea RTCPeerConnection)  |
        |                                      |<-- signal_answer {to:"A"} ----|
        |<-- signal_answer {from:"B"} ---------|                               |
        |                                      |                               |
        |<-- signal_ice_candidate (intercambio de candidatos ICE) ------------>|
        |                                      |                               |
        |====== DataChannel ABIERTO (conexion P2P directa) ===================>|
        |                                      |                               |
        |-- {kind:"text", message:"Hola!"} --> (directo, sin pasar backend) -->|
        |-- {kind:"file", content:base64} ---> (directo, sin pasar backend) -->|
```

### Conceptos clave

| Concepto | Descripcion |
|---|---|
| **WebSocket de señalizacion** | Canal permanente entre cada navegador y el backend. Solo sirve para intercambiar SDP e ICE candidates. |
| **SDP (Session Description Protocol)** | Descripcion de capacidades multimedia. La "oferta" (offer) la crea quien inicia la conexion; la "respuesta" (answer) la genera quien la recibe. |
| **ICE (Interactive Connectivity Establishment)** | Protocolo para descubrir como dos peers pueden conectarse directamente (IP local, IP publica via STUN, o relay via TURN). |
| **STUN** | Servidor que le dice al navegador cual es su IP publica. Permite conexiones directas entre peers en redes diferentes. |
| **TURN** | Servidor relay de ultimo recurso cuando la conexion directa no es posible (firewalls muy restrictivos). |
| **RTCPeerConnection** | API del navegador que gestiona toda la negociacion WebRTC. |
| **DataChannel** | Canal de datos bidireccional sobre la conexion P2P. Por aqui viajan los mensajes y archivos. |
| **Heartbeat** | Ping periodico enviado por el DataChannel para detectar conexiones muertas antes de que el navegador lo reporte. |
| **Reconexion exponencial** | Si se pierde la conexion, se reintenta con delays crecientes: 500ms, 1s, 2s, 4s... hasta 30s, con maximo 5 intentos. |

---

## Descripcion de archivos — Backend

El backend esta construido con **FastAPI** (Python) y su unica responsabilidad es gestionar el servidor de señalizacion WebRTC.

```
backend/
├── __init__.py                      # Marca el directorio como paquete Python
├── main.py                          # Punto de entrada: crea y configura la app FastAPI
├── container.py                     # Contenedor de dependencias: instancia global del SignalingManager
├── core/
│   ├── __init__.py
│   └── config.py                    # Configuracion de la aplicacion (host, puerto, modo de transporte)
├── api/
│   ├── __init__.py
│   ├── contracts/
│   │   ├── __init__.py
│   │   └── signaling_v1.py          # Constantes del protocolo de señalizacion (tipos de mensajes)
│   └── routes/
│       ├── __init__.py
│       ├── health.py                # Endpoint GET /health
│       └── signaling.py             # Endpoint WebSocket WS /signal/ws
├── services/
│   ├── __init__.py
│   └── signaling_manager.py         # Logica central: registro de peers y enrutamiento de señales
└── web/
    ├── __init__.py
    └── static_files.py              # Sirve el build del frontend como archivos estaticos
```

### `backend/main.py`
Crea la aplicacion FastAPI usando el patron factory (`create_app()`). Registra el middleware CORS (permite peticiones desde cualquier origen), incluye los routers de health y señalizacion, y monta el frontend estatico. Si se ejecuta directamente, lanza Uvicorn.

### `backend/container.py`
Contenedor de inyeccion de dependencias minimalista. Crea una unica instancia global de `SignalingManager` que es compartida por todos los endpoints. Esto garantiza que todos los peers conectados sean visibles desde cualquier ruta.

### `backend/core/config.py`
Define la clase `Settings` con la configuracion del servidor: `host` (default `0.0.0.0`), `port` (default `8000`, configurable via variable de entorno `PORT` o `CHAT_PORT`) y `transport_mode` (siempre `"p2p"`). Usa `@lru_cache` para crear la configuracion una sola vez.

### `backend/api/contracts/signaling_v1.py`
Define todas las constantes de string del protocolo de mensajeria:
- `signal_registered`: el servidor confirma el nombre de usuario asignado al cliente
- `signal_peer_list`: lista actualizada de todos los usuarios conectados
- `signal_offer` / `signal_answer` / `signal_ice_candidate`: mensajes WebRTC para establecer la conexion P2P
- `signal_ping` / `signal_pong`: keepalive del WebSocket de señalizacion
- `signal_disconnect`: cierre graceful de la conexion
- `signal_error`: notificacion de error al cliente

### `backend/api/routes/health.py`
Expone el endpoint `GET /health`. Devuelve el estado del servicio, la lista de usuarios actualmente conectados, el modo de transporte y la version del contrato de señalizacion. Util para monitoreo y depuracion.

### `backend/api/routes/signaling.py`
El corazon del backend. Expone el endpoint `WebSocket /signal/ws?username=...`. Gestiona el ciclo de vida completo de cada cliente:
1. Al conectar: llama a `SignalingManager.connect()` para registrar al peer.
2. Bucle de recepcion: valida cada mensaje recibido, maneja ping/pong, y enruta los mensajes de señalizacion al peer destino usando `SignalingManager.send_to()`.
3. Al desconectar (voluntario o por error): llama a `SignalingManager.disconnect()` para limpiar el registro y notificar a los demas peers.

### `backend/services/signaling_manager.py`
Gestiona el estado de todos los peers conectados. Mantiene dos diccionarios sincronizados: `peers` (nombre → WebSocket) y `sockets` (WebSocket → nombre). Usa un `asyncio.Lock` para evitar condiciones de carrera en entornos asíncronos. Sus metodos principales son:
- `connect()`: acepta la conexion, resuelve nombres duplicados (agrega sufijo `_2`, `_3`...), envia confirmacion y difunde la lista actualizada.
- `disconnect()`: elimina al peer de los registros y difunde la lista actualizada.
- `broadcast_peer_list()`: envia la lista de usuarios a todos los conectados.
- `send_to()`: enruta un mensaje JSON a un peer especifico por nombre.

### `backend/web/static_files.py`
Si existe el directorio `frontend/dist/` (generado por `npm run build`), monta el frontend compilado como archivos estaticos. El endpoint `GET /` sirve el `index.html`. Los assets del frontend se sirven bajo `/assets/`. Esto permite desplegar toda la aplicacion desde un solo servidor.

### `ws_server.py` (raiz del proyecto)
Script de arranque alternativo en la raiz del proyecto. Lee la configuracion y lanza Uvicorn apuntando a `backend.main:app`. Equivalente a ejecutar directamente `backend/main.py`.

---

## Descripcion de archivos — Frontend

El frontend esta construido con **React** + **Vite**. Implementa toda la logica WebRTC del lado del cliente.

```
frontend/
├── index.html                                   # HTML base de la SPA
├── package.json                                 # Dependencias y scripts npm
├── vite.config.js                               # Configuracion del bundler Vite
├── eslint.config.js                             # Reglas de linting JavaScript
├── .env.example                                 # Plantilla de variables de entorno
└── src/
    ├── main.jsx                                 # Punto de entrada React: monta <App> en el DOM
    ├── App.jsx                                  # Componente raiz: orquesta UI y logica de conexion
    ├── App.css                                  # Estilos de la aplicacion
    ├── index.css                                # Estilos globales / reset CSS
    ├── config/
    │   └── transport.js                         # Constante del modo de transporte (siempre "p2p")
    └── features/
        └── chat/
            ├── components/
            │   ├── TopBar.jsx                   # Barra superior: login, estado de conexion
            │   ├── UsersPanel.jsx               # Panel lateral: lista de peers disponibles
            │   ├── MessageList.jsx              # Lista de mensajes del chat
            │   ├── Composer.jsx                 # Caja de texto y botones de envio
            │   ├── PeerConnectionStatus.jsx     # Indicador de estado de cada conexion P2P
            │   └── ConnectionDiagnostics.jsx    # Panel de diagnosticos ICE y WebRTC
            ├── hooks/
            │   └── useChatConnection.js         # Hook principal: toda la logica WebRTC y señalizacion
            └── utils/
                ├── iceConfig.js                 # Configuracion de servidores STUN/TURN
                ├── resilience.js                # Reconexion automatica, heartbeat y cleanup
                └── fileTransfer.js              # Codificacion/decodificacion de archivos en Base64
```

### `frontend/src/main.jsx`
Punto de entrada de React. Monta el componente `<App>` dentro del elemento `#root` del HTML usando `createRoot`. Envuelve la app en `<StrictMode>` para detectar problemas en desarrollo.

### `frontend/src/App.jsx`
Componente raiz que orquesta toda la interfaz. Resuelve automaticamente la URL del servidor de señalizacion segun el entorno (local vs produccion). Usa el hook `useChatConnection` para obtener el estado y los metodos de conexion, y los distribuye a los componentes hijos. Renderiza el layout completo: barra superior, panel de usuarios, lista de mensajes, compositor, estado P2P y diagnosticos.

### `frontend/src/config/transport.js`
Modulo de configuracion simple. Exporta la constante `TRANSPORT_MODES.P2P = "p2p"` y la funcion `getTransportMode()` que siempre devuelve `"p2p"`. Centraliza el modo de transporte para facilitar futuras extensiones.

### `frontend/src/features/chat/hooks/useChatConnection.js`
El hook mas importante del proyecto. Encapsula toda la logica de red:

1. **Señalizacion WebSocket**: abre y mantiene viva la conexion con el servidor. Implementa reconexion automatica con backoff exponencial si el servidor cae.
2. **Negociacion WebRTC**: cuando el usuario intenta enviar un mensaje a un peer sin conexion activa, crea un `RTCPeerConnection`, genera un SDP offer, lo envia via señalizacion, y espera el answer.
3. **DataChannel**: configura el canal de datos P2P para enviar y recibir mensajes de texto y archivos.
4. **Heartbeat**: cada 5 segundos envia un ping por el DataChannel. Si se pierden 3 pings seguidos, declara la conexion muerta y dispara la reconexion.
5. **Reconexion de peers**: usa `PeerReconnectionManager` para reintentar la conexion P2P hasta 5 veces con backoff exponencial.
6. **Diagnosticos (Fase 4)**: actualiza estados reactivos con metricas de cada conexion para mostrarlas en la UI.

Expone: `connected`, `myUsername`, `users`, `messages`, `peerConnectionStates`, `diagnosticsByPeer`, `reconnectionStatusByPeer`, `iceInfoByPeer`, `allPeers`, `connect`, `disconnect`, `sendText`, `sendFile`.

### `frontend/src/features/chat/utils/iceConfig.js`
Construye el objeto `RTCConfiguration` con los servidores ICE. Por defecto usa 5 servidores STUN publicos de Google, Mozilla y stunprotocol.org. Permite sobreescribir los servidores mediante variables de entorno (`VITE_ICE_STUN_SERVERS`, `VITE_ICE_TURN_SERVER`, etc.). Tambien exporta `getIceServerDebugInfo()` que devuelve un resumen de los servidores configurados para los diagnosticos de la UI.

### `frontend/src/features/chat/utils/resilience.js`
Contiene las herramientas de recuperacion ante fallos:
- **`calculateBackoff(attempt)`**: calcula el delay para el intento N con formula exponencial (`500ms * 2^N`, maximo 30s).
- **`PeerReconnectionManager`**: clase que ejecuta hasta 5 reintentos de reconexion P2P con backoff exponencial. Llama a `onReconnect` en cada intento y a `onGiveUp` si se agotan.
- **`HeartbeatMonitor`**: clase que envia `{kind:"heartbeat"}` por el DataChannel cada 5s. Si falla 3 veces seguidas, llama a `onDead` para disparar la reconexion.
- **`cleanupPeerResources(pc, channel)`**: cierra de forma segura un `RTCPeerConnection` y su `DataChannel` previniendo memory leaks.
- **`diagnoseConnectionHealth(pc, channel, peerName)`**: toma una "fotografia" del estado actual de una conexion (estado RTC, ICE, señalizacion, DataChannel) e indica si esta saludable.

### `frontend/src/features/chat/utils/fileTransfer.js`
Dos funciones para la transferencia de archivos:
- **`encodeFileAsBase64(file)`**: lee un `File` del navegador con `FileReader` y devuelve su contenido como string Base64 (sin el prefijo `data:...`).
- **`downloadBase64File(file)`**: dado un objeto `{content, name, mimeType}`, decodifica el Base64 a bytes, crea un `Blob`, genera una URL temporal y simula un click en un enlace `<a download>` para forzar la descarga en el navegador del receptor.

### `frontend/src/features/chat/components/TopBar.jsx`
Barra de navegacion superior. Muestra el titulo de la app y el modo de transporte. Si el usuario no esta conectado, muestra un input de nombre de usuario y el boton "Conectar". Si ya esta conectado, muestra el nombre asignado por el servidor y el boton "Salir".

### `frontend/src/features/chat/components/UsersPanel.jsx`
Panel lateral que muestra un `<select>` con la lista de peers disponibles (todos los usuarios conectados excepto el propio). El usuario selecciona aqui a quien quiere enviarle un mensaje. Se deshabilita si no hay conexion o no hay otros usuarios.

### `frontend/src/features/chat/components/MessageList.jsx`
Lista scrolleable de todos los mensajes del chat. Renderiza cada mensaje con una clase CSS segun su tipo (`sent`, `received`, `system`, `error`, `file`). Los mensajes de tipo `file` incluyen un boton "Descargar" que llama a `downloadBase64File`.

### `frontend/src/features/chat/components/Composer.jsx`
Caja de composicion de mensajes. Contiene un input de texto (con soporte para Enter), el boton "Enviar" y el boton "Archivo" que abre un `<input type="file">` oculto. Todos los controles se deshabilitan si no hay conexion activa o no hay un peer destino seleccionado.

### `frontend/src/features/chat/components/PeerConnectionStatus.jsx`
Tarjeta visual para cada peer conectado. Muestra un indicador de color (verde=conectado, azul=conectando, naranja=desconectado, rojo=fallido, gris=cerrado), el estado del DataChannel, una insignia de "Reconectando X/5" si hay un reintento activo, y metricas de diagnostico (RTCState, ICEState, latencia).

### `frontend/src/features/chat/components/ConnectionDiagnostics.jsx`
Panel expandible de diagnosticos detallados. Para cada peer muestra una cuadricula con los estados de `RTCPeerConnection`, ICE, Signaling y DataChannel, ademas de la lista de servidores ICE configurados (STUN y TURN). Incluye un tip para ver logs detallados en DevTools.

---

## Endpoints

- `GET /health`: estado del servicio, usuarios conectados y contrato.
- `WS /signal/ws?username=...`: canal de señalizacion WebRTC.

## Variables de entorno

Frontend (`frontend/.env`):

- `VITE_SIGNALING_WS_URL` (opcional): URL explicita de señalizacion. Si no existe, se resuelve automaticamente segun el host actual.
- `VITE_DEBUG_P2P` (opcional): `true` para logs detallados de P2P en consola.
- `VITE_ICE_STUN_SERVERS` (opcional): lista de STUN servers separados por comas.
- `VITE_ICE_TURN_SERVER`, `VITE_ICE_TURN_USERNAME`, `VITE_ICE_TURN_PASSWORD` (opcionales): configuracion del servidor TURN.

Backend:

- `CHAT_HOST` (opcional, default `0.0.0.0`)
- `PORT` / `CHAT_PORT` (opcional, default `8000`)

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
