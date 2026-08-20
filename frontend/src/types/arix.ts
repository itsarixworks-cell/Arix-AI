export type PipelineStatus = 'offline' | 'connecting' | 'listening' | 'processing' | 'speaking' | 'error'

export type TranscriptRole = 'user' | 'assistant' | 'system'

export interface TranscriptEntry {
  id: string
  role: TranscriptRole
  text: string
  timestamp: number
  final: boolean
}

export interface ToolExecutionResult {
  ok: boolean
  result?: Record<string, unknown>
  error?: string
  error_code?: 'confirmation_required' | 'path_error' | 'invalid_arguments' | 'unavailable' | 'execution_failed' | 'unknown_tool' | string
  tool?: string
  duration_ms?: number
}

export interface ToolResultEntry {
  id: string
  name: string
  result: ToolExecutionResult
  timestamp: number
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
  | { type: 'tool.result'; name: string; result: ToolExecutionResult }

declare global {
  interface Window {
    arixDesktop?: {
      getVersion: () => Promise<string>
      openExternal: (url: string) => Promise<boolean>
      platform: string
    }
  }
}
