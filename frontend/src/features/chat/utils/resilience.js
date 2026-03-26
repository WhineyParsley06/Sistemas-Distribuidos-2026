/**
 * P2P Resilience & Error Recovery Manager
 * Provides automatic reconnection, heartbeat monitoring, and resource cleanup
 */

const DEBUG_RESILIENCE = import.meta.env.VITE_DEBUG_P2P === 'true'

const resilience_log = (message, data) => {
  if (DEBUG_RESILIENCE) {
    console.log(`[P2P:Resilience] ${message}`, data || '')
  }
}

/**
 * Exponential backoff calculator
 * Retries with increasing delay: 500ms, 1s, 2s, 4s, ..., max 30s
 *
 * @param {number} attemptNumber - Current attempt (0-indexed)
 * @param {number} baseDelayMs - Base delay in milliseconds (default 500)
 * @param {number} maxDelayMs - Maximum delay cap (default 30000)
 * @returns {number} Delay in milliseconds for this attempt
 */
export function calculateBackoff(attemptNumber, baseDelayMs = 500, maxDelayMs = 30000) {
  const delay = baseDelayMs * Math.pow(2, attemptNumber)
  return Math.min(delay, maxDelayMs)
}

/**
 * Reconnection Manager for WebRTC peer connections
 * Handles automatic reconnection with exponential backoff
 */
export class PeerReconnectionManager {
  constructor(peerName, onReconnect, onGiveUp) {
    this.peerName = peerName
    this.onReconnect = onReconnect // callback(attemptNumber)
    this.onGiveUp = onGiveUp // callback(reason, attemptCount)

    this.attemptCount = 0
    this.maxAttempts = 5
    this.timeoutId = null
    this.isActive = true
    this.lastAttemptTime = null
  }

  /**
   * Start reconnection retry loop
   */
  start() {
    if (!this.isActive) {
      resilience_log(`Reconnection already in progress for ${this.peerName}`)
      return
    }

    resilience_log(`Starting reconnection for ${this.peerName}`)
    this.attemptCount = 0
    this._scheduleRetry()
  }

  _scheduleRetry() {
    if (this.attemptCount >= this.maxAttempts) {
      resilience_log(`Max reconnection attempts reached for ${this.peerName}`, {
        attempts: this.attemptCount,
      })
      this.isActive = false
      this.onGiveUp?.(`Max ${this.maxAttempts} attempts reached`, this.attemptCount)
      return
    }

    const delay = calculateBackoff(this.attemptCount)
    resilience_log(`Scheduling reconnection for ${this.peerName} in ${delay}ms (attempt ${this.attemptCount + 1}/${this.maxAttempts})`)

    this.timeoutId = setTimeout(() => {
      this.lastAttemptTime = Date.now()
      this.attemptCount++
      resilience_log(`Attempting reconnection for ${this.peerName} (attempt ${this.attemptCount}/${this.maxAttempts})`)

      this.onReconnect?.(this.attemptCount)
      // Schedule next attempt if this one doesn't succeed
      this._scheduleRetry()
    }, delay)
  }

  /**
   * Stop reconnection attempts (successful or manual)
   */
  stop() {
    if (this.timeoutId) {
      clearTimeout(this.timeoutId)
      this.timeoutId = null
    }
    this.isActive = false
    resilience_log(`Stopped reconnection attempts for ${this.peerName}`)
  }

  getStatus() {
    return {
      peerName: this.peerName,
      attemptCount: this.attemptCount,
      maxAttempts: this.maxAttempts,
      isActive: this.isActive,
      lastAttemptTime: this.lastAttemptTime,
    }
  }
}

/**
 * Heartbeat Monitor for verifying connection health
 * Periodic ping/pong to detect dead connections
 */
export class HeartbeatMonitor {
  constructor(peerName, channel, onHeartbeat, onDead) {
    this.peerName = peerName
    this.channel = channel
    this.onHeartbeat = onHeartbeat // callback()
    this.onDead = onDead // callback(reason)

    this.intervalId = null
    this.lastHeartbeatTime = Date.now()
    this.missedHeartbeats = 0
    this.isMonitoring = false

    this.heartbeatIntervalMs = 5000
    this.heartbeatTimeoutMs = 10000
    this.maxMissedHeartbeats = 3
  }

  /**
   * Start heartbeat monitoring
   */
  start() {
    if (this.isMonitoring) {
      resilience_log(`Heartbeat already monitoring for ${this.peerName}`)
      return
    }

    this.isMonitoring = true
    this.missedHeartbeats = 0
    resilience_log(`Starting heartbeat monitor for ${this.peerName} (interval: ${this.heartbeatIntervalMs}ms)`)

    this.intervalId = setInterval(() => {
      if (!this.channel || this.channel.readyState !== 'open') {
        resilience_log(`DataChannel not open for ${this.peerName}, stopping heartbeat`)
        this.stop()
        return
      }

      try {
        this.channel.send(JSON.stringify({ kind: 'heartbeat', timestamp: Date.now() }))
        this.lastHeartbeatTime = Date.now()
        resilience_log(`Heartbeat sent to ${this.peerName}`)
        this.onHeartbeat?.()
      } catch (error) {
        resilience_log(`Failed to send heartbeat to ${this.peerName}:`, error.message)
        this.missedHeartbeats++
        if (this.missedHeartbeats >= this.maxMissedHeartbeats) {
          this.stop()
          this.onDead?.(
            `Missed ${this.maxMissedHeartbeats} heartbeats to ${this.peerName}`,
          )
        }
      }
    }, this.heartbeatIntervalMs)
  }

  /**
   * Stop heartbeat monitoring
   */
  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId)
      this.intervalId = null
    }
    this.isMonitoring = false
    resilience_log(`Stopped heartbeat monitor for ${this.peerName}`)
  }

  /**
   * Record received heartbeat (ACK)
   */
  recordHeartbeat() {
    this.missedHeartbeats = Math.max(0, this.missedHeartbeats - 1)
    resilience_log(`Heartbeat ACK from ${this.peerName}`, {
      missedHeartbeats: this.missedHeartbeats,
    })
  }

  getStatus() {
    return {
      peerName: this.peerName,
      isMonitoring: this.isMonitoring,
      lastHeartbeatTime: this.lastHeartbeatTime,
      missedHeartbeats: this.missedHeartbeats,
      maxMissedHeartbeats: this.maxMissedHeartbeats,
    }
  }
}

/**
 * Safe cleanup function for WebRTC resources
 * Prevents memory leaks and zombie connections
 */
export function cleanupPeerResources(pc, channel) {
  const errors = []

  // Close DataChannel
  if (channel) {
    try {
      if (channel.readyState !== 'closed') {
        channel.close()
      }
    } catch (error) {
      errors.push(`DataChannel close error: ${error.message}`)
    }
  }

  // Close RTCPeerConnection
  if (pc) {
    try {
      if (pc.connectionState !== 'closed') {
        // Close all SENDERS and RECEIVERS
        pc.getSenders().forEach((sender) => {
          try {
            pc.removeTrack(sender)
          } catch {
            // Sender may already be detached.
          }
        })

        pc.close()
      }
    } catch (error) {
      errors.push(`RTCPeerConnection close error: ${error.message}`)
    }
  }

  if (errors.length > 0) {
    resilience_log(`Cleanup errors:`, errors)
  }
}

/**
 * Connection health check
 * Returns diagnosis info about connection state
 */
export function diagnoseConnectionHealth(pc, channel, peerName) {
  const diagnosis = {
    peerName,
    rtcState: pc?.connectionState || 'unknown',
    rtcIceState: pc?.iceConnectionState || 'unknown',
    rtcSignalingState: pc?.signalingState || 'unknown',
    channelState: channel?.readyState || 'closed',
    timestamp: Date.now(),
    isHealthy: false,
  }

  // Healthy if connection is connected and channel is open
  diagnosis.isHealthy =
    diagnosis.rtcState === 'connected' &&
    diagnosis.channelState === 'open'

  return diagnosis
}
