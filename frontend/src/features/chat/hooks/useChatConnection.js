import { useCallback, useEffect, useRef, useState } from 'react'
import { encodeFileAsBase64 } from '../utils/fileTransfer'
import { buildIceConfiguration, getIceServerDebugInfo } from '../utils/iceConfig'
import {
  PeerReconnectionManager,
  HeartbeatMonitor,
  cleanupPeerResources,
  diagnoseConnectionHealth,
} from '../utils/resilience'

const RTC_CONFIGURATION = buildIceConfiguration()

const DEBUG_P2P = import.meta.env.VITE_DEBUG_P2P === 'true'

const p2pLog = (message, data) => {
  if (DEBUG_P2P) {
    console.log(`[P2P] ${message}`, data || '')
  }
}

const createMessageId = () => {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function useChatConnection(signalingUrl = 'ws://localhost:8000/signal/ws') {
  const [connected, setConnected] = useState(false)
  const [myUsername, setMyUsername] = useState('')
  const [users, setUsers] = useState([])
  const [messages, setMessages] = useState([])

  // Fase 4: UI & Monitoreo - Estados de peers y diagnósticos
  const [peerConnectionStates, setPeerConnectionStates] = useState({}) // { peerName: 'connected'|'connecting'|... }
  const [diagnosticsByPeer, setDiagnosticsByPeer] = useState({}) // { peerName: {...diagnostics} }
  const [reconnectionStatusByPeer, setReconnectionStatusByPeer] = useState({}) // { peerName: {...status} }
  const [iceInfoByPeer, setIceInfoByPeer] = useState({}) // { peerName: {...iceServers} }

  const wsRef = useRef(null)
  const connectRef = useRef(null)
  const peerConnectionsRef = useRef(new Map())
  const dataChannelsRef = useRef(new Map())
  const signalingReconnectTimeoutRef = useRef(null)
  const signalingHeartbeatIntervalRef = useRef(null)
  const isManualDisconnectRef = useRef(false)
  const signalingReconnectAttemptsRef = useRef(0)
  const lastSignalingErrorAtRef = useRef(0)
  const heartbeatMonitorsRef = useRef(new Map()) // Fase 3: Heartbeat monitors
  const reconnectionManagersRef = useRef(new Map()) // Fase 3: Reconnection managers

  // Fase 4: Helper functions to update diagnostics
  const updatePeerDiagnostics = useCallback((peerName, data) => {
    setDiagnosticsByPeer((prev) => ({
      ...prev,
      [peerName]: { ...prev[peerName], ...data, timestamp: Date.now() },
    }))
  }, [])

  const updateReconnectionStatus = useCallback((peerName, status) => {
    setReconnectionStatusByPeer((prev) => ({
      ...prev,
      [peerName]: status,
    }))
  }, [])

  const updatePeerConnectionState = useCallback((peerName, state) => {
    setPeerConnectionStates((prev) => ({
      ...prev,
      [peerName]: state,
    }))
  }, [])

  const setIceInfoForPeer = useCallback((peerName) => {
    const iceInfo = getIceServerDebugInfo()
    setIceInfoByPeer((prev) => ({
      ...prev,
      [peerName]: iceInfo,
    }))
  }, [])

  const appendMessage = useCallback((msg) => {
    setMessages((prev) => [...prev, { id: createMessageId(), ...msg }])
  }, [])

  const closePeerConnection = useCallback((peerName) => {
    p2pLog(`Closing peer connection for ${peerName}`)

    // Stop heartbeat monitor
    const heartbeatMonitor = heartbeatMonitorsRef.current.get(peerName)
    if (heartbeatMonitor) {
      heartbeatMonitor.stop()
      heartbeatMonitorsRef.current.delete(peerName)
    }

    // Stop reconnection manager
    const reconnectionManager = reconnectionManagersRef.current.get(peerName)
    if (reconnectionManager) {
      reconnectionManager.stop()
      reconnectionManagersRef.current.delete(peerName)
    }

    // Get references
    const channel = dataChannelsRef.current.get(peerName)
    const pc = peerConnectionsRef.current.get(peerName)

    // Clean up resources using safe cleanup function
    cleanupPeerResources(pc, channel)

    // Remove from maps
    dataChannelsRef.current.delete(peerName)
    peerConnectionsRef.current.delete(peerName)

    p2pLog(`Peer connection closed for ${peerName}`)
  }, [])

  const closeAllPeerConnections = useCallback(() => {
    const peerNames = new Set([...peerConnectionsRef.current.keys(), ...dataChannelsRef.current.keys()])
    peerNames.forEach((peerName) => closePeerConnection(peerName))
  }, [closePeerConnection])

  const sendSignal = useCallback(
    (type, destination, payload) => {
      const ws = wsRef.current

      if (!ws || ws.readyState !== WebSocket.OPEN) {
        const now = Date.now()
        if (now - lastSignalingErrorAtRef.current > 2000) {
          appendMessage({ kind: 'error', text: 'No hay conexión activa con signaling.' })
          lastSignalingErrorAtRef.current = now
        }
        return false
      }

      const to = (destination || '').trim()
      if (!to) {
        appendMessage({ kind: 'error', text: 'Debes indicar un peer destino para señalización.' })
        return false
      }

      ws.send(
        JSON.stringify({
          type,
          to,
          payload: payload || {},
        }),
      )

      return true
    },
    [appendMessage],
  )

  const sendSignalOffer = useCallback(
    (destination, offer) => sendSignal('signal_offer', destination, offer),
    [sendSignal],
  )

  const sendSignalAnswer = useCallback(
    (destination, answer) => sendSignal('signal_answer', destination, answer),
    [sendSignal],
  )

  const sendSignalIceCandidate = useCallback(
    (destination, candidate) => sendSignal('signal_ice_candidate', destination, candidate),
    [sendSignal],
  )

  const handleDataChannelMessage = useCallback(
    (peerName, rawData) => {
      try {
        const payload = JSON.parse(rawData)

        // Fase 3: Handle heartbeat messages
        if (payload.kind === 'heartbeat') {
          p2pLog(`Heartbeat received from ${peerName}`)
          const heartbeatMonitor = heartbeatMonitorsRef.current.get(peerName)
          if (heartbeatMonitor) {
            heartbeatMonitor.recordHeartbeat()
          }
          // Send heartbeat ACK
          const channel = dataChannelsRef.current.get(peerName)
          if (channel && channel.readyState === 'open') {
            try {
              channel.send(JSON.stringify({ kind: 'heartbeat_ack', timestamp: Date.now() }))
            } catch {
              // Ignore heartbeat ACK send failures.
            }
          }
          return
        }

        if (payload.kind === 'heartbeat_ack') {
          p2pLog(`Heartbeat ACK from ${peerName}`)
          const heartbeatMonitor = heartbeatMonitorsRef.current.get(peerName)
          if (heartbeatMonitor) {
            heartbeatMonitor.recordHeartbeat()
          }
          return
        }

        if (payload.kind === 'text') {
          appendMessage({ kind: 'received', text: `${peerName}: ${payload.message}` })
          return
        }

        if (payload.kind === 'file') {
          appendMessage({
            kind: 'file',
            text: `${peerName} te envio ${payload.filename} (${Number(payload.size || 0).toLocaleString()} bytes)`,
            file: {
              name: payload.filename,
              content: payload.content,
              mimeType: payload.mimeType,
            },
          })
        }
      } catch {
        appendMessage({ kind: 'error', text: `Mensaje DataChannel invalido desde ${peerName}` })
      }
    },
    [appendMessage],
  )

  const setupDataChannel = useCallback((peerName, channel) => {
      dataChannelsRef.current.set(peerName, channel)
      p2pLog(`Setting up DataChannel for ${peerName}`)

      channel.onopen = () => {
        p2pLog(`DataChannel opened with ${peerName}`)
        appendMessage({ kind: 'system', text: `Canal P2P activo con ${peerName}` })

        // Fase 4: Update diagnostics on channel open
        const pc = peerConnectionsRef.current.get(peerName)
        const diagnosis = diagnoseConnectionHealth(pc, channel, peerName)
        updatePeerDiagnostics(peerName, diagnosis)
        updatePeerConnectionState(peerName, 'connected')
        setIceInfoForPeer(peerName)

        // Fase 3: Start heartbeat monitoring when channel opens
        let heartbeatMonitor = heartbeatMonitorsRef.current.get(peerName)
        if (heartbeatMonitor) {
          heartbeatMonitor.stop()
        }

        heartbeatMonitor = new HeartbeatMonitor(
          peerName,
          channel,
          () => {
            // onHeartbeat - just logging
          },
          (reason) => {
            // onDead - connection is dead, trigger reconnection
            p2pLog(`Heartbeat dead for ${peerName}: ${reason}`)
            appendMessage({ kind: 'error', text: `Conexión perdida con ${peerName}, reintenando...` })
            
            // Fase 4: Update diagnostics on heartbeat dead
            updatePeerDiagnostics(peerName, { channelState: 'closed' })
            
            closePeerConnection(peerName)
          },
        )
        heartbeatMonitorsRef.current.set(peerName, heartbeatMonitor)
        heartbeatMonitor.start()
      }

      channel.onmessage = (event) => {
        p2pLog(`Message received from ${peerName}:`, event.data.substring(0, 50))
        handleDataChannelMessage(peerName, event.data)
      }

      channel.onerror = () => {
        p2pLog(`DataChannel error with ${peerName}`)
        appendMessage({ kind: 'error', text: `Error en DataChannel con ${peerName}` })
      }

      channel.onclose = () => {
        p2pLog(`DataChannel closed with ${peerName}`)
        dataChannelsRef.current.delete(peerName)

        // Fase 4: Update diagnostics on close
        updatePeerDiagnostics(peerName, { channelState: 'closed' })

        // Fase 3: Trigger automatic reconnection on DataChannel close
        appendMessage({ kind: 'system', text: `Canal P2P cerrado con ${peerName}, reconectando...` })
        const reconnectionManager = reconnectionManagersRef.current.get(peerName)
        if (!reconnectionManager || !reconnectionManager.isActive) {
          const newReconnectionManager = new PeerReconnectionManager(
            peerName,
            (attemptNumber) => {
              // onReconnect callback - try to establish connection again
              p2pLog(`Reconnection attempt ${attemptNumber} for ${peerName}`)
              
              // Fase 4: Update reconnection status
              updateReconnectionStatus(peerName, {
                isActive: true,
                attemptCount: attemptNumber,
                maxAttempts: newReconnectionManager.maxAttempts,
                nextRetryInMs: 0,
              })
              
              // The RTCPeerConnection might still exist; if so, try offer again.
              const pc = peerConnectionsRef.current.get(peerName)
              if (pc && pc.connectionState !== 'closed') {
                void (async () => {
                  if (pc.signalingState !== 'stable') {
                    return
                  }

                  const offer = await pc.createOffer()
                  await pc.setLocalDescription(offer)
                  sendSignalOffer(peerName, { sdp: pc.localDescription })
                })()
              }
            },
            (reason, attemptCount) => {
              // onGiveUp callback - max retries reached
              p2pLog(`Giving up on ${peerName} after ${attemptCount} attempts: ${reason}`)
              appendMessage({
                kind: 'error',
                text: `No se pudo reconectar con ${peerName} después de ${attemptCount} intentos`,
              })
              
              // Fase 4: Clear reconnection status on give up
              updateReconnectionStatus(peerName, null)
              
              closePeerConnection(peerName)
            },
          )
          reconnectionManagersRef.current.set(peerName, newReconnectionManager)
          newReconnectionManager.start()
        }
      }
    }, [
      appendMessage,
      closePeerConnection,
      handleDataChannelMessage,
      sendSignalOffer,
      setIceInfoForPeer,
      updatePeerConnectionState,
      updatePeerDiagnostics,
      updateReconnectionStatus,
    ])

  const ensurePeerConnection = useCallback(
    (peerName) => {
      const existing = peerConnectionsRef.current.get(peerName)
      if (existing) return existing

      p2pLog(`Creating RTCPeerConnection for ${peerName}`)
      const pc = new RTCPeerConnection(RTC_CONFIGURATION)

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          p2pLog(`ICE candidate gathered for ${peerName}`, event.candidate.candidate.substring(0, 50))
          sendSignalIceCandidate(peerName, { candidate: event.candidate.toJSON() })
        }
      }

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState
        p2pLog(`Connection state changed for ${peerName}:`, state)

        // Fase 4: Update connection state for UI
        updatePeerConnectionState(peerName, state)
        
        const channel = dataChannelsRef.current.get(peerName)
        const diagnosis = diagnoseConnectionHealth(pc, channel, peerName)
        updatePeerDiagnostics(peerName, diagnosis)

        // Fase 3: Handle different connection states with resilience
        if (state === 'failed') {
          p2pLog(`Connection failed for ${peerName}, attempting reconnection`)
          appendMessage({
            kind: 'error',
            text: `Conexión fallida con ${peerName}, reintenando...`,
          })
          closePeerConnection(peerName)
          // Reconnection starts automatically via heartbeat dead detection or DataChannel close
        } else if (state === 'disconnected') {
          p2pLog(`Connection disconnected for ${peerName}`)
          appendMessage({
            kind: 'system',
            text: `Desconexión temporal con ${peerName}`,
          })
          // Give it a moment to reconnect before closing
          setTimeout(() => {
            const currentState = pc.connectionState
            if (currentState === 'disconnected' || currentState === 'failed') {
              p2pLog(`Timeout on disconnected state for ${peerName}, closing`)
              closePeerConnection(peerName)
            }
          }, 5000) // Wait 5 seconds before force-closing
        } else if (state === 'closed') {
          p2pLog(`Connection closed for ${peerName}`)
          closePeerConnection(peerName)
        } else if (state === 'connected') {
          p2pLog(`Connection established with ${peerName}`)
          // Stop any active reconnection attempts
          const reconnectionManager = reconnectionManagersRef.current.get(peerName)
          if (reconnectionManager) {
            reconnectionManager.stop()
          }
          // Fase 4: Clear reconnection status on successful connection
          updateReconnectionStatus(peerName, null)
        }
      }

      pc.ondatachannel = (event) => {
        p2pLog(`DataChannel received from ${peerName}:`, event.channel.label)
        setupDataChannel(peerName, event.channel)
      }

      peerConnectionsRef.current.set(peerName, pc)
      return pc
    },
    [
      appendMessage,
      closePeerConnection,
      sendSignalIceCandidate,
      setupDataChannel,
      updatePeerConnectionState,
      updatePeerDiagnostics,
      updateReconnectionStatus,
    ],
  )

  const createAndSendOffer = useCallback(
    async (peerName) => {
      p2pLog(`Creating offer for ${peerName}`)
      const pc = ensurePeerConnection(peerName)

      let channel = dataChannelsRef.current.get(peerName)
      if (!channel) {
        p2pLog(`Creating DataChannel for ${peerName}`)
        channel = pc.createDataChannel('chat')
        setupDataChannel(peerName, channel)
      }

      if (pc.signalingState !== 'stable') {
        p2pLog(`Signaling state not stable for ${peerName}:`, pc.signalingState)
        return false
      }

      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      p2pLog(`Offer created and set as local description for ${peerName}`)
      return sendSignalOffer(peerName, { sdp: pc.localDescription })
    },
    [ensurePeerConnection, sendSignalOffer, setupDataChannel],
  )

  const handleSignalOffer = useCallback(
    async (peerName, payload) => {
      p2pLog(`Received offer from ${peerName}`)
      const sdpPayload = payload?.sdp || payload
      if (!sdpPayload?.type || !sdpPayload?.sdp) {
        p2pLog(`Invalid offer from ${peerName}`)
        appendMessage({ kind: 'error', text: `Oferta invalida recibida desde ${peerName}` })
        return
      }

      try {
        let pc = ensurePeerConnection(peerName)
        if (pc.signalingState !== 'stable') {
          p2pLog(`Signaling state not stable, closing and recreating for ${peerName}`)
          closePeerConnection(peerName)
          pc = ensurePeerConnection(peerName)
        }

        p2pLog(`Setting remote description (offer) for ${peerName}`)
        await pc.setRemoteDescription(new RTCSessionDescription(sdpPayload))
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        p2pLog(`Answer created for ${peerName}`)
        sendSignalAnswer(peerName, { sdp: pc.localDescription })
      } catch {
        p2pLog(`Error processing offer from ${peerName}`)
        appendMessage({ kind: 'error', text: `No se pudo procesar oferta de ${peerName}` })
      }
    },
    [appendMessage, closePeerConnection, ensurePeerConnection, sendSignalAnswer],
  )

  const handleSignalAnswer = useCallback(
    async (peerName, payload) => {
      p2pLog(`Received answer from ${peerName}`)
      const sdpPayload = payload?.sdp || payload
      if (!sdpPayload?.type || !sdpPayload?.sdp) {
        p2pLog(`Invalid answer from ${peerName}`)
        appendMessage({ kind: 'error', text: `Respuesta invalida recibida desde ${peerName}` })
        return
      }

      const pc = peerConnectionsRef.current.get(peerName)
      if (!pc) {
        p2pLog(`No peer connection pending for ${peerName}`)
        appendMessage({ kind: 'error', text: `No existe conexión P2P pendiente para ${peerName}` })
        return
      }

      try {
        p2pLog(`Setting remote description (answer) for ${peerName}`)
        await pc.setRemoteDescription(new RTCSessionDescription(sdpPayload))
      } catch {
        p2pLog(`Error processing answer from ${peerName}`)
        appendMessage({ kind: 'error', text: `No se pudo aplicar respuesta de ${peerName}` })
      }
    },
    [appendMessage],
  )

  const handleSignalIceCandidate = useCallback(
    async (peerName, payload) => {
      const candidatePayload = payload?.candidate || payload
      if (!candidatePayload) return

      p2pLog(`Received ICE candidate from ${peerName}`)
      const pc = ensurePeerConnection(peerName)
      try {
        await pc.addIceCandidate(new RTCIceCandidate(candidatePayload))
      } catch {
        p2pLog(`Error applying ICE candidate from ${peerName}`)
        appendMessage({ kind: 'error', text: `No se pudo aplicar ICE candidate de ${peerName}` })
      }
    },
    [appendMessage, ensurePeerConnection],
  )

  const resetConnectionState = useCallback(() => {
    closeAllPeerConnections()
    setConnected(false)
    setUsers([])
    setMyUsername('')
  }, [closeAllPeerConnections])

  const clearSignalingReconnectTimer = useCallback(() => {
    if (signalingReconnectTimeoutRef.current) {
      clearTimeout(signalingReconnectTimeoutRef.current)
      signalingReconnectTimeoutRef.current = null
    }
  }, [])

  const clearSignalingHeartbeat = useCallback(() => {
    if (signalingHeartbeatIntervalRef.current) {
      clearInterval(signalingHeartbeatIntervalRef.current)
      signalingHeartbeatIntervalRef.current = null
    }
  }, [])

  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true
    clearSignalingReconnectTimer()
    clearSignalingHeartbeat()
    signalingReconnectAttemptsRef.current = 0

    const ws = wsRef.current
    resetConnectionState()

    if (!ws) return

    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'signal_disconnect' }))
      ws.close()
    }
  }, [clearSignalingHeartbeat, clearSignalingReconnectTimer, resetConnectionState])

  const connect = useCallback(
    (rawName) => {
      const username = rawName.trim()
      if (!username) return

      isManualDisconnectRef.current = false
      clearSignalingReconnectTimer()
      clearSignalingHeartbeat()

      const ws = new WebSocket(`${signalingUrl}?username=${encodeURIComponent(username)}`)
      wsRef.current = ws

      ws.onopen = () => {
        signalingReconnectAttemptsRef.current = 0
        setConnected(true)
        appendMessage({ kind: 'system', text: 'Conectado al servidor de señalizacion (P2P)' })

        signalingHeartbeatIntervalRef.current = setInterval(() => {
          const currentWs = wsRef.current
          if (currentWs && currentWs.readyState === WebSocket.OPEN) {
            currentWs.send(
              JSON.stringify({
                type: 'signal_ping',
                timestamp: Date.now(),
              }),
            )
          }
        }, 10000)

        const iceInfo = getIceServerDebugInfo()
        p2pLog(`ICE Server Configuration - Total: ${iceInfo.totalServers} servers`, iceInfo)
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.type === 'signal_registered') {
          if (data.username) {
            setMyUsername(data.username)
          }
          appendMessage({ kind: 'system', text: `Registrado para señalizacion como ${data.username}` })
          return
        }

        if (data.type === 'signal_peer_list') {
          const nextUsers = data.users || []
          setUsers(nextUsers)

          const activePeers = new Set(nextUsers)
          for (const peerName of peerConnectionsRef.current.keys()) {
            if (!activePeers.has(peerName)) {
              closePeerConnection(peerName)
            }
          }
          return
        }

        if (data.type === 'signal_offer') {
          void handleSignalOffer(data.from, data.payload)
          return
        }

        if (data.type === 'signal_answer') {
          void handleSignalAnswer(data.from, data.payload)
          return
        }

        if (data.type === 'signal_ice_candidate') {
          void handleSignalIceCandidate(data.from, data.payload)
          return
        }

        if (data.type === 'signal_error') {
          appendMessage({ kind: 'error', text: data.message || 'Error de señalizacion' })
          return
        }

        if (data.type === 'signal_pong') {
          p2pLog('Signaling keepalive pong', data.timestamp)
        }
      }

      ws.onclose = () => {
        clearSignalingHeartbeat()
        appendMessage({ kind: 'system', text: 'Conexion de señalizacion cerrada' })
        resetConnectionState()

        if (!isManualDisconnectRef.current) {
          signalingReconnectAttemptsRef.current += 1
          const attempt = signalingReconnectAttemptsRef.current
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 8000)

          appendMessage({
            kind: 'system',
            text: `Reintentando signaling (${attempt}) en ${Math.ceil(delay / 1000)}s...`,
          })

          clearSignalingReconnectTimer()
          signalingReconnectTimeoutRef.current = setTimeout(() => {
            if (connectRef.current) {
              connectRef.current(username)
            }
          }, delay)
        }
      }

      ws.onerror = () => {
        appendMessage({ kind: 'error', text: 'Error de conexion con servidor de señalizacion' })
      }
    },
    [
      appendMessage,
      closePeerConnection,
      handleSignalAnswer,
      handleSignalIceCandidate,
      handleSignalOffer,
      resetConnectionState,
      clearSignalingHeartbeat,
      clearSignalingReconnectTimer,
      signalingUrl,
    ],
  )

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  const sendText = useCallback(
    async (destination, rawMessage) => {
      const message = rawMessage.trim()
      if (!connected || !destination || !message) return false

      const channel = dataChannelsRef.current.get(destination)
      if (channel && channel.readyState === 'open') {
        channel.send(
          JSON.stringify({
            kind: 'text',
            from: myUsername,
            message,
          }),
        )
        appendMessage({ kind: 'sent', text: `Tu -> ${destination}: ${message}` })
        return true
      }

      const started = await createAndSendOffer(destination)
      if (started) {
        appendMessage({
          kind: 'system',
          text: `Iniciando enlace P2P con ${destination}. Reintenta enviar en unos segundos.`,
        })
      }
      return false
    },
    [appendMessage, connected, createAndSendOffer, myUsername],
  )

  const sendFile = useCallback(
    async (destination, file) => {
      if (!connected || !destination || !file) return false

      const channel = dataChannelsRef.current.get(destination)
      if (!channel || channel.readyState !== 'open') {
        const started = await createAndSendOffer(destination)
        if (started) {
          appendMessage({
            kind: 'system',
            text: `Iniciando enlace P2P con ${destination}. Reintenta enviar el archivo en unos segundos.`,
          })
        }
        return false
      }

      const base64 = await encodeFileAsBase64(file)
      channel.send(
        JSON.stringify({
          kind: 'file',
          from: myUsername,
          filename: file.name,
          content: base64,
          mimeType: file.type || 'application/octet-stream',
          size: file.size,
        }),
      )

      appendMessage({
        kind: 'sent',
        text: `Tu -> ${destination}: archivo ${file.name} (${file.size.toLocaleString()} bytes)`,
      })
      return true
    },
    [appendMessage, connected, createAndSendOffer, myUsername],
  )

  useEffect(() => {
    return () => {
      clearSignalingReconnectTimer()
      clearSignalingHeartbeat()
      isManualDisconnectRef.current = true

      closeAllPeerConnections()
      const ws = wsRef.current
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'signal_disconnect' }))
        ws.close()
      }
    }
  }, [clearSignalingHeartbeat, clearSignalingReconnectTimer, closeAllPeerConnections])

  return {
    connected,
    myUsername,
    users,
    messages,
    // Fase 4: Export UI & monitoring states
    peerConnectionStates,
    diagnosticsByPeer,
    reconnectionStatusByPeer,
    iceInfoByPeer,
    allPeers: users.filter((name) => name !== myUsername),
    // Connection methods
    connect,
    disconnect,
    sendText,
    sendFile,
    sendSignalOffer,
    sendSignalAnswer,
    sendSignalIceCandidate,
  }
}
