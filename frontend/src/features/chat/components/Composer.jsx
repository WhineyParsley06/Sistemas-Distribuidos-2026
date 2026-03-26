import { useRef } from 'react'

export function Composer({
  connected,
  targetUser,
  message,
  onMessageChange,
  onSendText,
  onSendFile,
}) {
  const fileInputRef = useRef(null)

  return (
    <div className="composer">
      <input
        value={message}
        onChange={(e) => onMessageChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSendText()
        }}
        placeholder="Escribe un mensaje privado"
        disabled={!connected || !targetUser}
      />
      <button onClick={onSendText} disabled={!connected || !targetUser || !message.trim()}>
        Enviar
      </button>
      <button onClick={() => fileInputRef.current?.click()} disabled={!connected || !targetUser}>
        Archivo
      </button>
      <input
        ref={fileInputRef}
        type="file"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          if (file) {
            onSendFile(file)
          }
        }}
        hidden
      />
    </div>
  )
}
