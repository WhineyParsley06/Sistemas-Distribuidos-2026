/**
 * ICE Server Configuration Manager
 * Provides resilient STUN/TURN configuration for WebRTC connections
 * Supports fallback to public servers and custom configuration via environment variables
 */

// Public STUN servers (free, widely available)
const PUBLIC_STUN_SERVERS = [
  'stun:stun.l.google.com:19302',
  'stun:stun1.l.google.com:19302',
  'stun:stun2.l.google.com:19302',
  'stun:stun.stunprotocol.org:3478',
  'stun:stun.services.mozilla.com:3478',
]

/**
 * Build RTCConfiguration with ICE servers
 * Supports:
 * - Multiple STUN servers for redundancy and fallback
 * - TURN servers with optional credentials
 * - Custom servers via environment variables
 *
 * Environment variables (optional):
 * - VITE_ICE_STUN_SERVERS: comma-separated STUN server URLs (overrides defaults)
 * - VITE_ICE_TURN_SERVER: TURN server URL (e.g., turn:turnserver.com)
 * - VITE_ICE_TURN_USERNAME: TURN server username
 * - VITE_ICE_TURN_PASSWORD: TURN server password
 *
 * @returns {RTCConfiguration} Configured RTCConfiguration object
 */
export function buildIceConfiguration() {
  const iceServers = []

  // Load STUN servers from environment or use defaults
  const stunServersEnv = import.meta.env.VITE_ICE_STUN_SERVERS
  const stunServers = stunServersEnv
    ? stunServersEnv.split(',').map((url) => url.trim()).filter(Boolean)
    : PUBLIC_STUN_SERVERS

  // Add STUN servers
  stunServers.forEach((url) => {
    iceServers.push({ urls: url })
  })

  // Load and add TURN server if configured
  const turnServer = import.meta.env.VITE_ICE_TURN_SERVER
  if (turnServer) {
    const turnConfig = { urls: turnServer }
    const turnUsername = import.meta.env.VITE_ICE_TURN_USERNAME
    const turnPassword = import.meta.env.VITE_ICE_TURN_PASSWORD

    if (turnUsername) turnConfig.username = turnUsername
    if (turnPassword) turnConfig.credential = turnPassword

    iceServers.push(turnConfig)
  }

  return {
    iceServers,
    iceTransportPolicy: 'all', // Allow both host and srflx candidates
  }
}

/**
 * Get debugging information about configured ICE servers
 * @returns {Object} Debug information with server details
 */
export function getIceServerDebugInfo() {
  const config = buildIceConfiguration()
  const info = {
    totalServers: config.iceServers.length,
    stunServers: [],
    turnServers: [],
  }

  config.iceServers.forEach((server) => {
    const urls = Array.isArray(server.urls) ? server.urls : [server.urls]
    const type = server.username ? 'TURN' : 'STUN'

    urls.forEach((url) => {
      if (type === 'TURN') {
        info.turnServers.push({
          url: url.replace(/^turn:/i, ''),
          hasAuth: !!server.username,
        })
      } else {
        info.stunServers.push(url.replace(/^stun:/i, ''))
      }
    })
  })

  return info
}
