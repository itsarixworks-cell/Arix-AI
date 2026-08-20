import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, CheckCircle2, Eraser, MessageSquare, Send, UserRound, Wrench } from 'lucide-react'
import type { PipelineStatus, ToolResultEntry, TranscriptEntry } from '../types/arix'

interface Props {
  status: PipelineStatus
  transcripts: TranscriptEntry[]
  toolResults: ToolResultEntry[]
  onSend: (text: string) => boolean
  onClear: () => void
  onConfirmTool: (name: string) => void
}

export function TranscriptPanel({ status, transcripts, toolResults, onSend, onClear, onConfirmTool }: Props) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const connected = !['offline', 'connecting', 'error'].includes(status)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [toolResults, transcripts])

  const submit = () => {
    if (onSend(draft)) setDraft('')
  }

  return (
    <aside className="transcript-panel" id="live-transcription-panel">
      <header className="panel-heading">
        <div><span className="eyebrow">LIVE FEED</span><h2>Conversation</h2></div>
        <button className="icon-button" onClick={onClear} title="Clear transcript"><Eraser size={16} /></button>
      </header>
      <div className="panel-rule"><span className={connected ? 'online' : ''} />{connected ? 'Channel open' : 'Channel closed'}</div>
      {toolResults.length > 0 && (
        <section className="tool-activity" aria-label="Executable action history">
          <header><Wrench size={12} /> Recent actions</header>
          {toolResults.slice(-4).reverse().map((entry) => {
            const output = entry.result.result
            const path = output && ['path', 'output_path', 'destination']
              .map((key) => output[key])
              .find((value): value is string => typeof value === 'string')
            const needsConfirmation = entry.result.error_code === 'confirmation_required'
            return (
              <article className={`tool-result ${entry.result.ok ? 'success' : 'failure'}`} key={entry.id}>
                {entry.result.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                <div>
                  <strong>{entry.name.replaceAll('_', ' ')}</strong>
                  <p>{entry.result.ok ? (path ? `Saved: ${path}` : 'Action completed and confirmed') : entry.result.error}</p>
                  {typeof entry.result.duration_ms === 'number' && <small>{entry.result.duration_ms} ms</small>}
                </div>
                {needsConfirmation && connected && (
                  <button onClick={() => onConfirmTool(entry.name)}>Confirm</button>
                )}
              </article>
            )
          })}
        </section>
      )}
      <div className="transcript-stream">
        {transcripts.length === 0 ? (
          <div className="empty-transcript"><MessageSquare size={24} /><p>Your live transcript will appear here.</p><span>Start a session, then speak naturally.</span></div>
        ) : transcripts.map((entry) => (
          <article className={`transcript-entry ${entry.role}`} key={entry.id}>
            <div className="speaker-icon">{entry.role === 'user' ? <UserRound size={14} /> : <Bot size={14} />}</div>
            <div className="entry-content">
              <header><strong>{entry.role === 'user' ? 'You' : 'Arix'}</strong><time>{new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></header>
              <p>{entry.text}<span className={!entry.final ? 'typing-caret' : ''} /></p>
            </div>
          </article>
        ))}
        <div ref={endRef} />
      </div>
      <footer className="text-composer">
        <input value={draft} disabled={!connected} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && submit()} placeholder={connected ? 'Send a text message…' : 'Connect to send a message'} aria-label="Message Arix" />
        <button onClick={submit} disabled={!connected || !draft.trim()} aria-label="Send message"><Send size={16} /></button>
      </footer>
    </aside>
  )
}
