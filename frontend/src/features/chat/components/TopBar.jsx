export function TopBar({
  connected,
  usernameInput,
  onUsernameChange,
  onConnect,
  myUsername,
  onDisconnect,
  transportMode,
}) {
  return (
    <header className="topbar">
      <div>
        <h1>Chat WebSocket</h1>
        <p>Mensajes y archivos en tiempo real sobre HTTP</p>
        <p>Modo de transporte: {transportMode}</p>
      </div>

      {!connected ? (
        <div className="connect-panel">
          <input
            value={usernameInput}
            onChange={(e) => onUsernameChange(e.target.value)}
            placeholder="Tu nombre de usuario"
          />
          <button onClick={onConnect} disabled={!usernameInput.trim()}>
            Conectar
          </button>
        </div>
      ) : (
        <div className="connect-panel">
          <span className="chip">Conectado como {myUsername}</span>
          <button className="danger" onClick={onDisconnect}>
            Salir
          </button>
        </div>
      )}
    </header>
  )
}
