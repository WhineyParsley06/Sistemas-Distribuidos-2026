import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

function App() {
  const [usernameInput, setUsernameInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [myUsername, setMyUsername] = useState('')
  const [users, setUsers] = useState([])
  const [targetUser, setTargetUser] = useState('')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])

  const wsRef = useRef(null)
  const fileInputRef = useRef(null)
  const wsUrl = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws'

  const availableTargets = useMemo(
    () => users.filter((name) => name !== myUsername),
    [users, myUsername],
  )

  useEffect(() => {
    if (!availableTargets.length) {
      setTargetUser('')
      return
    }

    if (!availableTargets.includes(targetUser)) {
      setTargetUser(availableTargets[0])
    }
  }, [availableTargets, targetUser])

  useEffect(() => {
    return () => {
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'disconnect' }))
        ws.close()
      }
    }
  }, [])

  const appendMessage = (msg) => {
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), ...msg }])
  }

  const connect = () => {
    const rawName = usernameInput.trim()
    if (!rawName) return

    const ws = new WebSocket(`${wsUrl}?username=${encodeURIComponent(rawName)}`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      appendMessage({ kind: 'system', text: 'Conectado al servidor' })
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'system') {
        if (data.username) {
          setMyUsername(data.username)
        }
        appendMessage({ kind: 'system', text: data.message })
      }

      if (data.type === 'user_list') {
        setUsers(data.users || [])
      }

      if (data.type === 'user_disconnected') {
        appendMessage({ kind: 'system', text: data.message })
      }

      if (data.type === 'text') {
        appendMessage({ kind: 'received', text: `${data.from}: ${data.message}` })
      }

      if (data.type === 'file') {
        appendMessage({
          kind: 'file',
          text: `${data.from} te envio ${data.filename} (${Number(data.size || 0).toLocaleString()} bytes)`,
          file: {
            name: data.filename,
            content: data.content,
            mimeType: data.mimeType,
          },
        })
      }
    }

    ws.onclose = () => {
      appendMessage({ kind: 'system', text: 'Conexion cerrada' })
      setConnected(false)
      setUsers([])
      setTargetUser('')
      setMyUsername('')
    }

    ws.onerror = () => {
      appendMessage({ kind: 'error', text: 'Error de conexion con el servidor' })
    }
  }

  const disconnect = () => {
    const ws = wsRef.current
    if (!ws) return

    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'disconnect' }))
      ws.close()
    }
  }

  const sendText = () => {
    const ws = wsRef.current
    const trimmed = message.trim()
    if (!connected || !ws || !trimmed || !targetUser) return

    ws.send(
      JSON.stringify({
        type: 'text',
        to: targetUser,
        message: trimmed,
      }),
    )

    appendMessage({ kind: 'sent', text: `Tu -> ${targetUser}: ${trimmed}` })
    setMessage('')
  }

  const encodeFileAsBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = String(reader.result)
        const [, base64] = result.split(',')
        resolve(base64)
      }
      reader.onerror = () => reject(new Error('No se pudo leer el archivo'))
      reader.readAsDataURL(file)
    })

  const sendFile = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''

    const ws = wsRef.current
    if (!connected || !ws || !file || !targetUser) return

    const base64 = await encodeFileAsBase64(file)
    ws.send(
      JSON.stringify({
        type: 'file',
        to: targetUser,
        filename: file.name,
        content: base64,
        mimeType: file.type || 'application/octet-stream',
        size: file.size,
      }),
    )

    appendMessage({
      kind: 'sent',
      text: `Tu -> ${targetUser}: archivo ${file.name} (${file.size.toLocaleString()} bytes)`,
    })
  }

  const downloadFile = (file) => {
    const byteChars = atob(file.content)
    const byteNumbers = new Array(byteChars.length)
    for (let i = 0; i < byteChars.length; i += 1) {
      byteNumbers[i] = byteChars.charCodeAt(i)
    }
    const blob = new Blob([new Uint8Array(byteNumbers)], {
      type: file.mimeType || 'application/octet-stream',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="chat-page">
      <header className="topbar">
        <div>
          <h1>Chat WebSocket</h1>
          <p>Mensajes y archivos en tiempo real sobre HTTP</p>
        </div>

        {!connected ? (
          <div className="connect-panel">
            <input
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              placeholder="Tu nombre de usuario"
            />
            <button onClick={connect} disabled={!usernameInput.trim()}>
              Conectar
            </button>
          </div>
        ) : (
          <div className="connect-panel">
            <span className="chip">Conectado como {myUsername}</span>
            <button className="danger" onClick={disconnect}>
              Salir
            </button>
          </div>
        )}
      </header>

      <main className="layout">
        <aside className="panel users">
          <h2>Usuarios</h2>
          <p>{availableTargets.length} disponibles</p>
          <select
            value={targetUser}
            onChange={(e) => setTargetUser(e.target.value)}
            disabled={!connected || !availableTargets.length}
          >
            {availableTargets.length === 0 ? (
              <option value="">No hay usuarios disponibles</option>
            ) : (
              availableTargets.map((user) => (
                <option key={user} value={user}>
                  {user}
                </option>
              ))
            )}
          </select>
        </aside>

        <section className="panel chat">
          <div className="messages">
            {messages.length === 0 ? (
              <p className="placeholder">Sin mensajes todavia</p>
            ) : (
              messages.map((item) => (
                <div key={item.id} className={`msg ${item.kind}`}>
                  <span>{item.text}</span>
                  {item.file ? (
                    <button onClick={() => downloadFile(item.file)}>Descargar</button>
                  ) : null}
                </div>
              ))
            )}
          </div>

          <div className="composer">
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') sendText()
              }}
              placeholder="Escribe un mensaje privado"
              disabled={!connected || !targetUser}
            />
            <button onClick={sendText} disabled={!connected || !targetUser || !message.trim()}>
              Enviar
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={!connected || !targetUser}
            >
              Archivo
            </button>
            <input
              ref={fileInputRef}
              type="file"
              onChange={sendFile}
              hidden
            />
          </div>
        </section>
      </main>
    </div>
  )
}

export default App