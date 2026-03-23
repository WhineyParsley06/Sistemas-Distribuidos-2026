import socket
import threading
import struct
import json

HOST = "10.253.60.28"
PORT = 5000

clients = []
clients_info = {}  # {socket: username}

def recv_exact(sock, num_bytes):
    """Recibe exactamente num_bytes bytes del socket"""
    data = b""
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:
            raise ConnectionError("Conexión cerrada antes de recibir todos los datos")
        data += chunk
    return data

def broadcast_user_list():
    """Envía la lista de usuarios conectados a todos los clientes"""
    usernames = list(clients_info.values())
    user_list_json = json.dumps(usernames).encode()
    
    # Protocolo: TYPE (1 byte) = 1 para lista de usuarios, tamaño (4 bytes), datos
    clients_to_remove = []
    for client in clients:
        try:
            client.sendall(b'\x01')  # Tipo: lista de usuarios
            client.sendall(struct.pack("!I", len(user_list_json)))
            client.sendall(user_list_json)
        except (ConnectionResetError, BrokenPipeError, OSError):
            # Cliente desconectado, marcar para eliminar
            clients_to_remove.append(client)
    
    # Limpiar clientes desconectados
    for client in clients_to_remove:
        if client in clients:
            clients.remove(client)
        if client in clients_info:
            clients_info.pop(client, None)

def notify_user_disconnected(username):
    """Notifica a todos los clientes que un usuario se ha desconectado"""
    # Protocolo: TYPE (1 byte) = 5 para notificación de desconexión
    clients_to_remove = []
    for client in clients:
        try:
            client.sendall(b'\x05')  # Tipo: usuario desconectado
            client.sendall(struct.pack("!I", len(username)))
            client.sendall(username.encode())
        except (ConnectionResetError, BrokenPipeError, OSError):
            # Cliente desconectado, marcar para eliminar
            clients_to_remove.append(client)
    
    # Limpiar clientes desconectados
    for client in clients_to_remove:
        if client in clients:
            clients.remove(client)
        if client in clients_info:
            clients_info.pop(client, None)

def handle_client(client_socket):
    username = None
    try:
        # Recibir nombre del usuario
        name_size_data = recv_exact(client_socket, 4)
        if not name_size_data:
            return
        name_size = struct.unpack("!I", name_size_data)[0]
        username = recv_exact(client_socket, name_size).decode()
        clients_info[client_socket] = username
        
        print(f"👤 Usuario '{username}' conectado")
        
        # Notificar a todos los clientes la lista actualizada
        broadcast_user_list()
        
        while True:
            # Recibir tipo de mensaje
            msg_type = recv_exact(client_socket, 1)
            if not msg_type:
                break
            
            if msg_type == b'\x02':  # Tipo: archivo
                # Recibir nombre del destinatario
                dest_size_data = recv_exact(client_socket, 4)
                if not dest_size_data:
                    break
                dest_size = struct.unpack("!I", dest_size_data)[0]
                destination = recv_exact(client_socket, dest_size).decode()

                # Recibir tamaño del nombre del archivo
                name_size_data = recv_exact(client_socket, 4)
                if not name_size_data:
                    break
                name_size = struct.unpack("!I", name_size_data)[0]

                # Recibir nombre del archivo
                filename = recv_exact(client_socket, name_size).decode()

                # Recibir tamaño del archivo
                file_size = struct.unpack("!Q", recv_exact(client_socket, 8))[0]

                # Recibir datos del archivo en chunks más grandes (1 MB)
                file_data = b""
                remaining = file_size
                chunk_size = 1024 * 1024  # 1 MB en lugar de 4 KB
                
                while remaining > 0:
                    to_recv = min(chunk_size, remaining)
                    chunk = client_socket.recv(to_recv)
                    if not chunk:
                        break
                    file_data += chunk
                    remaining -= len(chunk)

                # No mostrar contenido por privacidad
                # print(f"📁 {username} envía '{filename}' ({file_size:,} bytes) a {destination}")

                # Enviar solo al destinatario especificado
                for client, name in clients_info.items():
                    if name == destination and client != client_socket:
                        try:
                            client.sendall(b'\x02')  # Tipo: archivo
                            client.sendall(struct.pack("!I", len(username)))
                            client.sendall(username.encode())
                            client.sendall(name_size_data)
                            client.sendall(filename.encode())
                            client.sendall(struct.pack("!Q", file_size))
                            client.sendall(file_data)
                            # Archivo reenviado (sin mostrar detalles por privacidad)
                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            # Cliente destino desconectado
                            pass
                        except Exception as e:
                            print(f"❌ Error enviando archivo a {destination}: {e}")
                        break
            
            elif msg_type == b'\x03':  # Tipo: mensaje de texto
                # Recibir nombre del destinatario
                dest_size_data = recv_exact(client_socket, 4)
                if not dest_size_data:
                    break
                dest_size = struct.unpack("!I", dest_size_data)[0]
                destination = recv_exact(client_socket, dest_size).decode()
                
                # Recibir mensaje
                msg_size_data = recv_exact(client_socket, 4)
                if not msg_size_data:
                    break
                msg_size = struct.unpack("!I", msg_size_data)[0]
                message = recv_exact(client_socket, msg_size).decode()
                
                # No mostrar contenido del mensaje por privacidad
                # print(f"💬 {username} -> {destination}: {message}")
                
                # Enviar solo al destinatario especificado
                for client, name in clients_info.items():
                    if name == destination and client != client_socket:
                        try:
                            client.sendall(b'\x03')  # Tipo: mensaje
                            client.sendall(struct.pack("!I", len(username)))
                            client.sendall(username.encode())
                            client.sendall(struct.pack("!I", len(message)))
                            client.sendall(message.encode())
                            # Mensaje reenviado (sin mostrar contenido por privacidad)
                        except (ConnectionResetError, BrokenPipeError, OSError) as e:
                            # Cliente destino desconectado
                            pass
                        except Exception as e:
                            print(f"❌ Error enviando mensaje a {destination}: {e}")
                        break
            
            elif msg_type == b'\x04':  # Tipo: desconexión explícita
                print(f"🚪 {username} se ha desconectado voluntariamente")
                break

    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError) as e:
        # Conexión interrumpida por el cliente (normal al desconectar)
        pass
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
    finally:
        if client_socket in clients:
            clients.remove(client_socket)
        if client_socket in clients_info:
            user = clients_info.pop(client_socket)
            print(f"👋 Usuario '{user}' desconectado")
            # Notificar a otros clientes sobre la desconexión
            notify_user_disconnected(user)
            # Notificar cambio en lista de usuarios
            broadcast_user_list()
        client_socket.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"🟢 Servidor escuchando en {PORT}")

    while True:
        client_socket, addr = server.accept()
        print(f"🔗 Cliente conectado: {addr}")
        clients.append(client_socket)
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()

start_server()