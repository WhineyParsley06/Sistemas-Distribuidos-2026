import { useMemo, useState } from 'react'
import './App.css'
import { TopBar } from './features/chat/components/TopBar'
import { UsersPanel } from './features/chat/components/UsersPanel'
import { MessageList } from './features/chat/components/MessageList'
import { Composer } from './features/chat/components/Composer'
import { PeerConnectionStatus } from './features/chat/components/PeerConnectionStatus'
import { ConnectionDiagnostics } from './features/chat/components/ConnectionDiagnostics'
import { useChatConnection } from './features/chat/hooks/useChatConnection'
import { downloadBase64File } from './features/chat/utils/fileTransfer'
import { getTransportMode } from './config/transport'

const resolveDefaultWsBaseUrl = () => {
  if (typeof window === 'undefined') {
    return 'ws://localhost:8000'
  }

  const { hostname, port, protocol, host } = window.location
  const isViteLocalDev = (hostname === 'localhost' || hostname === '127.0.0.1') && port === '5173'

  if (isViteLocalDev) {
    return 'ws://localhost:8000'
  }

  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${host}`
}

function App() {
  const [usernameInput, setUsernameInput] = useState('')
  const [targetUser, setTargetUser] = useState('')
  const [message, setMessage] = useState('')
  const defaultWsBaseUrl = resolveDefaultWsBaseUrl()
  const signalingUrl = import.meta.env.VITE_SIGNALING_WS_URL ?? `${defaultWsBaseUrl}/signal/ws`
  const transportMode = getTransportMode()

  const {
    connected,
    myUsername,
    users,
    messages,
    // Fase 4: UI & monitoring states
    peerConnectionStates,
    diagnosticsByPeer,
    reconnectionStatusByPeer,
    iceInfoByPeer,
    allPeers,
    // Connection methods
    connect,
    disconnect,
    sendText,
    sendFile,
  } = useChatConnection(signalingUrl)

  const availableTargets = useMemo(
    () => users.filter((name) => name !== myUsername),
    [users, myUsername],
  )

  const effectiveTargetUser = useMemo(() => {
    if (!availableTargets.length) {
      return ''
    }

    if (availableTargets.includes(targetUser)) {
      return targetUser
    }

    return availableTargets[0]
  }, [availableTargets, targetUser])

  const handleConnect = () => {
    connect(usernameInput)
  }

  const handleSendText = async () => {
    const sent = await sendText(effectiveTargetUser, message)
    if (sent) {
      setMessage('')
    }
  }

  const handleSendFile = async (file) => {
    await sendFile(effectiveTargetUser, file)
  }

  return (
    <div className="chat-page">
      <TopBar
        connected={connected}
        usernameInput={usernameInput}
        onUsernameChange={setUsernameInput}
        onConnect={handleConnect}
        myUsername={myUsername}
        onDisconnect={disconnect}
        transportMode={transportMode}
      />

      <main className="layout">
        <UsersPanel
          connected={connected}
          availableTargets={availableTargets}
          targetUser={effectiveTargetUser}
          onTargetChange={setTargetUser}
        />

        <section className="panel chat">
          <MessageList messages={messages} onDownloadFile={downloadBase64File} />

          <Composer
            connected={connected}
            targetUser={effectiveTargetUser}
            message={message}
            onMessageChange={setMessage}
            onSendText={handleSendText}
            onSendFile={handleSendFile}
          />

          {/* Fase 4: P2P Status Monitoring */}
          {transportMode === 'p2p' && allPeers && allPeers.length > 0 && (
            <div style={{ marginTop: '20px' }}>
              <h3 style={{ marginTop: '20px', marginBottom: '10px' }}>Estado de Conexiones P2P</h3>
              {allPeers.map((peerName) => (
                <PeerConnectionStatus
                  key={peerName}
                  peerName={peerName}
                  connectionState={peerConnectionStates[peerName] || 'closed'}
                  channelState={diagnosticsByPeer[peerName]?.channelState || 'closed'}
                  diagnostics={diagnosticsByPeer[peerName]}
                  reconnectionStatus={reconnectionStatusByPeer[peerName]}
                />
              ))}
            </div>
          )}

          {/* Fase 4: Connection Diagnostics */}
          {transportMode === 'p2p' && (
            <ConnectionDiagnostics
              allPeers={allPeers || []}
              diagnosticsByPeer={diagnosticsByPeer}
              iceInfoByPeer={iceInfoByPeer}
            />
          )}
        </section>
      </main>
    </div>
  )
}

export default App