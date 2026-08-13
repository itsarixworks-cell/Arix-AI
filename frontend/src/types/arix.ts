export type PipelineStatus = 'offline' | 'connecting' | 'listening' | 'processing' | 'speaking' | 'error'

export type TranscriptRole = 'user' | 'assistant' | 'system'

export interface TranscriptEntry {
  id: string
  role: TranscriptRole
  text: string
  timestamp: number
  final: boolean
}

export interface SessionConfig {
  apiKey: string
  model: string
  voice: string
  systemInstruction: string
}

export type ServerEvent =
  | { type: 'status'; status: PipelineStatus; message?: string }
  | { type: 'transcript'; role: 'user' | 'assistant'; text: string; final?: boolean }
  | { type: 'audio'; data: string; mime_type: string }
  | { type: 'turn.complete' }
  | { type: 'interrupted' }
  | { type: 'error'; code?: string; message: string }
  | { type: 'session.ready'; model: string }

declare global {
  interface Window {
    arixDesktop?: {
      getVersion: () => Promise<string>
      openExternal: (url: string) => Promise<boolean>
      platform: string
    }
  }
}
