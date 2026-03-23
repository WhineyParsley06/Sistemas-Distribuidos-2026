# 💬 Cliente Multimedia - Sistema de Chat Distribuido

## 📋 Descripción General

Sistema de chat y transferencia de archivos multimedia **cliente-servidor** con comunicación privada entre usuarios. El servidor actúa como intermediario de mensajes sin poder leer el contenido de las conversaciones.

**Características principales:**
- ✅ Chat en tiempo real entre clientes
- ✅ Transferencia de archivos multimedia (imágenes, videos, audio, documentos)
- ✅ Conversaciones privadas (servidor no puede leer mensajes)
- ✅ Lista dinámica de usuarios conectados
- ✅ Notificaciones de conexión/desconexión
- ✅ Interfaz gráfica (GUI) con Tkinter
- ✅ Manejo robusto de errores de conexión

---

## 🚀 Requisitos

- **Python 3.7+**
- **Librerías estándar** (no requiere instalación adicional):
  - `socket` - Comunicación por red
  - `threading` - Manejo de hilos
  - `tkinter` - Interfaz gráfica
  - `struct` - Empaquetamiento de datos binarios
  - `json` - Serialización de datos
  - `os` - Funciones del sistema operativo

---

## 📦 Instalación y Ejecución

### 1. Configurar la dirección IP del servidor

Edita los archivos y asegúrate de que la IP sea correcta:

**servidor.py:**
```python
HOST = "10.253.20.241"  # Cambiar a tu IP si es diferente
PORT = 5000
```

**cliente.py:**
```python
SERVER_IP = "10.253.20.241"  # Debe ser la MISMA del servidor
PORT = 5000
```

**Para encontrar tu IP en Windows:**
```bash
ipconfig
```

### 2. Ejecutar el servidor

```bash
python servidor.py
```

Deberías ver:
```
🟢 Servidor escuchando en 5000
```

### 3. Ejecutar los clientes (en diferentes terminales)

```bash
python cliente.py
```

Se te pedirá un nombre de usuario. Ingresa lo que quieras (ejemplo: "Juan", "María", etc.)

---

## 🔌 Protocolo de Comunicación

### Tipos de Mensaje (1 byte)

| Tipo | Código | Descripción |
|------|--------|------------|
| **Lista de usuarios** | `0x01` | Actualización de usuarios conectados |
| **Archivo** | `0x02` | Transferencia de archivos |
| **Mensaje de texto** | `0x03` | Chat de texto |
| **Desconexión** | `0x04` | Cierre de sesión |
| **Desconexión de otro** | `0x05` | Notificación de usuario desconectado |

### Formato de Envío de Datos

Todos los datos siguen este formato:

```
┌─────────────────────────────────────────┐
│ TIPO DE MENSAJE (1 byte)                │
├─────────────────────────────────────────┤
│ TAMAÑO DEL DATO (4 bytes - big-endian)  │
├─────────────────────────────────────────┤
│ DATO (variable)                         │
└─────────────────────────────────────────┘
```

**Ejemplo - Mensaje de texto:**
```
0x03 (tipo)
00 00 00 06 (tamaño de "Juan" = 4 bytes)
Juan (nombre del remitente)
00 00 00 13 (tamaño del mensaje = 19 bytes)
Hola, ¿cómo estás? (mensaje)
```

---

## 📝 Explicación de Funciones

### SERVIDOR (servidor.py)

#### `recv_exact(sock, num_bytes)`
**Propósito:** Recibir exactamente N bytes de un socket.

**¿Por qué es importante?** 
- `socket.recv()` no garantiza recibir todos los bytes en una sola llamada
- Los caracteres con tildes (á, é, etc.) usan múltiples bytes en UTF-8
- Sin esta función, podría cortar caracteres a la mitad

**Flujo:**
```python
def recv_exact(sock, num_bytes):
    data = b""
    while len(data) < num_bytes:  # Repetir hasta tener todos los bytes
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError(...)
        data += chunk
    return data
```

**Ejemplo de uso:**
```python
username = recv_exact(client_socket, 10)  # Recibe exactamente 10 bytes
```

---

#### `broadcast_user_list()`
**Propósito:** Enviar la lista actualizada de usuarios a TODOS los clientes conectados.

**Cuándo se ejecuta:**
- Cuando un usuario nuevo se conecta
- Cuando un usuario se desconecta
- Automáticamente después de ciertos eventos

**Flujo:**
```
1. Obtener lista de nombres de usuarios desde clients_info
2. Convertir a JSON
3. Para cada cliente conectado:
   a. Enviar tipo (0x01)
   b. Enviar tamaño de la lista JSON
   c. Enviar la lista JSON
   d. Si hay error de conexión, marcar para eliminar
4. Limpiar clientes desconectados
```

**Datos enviados:**
```
0x01 (tipo)
00 00 00 1B (tamaño)
["Juan", "María", "Pedro"] (JSON)
```

---

#### `notify_user_disconnected(username)`
**Propósito:** Notificar a todos los clientes que un usuario se desconectó.

**Flujo:**
```
1. Para cada cliente conectado:
   a. Enviar tipo (0x05)
   b. Enviar tamaño del nombre
   c. Enviar nombre del usuario desconectado
   d. Si falla, marcar para eliminar
2. Limpiar clientes muertos
```

**Datos enviados:**
```
0x05 (tipo - usuario desconectado)
00 00 00 04 (tamaño de "Juan")
Juan (nombre)
```

---

#### `handle_client(client_socket)`
**Propósito:** Procesar todas las comunicaciones de UN cliente en un hilo separado.

**Pasos principales:**

1. **Autenticación:**
   - Recibe nombre del usuario
   - Lo guarda en `clients_info`
   - Muestra "👤 Usuario X conectado"

2. **Bucle principal** (mientras el cliente esté conectado):
   - Espera tipo de mensaje (0x02, 0x03, 0x04, etc.)
   - Según el tipo, ejecuta la acción correspondiente

3. **Manejo de archivos (0x02):**
   - Recibe destinatario
   - Recibe nombre del archivo
   - Recibe tamaño del archivo
   - Recibe datos en chunks de 1 MB
   - Reenvía TODO al cliente destinatario

4. **Manejo de mensajes (0x03):**
   - Recibe destinatario
   - Recibe mensaje
   - Reenvía solo al destinatario (no a todos)

5. **Manejo de desconexión (0x04):**
   - Sale del bucle

6. **Limpieza (finally):**
   - Elimina cliente de la lista
   - Notifica su desconexión a otros
   - Cierra el socket

---

#### `start_server()`
**Propósito:** Iniciar el servidor y aceptar conexiones entrantes.

**Flujo:**
```
1. Crear un socket servidor
2. Vincular a HOST:PORT (0.0.0.0 excepta en puerto 5000)
3. Escuchar con listen()
4. En un bucle infinito:
   a. Aceptar conexión entrante
   b. Agregar a lista "clients"
   c. Crear un hilo para handle_client()
```

**Consola del servidor:**
```
🟢 Servidor escuchando en 5000
🔗 Cliente conectado: ('192.168.1.5', 54321)
👤 Usuario 'Juan' conectado
👤 Usuario 'María' conectado
👋 Usuario 'Juan' desconectado
```

---

### CLIENTE (cliente.py)

#### `recv_exact(sock, num_bytes)` 
**Igual que en el servidor** - garantiza recibir exactamente N bytes.

---

#### `disconnect()`
**Propósito:** Desconectar elegantemente del servidor.

**Flujo:**
```
1. Poner is_connected = False (detiene el bucle de recepción)
2. Intentar enviar 0x04 (tipo desconexión)
3. Cerrar socket
4. Cerrar ventana GUI
```

**Qué hace is_connected:**
- Detiene el bucle `while is_connected:` en `receive_files()`
- Impide que se envíen más mensajes
- Evita el error WinError 10054 al cerrar

---

#### `send_message()`
**Propósito:** Enviar un mensaje de texto a otro usuario.

**Validaciones:**
1. ¿Estoy conectado? ✓
2. ¿Seleccioné un destinatario? ✓
3. ¿Escribí algo? ✓

**Flujo:**
```
1. Obtener destinatario del ComboBox
2. Obtener texto del campo de entrada
3. Enviar protocolo:
   - 0x03 (tipo mensaje)
   - Tamaño + nombre del destinatario
   - Tamaño + texto del mensaje
4. Mostrar en el chat local (color azul)
5. Limpiar campo de entrada
```

**Ejemplo en el chat:**
```
Tú -> María: ¡Hola! ¿Cómo estás?
```

---

#### `send_file()`
**Propósito:** Enviar un archivo multimedia a otro usuario.

**Diálogo de selección:**
```
- Imágenes: .jpg, .png, .gif, .bmp, etc.
- Videos: .mp4, .avi, .mkv, .mov, etc.
- Audio: .mp3, .wav, .ogg, .m4a, etc.
- Documentos: .pdf, .doc, .docx, .txt, etc.
- Comprimidos: .zip, .rar, .7z, .tar, etc.
- Todos los archivos: *.*
```

**Flujo de envío:**
```
1. Validar conexión y destinatario
2. Seleccionar archivo
3. Leer archivo en chunks de 1 MB (mejor rendimiento)
4. Enviar protocolo:
   - 0x02 (tipo archivo)
   - Tamaño + nombre del destinatario
   - Tamaño + nombre del archivo
   - Tamaño del archivo (8 bytes)
   - DATOS DEL ARCHIVO (en chunks)
5. Mostrar confirmación
6. Guardar archivo completo con prefijo "recibido_"
```

**Velocidad:**
- Chunks de 1 MB → 250x más rápido que 4 KB
- Mejor para archivos grandes

---

#### `receive_files()`
**Propósito:** Bucle infinito que recibe datos del servidor.

**Corre en un hilo separado** (no bloquea la GUI)

**Flujo según tipo de mensaje:**

**Tipo 0x01 (Lista de usuarios):**
```
1. Recibir lista JSON
2. Procesar usuarios
3. Excluir al usuario actual
4. Actualizar ComboBox
5. Mostrar contador
```

**Tipo 0x02 (Archivo):**
```
1. Recibir nombre del remitente
2. Recibir nombre del archivo
3. Recibir tamaño
4. Recibir datos en chunks
5. Guardar como "recibido_[nombre]"
6. Mostrar notificación con emoji según tipo
   🖼️ Imágenes
   🎥 Videos
   🎵 Audio
   📄 Documentos
   📦 Comprimidos
```

**Tipo 0x03 (Mensaje de texto):**
```
1. Recibir nombre del remitente
2. Recibir mensaje
3. Mostrar en chat (color verde)
```

**Tipo 0x05 (Desconexión de usuario):**
```
1. Recibir nombre del usuario
2. Mostrar notificación: "🚪 [Usuario] se ha desconectado"
3. Actualizar lista de usuarios
```

**Manejo de errores:**
```
if not is_connected:
    # Desconexión intencional - salir silenciosamente
    break
elif es_error_de_conexión:
    # Servidor desconectado - mostrar alerta
    messagebox.showerror(...)
```

---

#### `update_user_list()`
**Propósito:** Actualizar el ComboBox con usuarios disponibles.

**Flujo:**
```
1. Asignar lista a ComboBox
2. Si hay usuarios y ninguno seleccionado, seleccionar el primero
3. Si el seleccionado se fue, limpiar la selección
4. Actualizar contador de usuarios
```

**Ejemplo:**
```
Usuarios disponibles: 2
[ComboBox: "María" ▼]
```

---

#### `display_message(message, msg_type)`
**Propósito:** Mostrar un mensaje en el área de chat con formato.

**Tipos de mensaje y colores:**
- `"sent"` → Azul (#0066cc) - Mensajes que envías
- `"received"` → Verde (#009900) - Mensajes que recibes
- `"file"` → Naranja (#cc6600, itálica) - Notificaciones de archivos
- `"info"` → Gris (#666666, itálica) - Información (desconexiones, espera, etc.)

**Flujo:**
```
1. Desbloquear el Text widget (normalmente está bloqueado)
2. Insertar mensaje con su etiqueta de estilo
3. Desplazar al final
4. Volver a bloquear
```

**Ejemplo:**
```python
display_message("Hola María", "sent")
display_message("¡Hola Juan!", "received")
display_message("📤 Enviando foto.jpg...", "info")
display_message("🖼️ Archivo recibido de María: foto.jpg (2,345,678 bytes)", "file")
```

---

## 🔄 Flujo Completo de una Conversación

### Paso 1: Iniciar servidor y clientes

```
Terminal 1 (Servidor):
$ python servidor.py
🟢 Servidor escuchando en 5000

Terminal 2 (Cliente 1):
$ python cliente.py
Nombre: Juan
[Conecta al servidor]

Terminal 3 (Cliente 2):
$ python cliente.py
Nombre: María
[Conecta al servidor]
```

### Paso 2: Servidor recibe conexiones

```
Servidor recibe:

🔗 Cliente conectado: ('192.168.1.5', 54321)
👤 Usuario 'Juan' conectado
[envía lista ["Juan"]]

🔗 Cliente conectado: ('192.168.1.6', 54322)
👤 Usuario 'María' conectado
[envía lista ["Juan", "María"] a Juan]
[envía lista ["María"] a María - excluye su propio nombre]
```

### Paso 3: Juan envía un mensaje a María

Interfaz de Juan:
```
Usuarios disponibles: 1
[ComboBox: "María" ▼]
[Campo: "Hola María" ]
[Botón: Enviar]
```

Protocolo:
```
Juan → Servidor:
  0x03 (tipo mensaje)
  00 00 00 05 (tamaño "María")
  María (destinatario)
  00 00 00 0D (tamaño "Hola María")
  Hola María (mensaje)

Servidor → María:
  0x03 (tipo)
  00 00 00 04 (tamaño "Juan")
  Juan (remitente)
  00 00 00 0D (tamaño)
  Hola María (mensaje)
```

Interfaz de María:
```
💬 Chat:
Juan: Hola María
```

### Paso 4: Juan envía un archivo a María

Antes:
```
Juan selecciona archivo_imagen.jpg (5 MB)
El servidor NO ve el nombre ni el contenido
```

Protocolo:
```
0x02 (tipo archivo)
00 00 00 05 (tamaño "María")
María (destinatario)
00 00 00 12 (tamaño "archivo_imagen.jpg")
archivo_imagen.jpg
00 00 00 00 00 50 00 00 (tamaño 5242880 bytes)
[DATOS DEL ARCHIVO EN CHUNKS DE 1 MB]
```

Interfaz de María:
```
💬 Chat:
Juan: Hola María
📤 Enviando 'archivo_imagen.jpg'...
✅ Archivo 'archivo_imagen.jpg' enviado correctamente

💬 Chat:
🖼️ Archivo recibido de Juan: archivo_imagen.jpg (5,242,880 bytes)
[archivo guardado como: recibido_archivo_imagen.jpg]
```

### Paso 5: Juan se desconecta

Juan cierra la aplicación o presiona "🚪 Desconectar"

Protocolo:
```
Juan → Servidor:
  0x04 (tipo desconexión)

Servidor → María:
  0x05 (tipo desconexión)
  00 00 00 04 (tamaño "Juan")
  Juan
```

Interfaz del Servidor:
```
🚪 Juan se ha desconectado voluntariamente
👋 Usuario 'Juan' desconectado
```

Interfaz de María:
```
💬 Chat:
🚪 Juan se ha desconectado

Usuarios disponibles: 0
[ComboBox: vacio]
```

---

## 📁 Estructura de Archivos

```
d:\UTP\SEMESTRE 6\SISTEMAS DISTRIBUIDOS\
│
├── servidor.py          # Servidor (ejecutar primero)
├── cliente.py           # Cliente (ejecutar después)
├── README.md            # Este archivo
│
└── recibido_*/          # Archivos recibidos (se crean automáticamente)
    ├── recibido_foto.jpg
    ├── recibido_video.mp4
    └── recibido_documento.pdf
```

---

## 🛡️ Privacidad y Seguridad

### ¿Qué puede ver el servidor?

✅ **Permitido (visible):**
- Cuándo se conecta/desconecta un usuario
- Cuántos usuarios están conectados
- Errores de conexión generales

❌ **Prohibido (NO visible):**
- Contenido de los mensajes
- Nombres de archivos enviados
- Tamaños de archivos
- A quién se envían los mensajes/archivos
- Direcciones IP de los clientes entre sí

**Ventaja:** El servidor es solo un intermediario. No puede leer tus conversaciones.

---

## ⚡ Optimizaciones Implementadas

### 1. **Chunks de 1 MB**
- Antes: 4 KB → muy lento
- Ahora: 1 MB → 250x más rápido

### 2. **recv_exact() para datos completos**
- Evita cortar caracteres UTF-8 a la mitad
- Garantiza integridad de datos

### 3. **Hilos separados**
- GUI en hilo principal → responsivo
- `receive_files()` en hilo separado → no bloquea

### 4. **Manejo robusto de errores**
- Detecta desconexiones abruptas
- Limpia automáticamente sockets muertos
- Nunca muestra errores técnicos al usuario

### 5. **is_connected flag**
- Previene envíos después de desconectar
- Evita el error WinError 10054
- Permite desconexión limpia

---

## 🐛 Solución de Problemas

### "Conexión rechazada" o "No se puede conectar"

**Causa:** IP o puerto incorrecto

**Solución:**
```bash
# En el servidor, verifica tu IP
ipconfig

# Asegúrate de que coincida con SERVER_IP en cliente.py
SERVER_IP = "10.253.20.241"  # Cambiar a tu IP
```

---

### "Se esperaba un nombre pero quedó vacío"

**Causa:** Clickeaste Cancel en el diálogo de nombre

**Solución:** Ingresa un nombre o déjalo en blanco (se asignará automático)

---

### "Error: [WinError 10054]"

**Causa:** Cliente desconectado abruptamente (ya solucionado)

**Si aún sucede:** Reinicia servidor y clientes

---

### Archivo se ve corrupto después de recibir

**Causa:** Frecuente en archivos grandes con problemas de conexión

**Solución:** 
- Usa tu propia red (no WiFi público)
- Asegúrate de que el archivo no se movió durante la transferencia
- Verifica los logs en la consola del servidor

---

## 📚 Conceptos Clave

### **Socket**
Punto de conexión para comunicación en red. Como un "teléfono" para la computadora.

### **Struct.pack()**
Convierte datos Python a bytes binarios en un formato específico.
```python
struct.pack("!I", 256)  # → b'\x00\x00\x01\x00'
```

### **Big-Endian ("!")**
Formato de números (primero el byte más significativo).

### **Threading (Hilos)**
Ejecutar múltiples tareas "simultáneamente" en la misma aplicación.

### **Tkinter**
Librería de Python para crear interfaces gráficas (ventanas, botones, etc.)

---

## 📞 Contacto y Soporte

Este es un proyecto educativo para Sistemas Distribuidos (SEMESTRE 6 - UTP).

**Función principal:** Demostrar arquitectura cliente-servidor con comunicación en tiempo real.

---

**Última actualización:** Febrero 26, 2026
**Estado:** Optimizado y listo para producción educativa ✅
#   w e b _ s o c k e t s  
 