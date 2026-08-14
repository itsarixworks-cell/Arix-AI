import { useEffect, useRef, useState } from 'react'
import { Bot, Eraser, MessageSquare, Send, UserRound } from 'lucide-react'
import type { PipelineStatus, TranscriptEntry } from '../types/arix'

interface Props {
  status: PipelineStatus
  transcripts: TranscriptEntry[]
  onSend: (text: string) => boolean
  onClear: () => void
}

export function TranscriptPanel({ status, transcripts, onSend, onClear }: Props) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const connected = !['offline', 'connecting', 'error'].includes(status)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcripts])

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
