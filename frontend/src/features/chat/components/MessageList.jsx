export function MessageList({ messages, onDownloadFile }) {
  return (
    <div className="messages">
      {messages.length === 0 ? (
        <p className="placeholder">Sin mensajes todavia</p>
      ) : (
        messages.map((item) => (
          <div key={item.id} className={`msg ${item.kind}`}>
            <span>{item.text}</span>
            {item.file ? <button onClick={() => onDownloadFile(item.file)}>Descargar</button> : null}
          </div>
        ))
      )}
    </div>
  )
}
