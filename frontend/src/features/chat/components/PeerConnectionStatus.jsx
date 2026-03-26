/**
 * Peer Connection Status Component
 * Displays visual indicators for each peer connection state
 */

export function PeerConnectionStatus({ peerName, connectionState, channelState, diagnostics, reconnectionStatus }) {
  const getStateColor = (state) => {
    const colors = {
      connected: '#4CAF50', // Green
      connecting: '#2196F3', // Blue
      disconnected: '#FF9800', // Orange
      failed: '#f44336', // Red
      closed: '#999', // Gray
    }
    return colors[state] || '#999'
  }

  const getStateLabel = (state) => {
    const labels = {
      connected: 'Conectado',
      connecting: 'Conectando',
      disconnected: 'Desconectado',
      failed: 'Falló',
      closed: 'Cerrado',
    }
    return labels[state] || state
  }

  const channelStateLabel = channelState === 'open' ? 'Abierto' : 'Cerrado'

  return (
    <div
      style={{
        padding: '12px',
        marginBottom: '10px',
        border: `2px solid ${getStateColor(connectionState)}`,
        borderRadius: '6px',
        backgroundColor: '#f5f5f5',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              backgroundColor: getStateColor(connectionState),
              animation: connectionState === 'connecting' ? 'pulse 1s infinite' : 'none',
            }}
          />
          <div>
            <strong>{peerName}</strong>
            <div style={{ fontSize: '12px', color: '#666' }}>
              Conexión: <span style={{ color: getStateColor(connectionState) }}>{getStateLabel(connectionState)}</span>
            </div>
            <div style={{ fontSize: '12px', color: '#666' }}>
              Canal: <span style={{ color: channelState === 'open' ? '#4CAF50' : '#999' }}>{channelStateLabel}</span>
            </div>
          </div>
        </div>

        {/* Reconnection Status Badge */}
        {reconnectionStatus && reconnectionStatus.isActive && (
          <div
            style={{
              padding: '6px 10px',
              backgroundColor: '#FF9800',
              color: 'white',
              borderRadius: '4px',
              fontSize: '12px',
              textAlign: 'center',
            }}
          >
            <div>Reconectando</div>
            <div style={{ fontSize: '11px' }}>
              Intento {reconnectionStatus.attemptCount}/{reconnectionStatus.maxAttempts}
            </div>
          </div>
        )}
      </div>

      {/* Diagnostic Info */}
      {diagnostics && (
        <div style={{ marginTop: '10px', fontSize: '11px', color: '#888', borderTop: '1px solid #ddd', paddingTop: '8px' }}>
          <div>RTCState: {diagnostics.rtcState}</div>
          <div>ICEState: {diagnostics.rtcIceState}</div>
          {diagnostics.latencyMs !== undefined && <div>Latencia: {diagnostics.latencyMs}ms</div>}
        </div>
      )}

      {/* Reconnection Timer */}
      {reconnectionStatus && reconnectionStatus.nextRetryInMs > 0 && (
        <div style={{ marginTop: '8px', fontSize: '12px', color: '#FF9800', fontWeight: 'bold' }}>
          Próximo intento en {Math.ceil(reconnectionStatus.nextRetryInMs / 1000)}s...
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
