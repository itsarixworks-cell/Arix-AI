import { lazy, Suspense, useMemo, useState } from 'react'
import { Mic, Power, Settings2, Sparkles } from 'lucide-react'
import { AudioOrb } from './components/AudioOrb'
import { NavigationRail, type WorkspaceView } from './components/NavigationRail'
import { SettingsModal } from './components/SettingsModal'
import { TitleBar } from './components/TitleBar'
import { TranscriptPanel } from './components/TranscriptPanel'
import { useArixSession } from './hooks/useArixSession'
import type { SessionConfig } from './types/arix'

const MemoryGraphWorkspace = lazy(() =>
  import('./components/memory/MemoryGraphWorkspace').then((module) => ({
    default: module.MemoryGraphWorkspace,
  })),
)

const defaultConfig: SessionConfig = {
  apiKey: '',
  model: 'gemini-3.1-flash-live-preview',
  voice: 'Kore',
  systemInstruction: 'You are Arix, a concise, capable voice-first desktop assistant. Speak naturally and use only the tools supplied to this session. Never claim an action succeeded unless its tool result confirms success. When a tool returns confirmation_required, clearly ask the user for confirmation and retry only after they explicitly confirm. Prefer known-folder paths such as Documents/Arix/report.docx or Desktop/note.txt. Use create_file for a new file and write only for an existing file. A messaging composer is not a sent message unless the result explicitly says sent=true.',
}

export default function App() {
  const session = useArixSession()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeView, setActiveView] = useState<WorkspaceView>('voice')
  const [config, setConfig] = useState(defaultConfig)
  const connected = !['offline', 'error'].includes(session.status)
  const latest = useMemo(() => session.transcripts.at(-1), [session.transcripts])

  const toggleSession = async () => {
    if (connected) return session.disconnect()
    if (!config.apiKey.trim()) return setSettingsOpen(true)
    try { await session.connect(config) } catch { setSettingsOpen(true) }
  }

  return (
    <div className={`app-shell antialiased ${activeView === 'memory' ? 'memory-mode' : ''}`}>
      <TitleBar />
      <NavigationRail activeView={activeView} onNavigate={setActiveView} onSettings={() => setSettingsOpen(true)} />
      {activeView === 'voice' ? <>
      <main className="command-center" id="command-center">
        <header className="workspace-header">
          <div><span className="eyebrow"><Sparkles size={12} /> GEMINI LIVE</span><h1>Voice link</h1></div>
          <button className="settings-trigger" onClick={() => setSettingsOpen(true)}><Settings2 size={16} /> Configure</button>
        </header>

        <section className="voice-workspace" id="voice-workspace">
          <div className="ambient ambient-one" /><div className="ambient ambient-two" />
          <AudioOrb status={session.status} level={session.audioLevel} />
          {latest && session.status !== 'offline' && <div className={`transient-caption ${latest.role}`}><span>{latest.role === 'user' ? 'YOU' : 'ARIX'}</span>{latest.text}</div>}
          <div className="session-controls">
            <p><span className={`connection-pulse ${session.status}`} />{session.statusMessage}</p>
            <button className={`session-button ${connected ? 'disconnect' : ''}`} onClick={toggleSession} disabled={session.status === 'connecting'}>
              {connected ? <Power size={18} /> : <Mic size={18} />}
              {session.status === 'connecting' ? 'Establishing link…' : connected ? 'End live session' : 'Start live session'}
            </button>
            <span className="shortcut-hint">Natural voice interruption enabled</span>
          </div>
        </section>
      </main>
      <TranscriptPanel
        status={session.status}
        transcripts={session.transcripts}
        toolResults={session.toolResults}
        onSend={session.sendText}
        onClear={session.clearHistory}
        onConfirmTool={(name) => {
          session.sendText(`I explicitly confirm the pending ${name.replaceAll('_', ' ')} action. Retry it with confirmed=true.`)
        }}
      />
      </> : (
        <Suspense fallback={<main className="memory-workspace memory-loading">Loading memory graph…</main>}>
          <MemoryGraphWorkspace />
        </Suspense>
      )}
      <SettingsModal open={settingsOpen} value={config} onChange={setConfig} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
