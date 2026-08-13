import { useCallback, useEffect, useRef, useState } from 'react'
import type { PipelineStatus, ServerEvent, SessionConfig, TranscriptEntry } from '../types/arix'
import { useAudioEngine } from './useAudioEngine'

const SOCKET_URL = import.meta.env.VITE_ARIX_WS_URL ?? 'ws://127.0.0.1:8765/ws/live'

export function useArixSession() {
  const [status, setStatus] = useState<PipelineStatus>('offline')
  const [statusMessage, setStatusMessage] = useState('Ready when you are')
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([])
  const socketRef = useRef<WebSocket | null>(null)

  const sendAudio = useCallback((chunk: ArrayBuffer) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(chunk)
  }, [])
  const { level: audioLevel, startCapture, stopCapture, playPcm, clearPlayback } = useAudioEngine(sendAudio)

  const upsertTranscript = useCallback((role: 'user' | 'assistant', text: string, final = false) => {
    setTranscripts((current) => {
      const last = current.at(-1)
      if (last?.role === role && !last.final) {
        return [...current.slice(0, -1), { ...last, text: `${last.text}${text}`, final }]
      }
      return [...current, { id: crypto.randomUUID(), role, text, timestamp: Date.now(), final }]
    })
  }, [])

  const disconnect = useCallback(() => {
    stopCapture()
    socketRef.current?.close(1000, 'User ended the session')
    socketRef.current = null
    setStatus('offline')
    setStatusMessage('Session ended')
  }, [stopCapture])

  const connect = useCallback(async (config: SessionConfig) => {
    if (!config.apiKey.trim()) throw new Error('Enter a Gemini API key in Settings first.')
    setStatus('connecting')
    setStatusMessage('Opening a secure live channel')
    const socket = new WebSocket(SOCKET_URL)
    socket.binaryType = 'arraybuffer'
    socketRef.current = socket

    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'session.start', ...config }))
    }
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as ServerEvent
      if (event.type === 'status') {
        setStatus(event.status)
        setStatusMessage(event.message ?? event.status)
      } else if (event.type === 'session.ready') {
        setStatus('listening')
        setStatusMessage('Listening for your voice')
        void startCapture().catch((error: Error) => {
          setStatus('error')
          setStatusMessage(`Microphone unavailable: ${error.message}`)
        })
      } else if (event.type === 'audio') {
        setStatus('speaking')
        setStatusMessage('Arix is speaking')
        const sampleRate = Number(event.mime_type.match(/rate=(\d+)/)?.[1] ?? 24000)
        void playPcm(event.data, sampleRate)
      } else if (event.type === 'transcript') {
        upsertTranscript(event.role, event.text, event.final)
      } else if (event.type === 'turn.complete') {
        setTranscripts((current) => current.map((entry) => ({ ...entry, final: true })))
        setStatus('listening')
        setStatusMessage('Listening for your voice')
      } else if (event.type === 'interrupted') {
        clearPlayback()
        setStatus('listening')
        setStatusMessage('Interrupted — listening')
      } else if (event.type === 'error') {
        setStatus('error')
        setStatusMessage(event.message)
      }
    }
    socket.onerror = () => {
      setStatus('error')
      setStatusMessage('Cannot reach the local Arix backend')
    }
    socket.onclose = () => {
      stopCapture()
      socketRef.current = null
      setStatus((current) => current === 'error' ? current : 'offline')
    }
  }, [clearPlayback, playPcm, startCapture, stopCapture, upsertTranscript])

  const sendText = useCallback((text: string) => {
    if (!text.trim() || socketRef.current?.readyState !== WebSocket.OPEN) return false
    socketRef.current.send(JSON.stringify({ type: 'text', text: text.trim() }))
    upsertTranscript('user', text.trim(), true)
    setStatus('processing')
    setStatusMessage('Arix is thinking')
    return true
  }, [upsertTranscript])

  const clearTranscripts = useCallback(() => setTranscripts([]), [])
  useEffect(() => () => socketRef.current?.close(), [])

  return { status, statusMessage, transcripts, audioLevel, connect, disconnect, sendText, clearTranscripts }
}
