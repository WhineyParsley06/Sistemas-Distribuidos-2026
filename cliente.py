import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import struct
import os
import json

SERVER_IP = "10.253.60.28"
PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((SERVER_IP, PORT))

# Solicitar nombre de usuario
username = simpledialog.askstring("Nombre de usuario", "Ingresa tu nombre de usuario:")
if not username:
    username = "Usuario" + str(os.getpid())

# Enviar nombre al servidor
client.sendall(struct.pack("!I", len(username)))
client.sendall(username.encode())

# Lista de usuarios conectados
available_users = []

# Bandera para controlar el estado de la conexión
is_connected = True

def recv_exact(sock, num_bytes):
    """Recibe exactamente num_bytes bytes del socket"""
    data = b""
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError("Conexión cerrada antes de recibir todos los datos")
        data += chunk
    return data

def disconnect():
    """Desconectar del servidor y cerrar la aplicación"""
    global is_connected
    is_connected = False
    
    try:
        # Enviar mensaje de desconexión al servidor
        client.sendall(b'\x04')  # Tipo: desconexión
    except:
        pass
    finally:
        try:
            client.close()
        except:
            pass
        root.destroy()

def send_message():
    """Envía un mensaje de texto al destinatario seleccionado"""
    if not is_connected:
        messagebox.showwarning("Desconectado", "No estás conectado al servidor")
        return
    
    destination = user_combo.get()
    if not destination:
        messagebox.showwarning("Sin destinatario", "Selecciona un usuario destinatario")
        return
    
    message = message_entry.get().strip()
    if not message:
        return
    
    try:
        # Protocolo: TIPO (1 byte) = 3 para mensaje de texto
        client.sendall(b'\x03')  # Tipo: mensaje
        
        # Enviar nombre del destinatario
        client.sendall(struct.pack("!I", len(destination)))
        client.sendall(destination.encode())
        
        # Enviar mensaje
        client.sendall(struct.pack("!I", len(message)))
        client.sendall(message.encode())
        
        # Mostrar mensaje enviado en el chat
        chat_display.config(state=tk.NORMAL)
        chat_display.insert(tk.END, f"Tú -> {destination}: {message}\n", "sent")
        chat_display.see(tk.END)
        chat_display.config(state=tk.DISABLED)
        
        # Limpiar campo de entrada
        message_entry.delete(0, tk.END)
        
    except Exception as e:
        messagebox.showerror("Error", f"Error enviando mensaje: {e}")

def send_file():
    # Verificar que estamos conectados
    if not is_connected:
        messagebox.showwarning("Desconectado", "No estás conectado al servidor")
        return
    
    # Verificar que hay un destinatario seleccionado
    destination = user_combo.get()
    if not destination:
        messagebox.showwarning("Sin destinatario", "Selecciona un usuario destinatario")
        return
    
    # Filtros para archivos multimedia y otros
    filepath = filedialog.askopenfilename(
        title="Selecciona un archivo para enviar",
        filetypes=[
            ("Todos los archivos", "*.*"),
            ("Imágenes", "*.jpg *.jpeg *.png *.gif *.bmp *.svg *.webp *.ico"),
            ("Videos", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v"),
            ("Audio", "*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.wma"),
            ("Documentos", "*.pdf *.doc *.docx *.txt *.xls *.xlsx *.ppt *.pptx"),
            ("Comprimidos", "*.zip *.rar *.7z *.tar *.gz")
        ]
    )
    if not filepath:
        return

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    
    # Mostrar mensaje de envío en progreso
    display_message(f"📤 Enviando '{filename}' ({file_size:,} bytes) a {destination}...", "info")

    try:
        # Protocolo: TIPO (1 byte) = 2 para archivo
        client.sendall(b'\x02')  # Tipo: archivo
        
        # Enviar nombre del destinatario
        client.sendall(struct.pack("!I", len(destination)))
        client.sendall(destination.encode())
        
        # Enviar nombre del archivo
        client.sendall(struct.pack("!I", len(filename)))
        client.sendall(filename.encode())
        
        # Enviar tamaño del archivo
        client.sendall(struct.pack("!Q", file_size))
        
        # Enviar archivo en chunks de 1 MB para mejor rendimiento
        chunk_size = 1024 * 1024  # 1 MB
        bytes_sent = 0
        
        with open(filepath, "rb") as f:
            while bytes_sent < file_size:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                client.sendall(chunk)
                bytes_sent += len(chunk)

        display_message(f"✅ Archivo '{filename}' enviado correctamente a {destination}", "info")
        messagebox.showinfo("Enviado", f"{filename} enviado a {destination}")
    except Exception as e:
        display_message(f"❌ Error enviando archivo: {e}", "info")
        messagebox.showerror("Error", f"Error enviando archivo: {e}")

def receive_files():
    global is_connected
    while is_connected:
        try:
            # Recibir tipo de mensaje
            msg_type = recv_exact(client, 1)
            if not msg_type:
                break
            
            if msg_type == b'\x01':  # Lista de usuarios
                list_size = struct.unpack("!I", recv_exact(client, 4))[0]
                user_list_json = recv_exact(client, list_size).decode()
                users = json.loads(user_list_json)
                
                # Actualizar lista de usuarios (excluyendo el usuario actual)
                available_users.clear()
                for user in users:
                    if user != username:
                        available_users.append(user)
                
                # Actualizar ComboBox en el hilo principal
                root.after(0, update_user_list)
                
            elif msg_type == b'\x02':  # Archivo
                # Recibir nombre del remitente
                sender_size = struct.unpack("!I", recv_exact(client, 4))[0]
                sender = recv_exact(client, sender_size).decode()
                
                # Recibir nombre del archivo
                name_size = struct.unpack("!I", recv_exact(client, 4))[0]
                filename = recv_exact(client, name_size).decode()
                
                # Recibir tamaño del archivo
                file_size = struct.unpack("!Q", recv_exact(client, 8))[0]

                # Recibir datos del archivo usando chunks más grandes (1 MB) para mejor rendimiento
                data = b""
                remaining = file_size
                chunk_size = 1024 * 1024  # 1 MB en lugar de 4 KB
                
                while remaining > 0:
                    to_recv = min(chunk_size, remaining)
                    chunk = client.recv(to_recv)
                    if not chunk:
                        break
                    data += chunk
                    remaining -= len(chunk)

                # Guardar archivo
                with open(f"recibido_{filename}", "wb") as f:
                    f.write(data)

                # Determinar tipo de archivo para el emoji
                ext = filename.lower().split('.')[-1] if '.' in filename else ''
                emoji = "📁"
                if ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'ico']:
                    emoji = "🖼️"
                elif ext in ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v']:
                    emoji = "🎥"
                elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac', 'wma']:
                    emoji = "🎵"
                elif ext in ['pdf', 'doc', 'docx', 'txt', 'xls', 'xlsx', 'ppt', 'pptx']:
                    emoji = "📄"
                elif ext in ['zip', 'rar', '7z', 'tar', 'gz']:
                    emoji = "📦"

                root.after(0, lambda s=sender, f=filename, e=emoji, sz=file_size: 
                          display_message(f"{e} Archivo recibido de {s}: {f} ({sz:,} bytes)", "file"))
                root.after(0, lambda s=sender, f=filename: messagebox.showinfo(
                    "Archivo recibido",
                    f"Archivo recibido de {s}:\n{f}"
                ))
            
            elif msg_type == b'\x03':  # Mensaje de texto
                # Recibir nombre del remitente
                sender_size = struct.unpack("!I", recv_exact(client, 4))[0]
                sender = recv_exact(client, sender_size).decode()
                
                # Recibir mensaje
                msg_size = struct.unpack("!I", recv_exact(client, 4))[0]
                message = recv_exact(client, msg_size).decode()
                
                # Mostrar mensaje en el chat
                root.after(0, lambda s=sender, m=message: display_message(f"{s}: {m}", "received"))
            
            elif msg_type == b'\x05':  # Notificación de desconexión
                # Recibir nombre del usuario desconectado
                user_size = struct.unpack("!I", recv_exact(client, 4))[0]
                disconnected_user = recv_exact(client, user_size).decode()
                
                # Mostrar notificación en el chat
                root.after(0, lambda u=disconnected_user: display_message(f"🚪 {u} se ha desconectado", "info"))

        except (ConnectionError, OSError, struct.error) as e:
            # Socket cerrado o error de conexión - salir silenciosamente si es desconexión intencional
            if is_connected:
                print(f"Error en receive_files: {e}")
                root.after(0, lambda: messagebox.showerror("Error de conexión", "Se perdió la conexión con el servidor"))
            break
        except Exception as e:
            if is_connected:
                print(f"Error inesperado en receive_files: {e}")
            break

def update_user_list():
    """Actualiza el ComboBox con la lista de usuarios disponibles"""
    user_combo['values'] = available_users
    if available_users and not user_combo.get():
        user_combo.current(0)
    elif user_combo.get() not in available_users:
        user_combo.set('')
    
    # Actualizar el label con el conteo
    user_count_label.config(text=f"Usuarios disponibles: {len(available_users)}")

def display_message(message, msg_type="info"):
    """Muestra un mensaje en el área de chat"""
    chat_display.config(state=tk.NORMAL)
    chat_display.insert(tk.END, message + "\n", msg_type)
    chat_display.see(tk.END)
    chat_display.config(state=tk.DISABLED)

# GUI
root = tk.Tk()
root.title(f"💬 Cliente Multimedia - {username}")
root.geometry("500x600")
root.resizable(True, True)

# Frame principal
main_frame = tk.Frame(root, padx=15, pady=15)
main_frame.pack(fill=tk.BOTH, expand=True)

# Frame superior para selección de usuario
top_frame = tk.Frame(main_frame)
top_frame.pack(fill=tk.X, pady=(0, 10))

# Label de usuarios disponibles
user_count_label = tk.Label(top_frame, text="Usuarios disponibles: 0", font=("Arial", 9))
user_count_label.pack(pady=(0, 5))

# Label y ComboBox para seleccionar destinatario
tk.Label(top_frame, text="Destinatario:", font=("Arial", 9, "bold")).pack(pady=(0, 3))
user_combo = ttk.Combobox(top_frame, state="readonly", width=40, font=("Arial", 10))
user_combo.pack(pady=(0, 5))

# Frame para el área de chat
chat_frame = tk.LabelFrame(main_frame, text="💬 Chat", font=("Arial", 10, "bold"), padx=10, pady=10)
chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

# Área de texto para mostrar mensajes con scrollbar
chat_scroll = tk.Scrollbar(chat_frame)
chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)

chat_display = tk.Text(chat_frame, height=15, state=tk.DISABLED, wrap=tk.WORD, 
                       yscrollcommand=chat_scroll.set, font=("Arial", 9))
chat_display.pack(fill=tk.BOTH, expand=True)
chat_scroll.config(command=chat_display.yview)

# Configurar tags para colores de mensajes
chat_display.tag_config("sent", foreground="#0066cc")
chat_display.tag_config("received", foreground="#009900")
chat_display.tag_config("file", foreground="#cc6600", font=("Arial", 9, "italic"))
chat_display.tag_config("info", foreground="#666666", font=("Arial", 9, "italic"))

# Frame para entrada de mensaje
message_frame = tk.Frame(main_frame)
message_frame.pack(fill=tk.X, pady=(0, 10))

tk.Label(message_frame, text="Mensaje:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))
message_entry = tk.Entry(message_frame, font=("Arial", 10))
message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
message_entry.bind('<Return>', lambda e: send_message())

send_msg_btn = tk.Button(message_frame, text="Enviar", command=send_message, 
                         font=("Arial", 9, "bold"), bg="#2196F3", fg="white", width=10)
send_msg_btn.pack(side=tk.LEFT)

# Frame para botones
buttons_frame = tk.Frame(main_frame)
buttons_frame.pack(fill=tk.X)

# Botón para enviar archivo
file_btn = tk.Button(buttons_frame, text="📤 Enviar archivo", command=send_file, 
                     font=("Arial", 10, "bold"), bg="#4CAF50", fg="white", height=2)
file_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

# Botón para desconectar
disconnect_btn = tk.Button(buttons_frame, text="🚪 Desconectar", command=disconnect, 
                           font=("Arial", 10, "bold"), bg="#f44336", fg="white", height=2)
disconnect_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

# Manejar cierre de ventana
root.protocol("WM_DELETE_WINDOW", disconnect)

threading.Thread(target=receive_files, daemon=True).start()

root.mainloop()