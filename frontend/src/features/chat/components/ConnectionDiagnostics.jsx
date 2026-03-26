/**
 * Connection Diagnostics Component
 * Displays detailed connection statistics and ICE candidate information
 */

export function ConnectionDiagnostics({ allPeers, diagnosticsByPeer, iceInfoByPeer }) {
  if (!allPeers || allPeers.length === 0) {
    return (
      <div style={{ padding: '15px', backgroundColor: '#f0f0f0', borderRadius: '6px', marginTop: '20px' }}>
        <strong>📊 Diagnósticos</strong>
        <div style={{ fontSize: '12px', color: '#666', marginTop: '8px' }}>
          Sin conexiones P2P activas
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '15px', backgroundColor: '#f0f0f0', borderRadius: '6px', marginTop: '20px' }}>
      <strong>📊 Diagnósticos Detallados</strong>

      {allPeers.map((peerName) => {
        const diag = diagnosticsByPeer?.[peerName]
        const iceInfo = iceInfoByPeer?.[peerName]

        return (
          <div key={peerName} style={{ marginTop: '15px', paddingTop: '15px', borderTop: '1px solid #ddd' }}>
            <h4 style={{ margin: '0 0 10px 0', color: '#333' }}>{peerName}</h4>

            {/* Connection States */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
              <div style={{ fontSize: '12px', backgroundColor: 'white', padding: '8px', borderRadius: '4px' }}>
                <div style={{ color: '#666' }}>RTCPeerConnection</div>
                <div style={{ fontWeight: 'bold', color: diag?.isHealthy ? '#4CAF50' : '#f44336' }}>
                  {diag?.rtcState || '—'}
                </div>
              </div>

              <div style={{ fontSize: '12px', backgroundColor: 'white', padding: '8px', borderRadius: '4px' }}>
                <div style={{ color: '#666' }}>ICE Connection</div>
                <div style={{ fontWeight: 'bold', color: diag?.rtcIceState === 'connected' ? '#4CAF50' : '#FF9800' }}>
                  {diag?.rtcIceState || '—'}
                </div>
              </div>

              <div style={{ fontSize: '12px', backgroundColor: 'white', padding: '8px', borderRadius: '4px' }}>
                <div style={{ color: '#666' }}>Signaling State</div>
                <div style={{ fontWeight: 'bold' }}>{diag?.rtcSignalingState || '—'}</div>
              </div>

              <div style={{ fontSize: '12px', backgroundColor: 'white', padding: '8px', borderRadius: '4px' }}>
                <div style={{ color: '#666' }}>DataChannel</div>
                <div style={{ fontWeight: 'bold', color: diag?.channelState === 'open' ? '#4CAF50' : '#999' }}>
                  {diag?.channelState || '—'}
                </div>
              </div>
            </div>

            {/* ICE Server Configuration */}
            {iceInfo && (
              <div style={{ marginTop: '10px', padding: '10px', backgroundColor: 'white', borderRadius: '4px', fontSize: '11px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '6px', color: '#333' }}>Servidores ICE Configurados</div>
                {iceInfo.stunServers && iceInfo.stunServers.length > 0 && (
                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ color: '#666', fontWeight: '500' }}>STUN ({iceInfo.stunServers.length}):</div>
                    <div style={{ color: '#888', marginLeft: '10px' }}>
                      {iceInfo.stunServers.slice(0, 3).map((server, idx) => (
                        <div key={idx}>• {server}</div>
                      ))}
                      {iceInfo.stunServers.length > 3 && <div>• +{iceInfo.stunServers.length - 3} más</div>}
                    </div>
                  </div>
                )}

                {iceInfo.turnServers && iceInfo.turnServers.length > 0 && (
                  <div>
                    <div style={{ color: '#666', fontWeight: '500' }}>TURN ({iceInfo.turnServers.length}):</div>
                    <div style={{ color: '#888', marginLeft: '10px' }}>
                      {iceInfo.turnServers.map((server, idx) => (
                        <div key={idx}>
                          • {server.url} {server.hasAuth && '(con autenticación)'}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div style={{ color: '#666', marginTop: '8px', fontSize: '10px' }}>
                  Última actualización: {diag?.timestamp ? new Date(diag.timestamp).toLocaleTimeString() : '—'}
                </div>
              </div>
            )}
          </div>
        )
      })}

      <div style={{ marginTop: '15px', fontSize: '11px', color: '#888' }}>
        💡 Tip: Abre DevTools (F12) → Console para ver logs detallados con [P2P] y [P2P:Resilience]
      </div>
    </div>
  )
}
