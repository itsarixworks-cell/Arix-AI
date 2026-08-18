import { AudioLines, Blocks, BrainCircuit, Clock3, FolderKanban, Home, MessageSquareText, Settings2 } from 'lucide-react'

export type WorkspaceView = 'voice' | 'memory'

interface Props {
  activeView: WorkspaceView
  onNavigate: (view: WorkspaceView) => void
  onSettings: () => void
}

const nav = [
  { icon: Home, label: 'Command center', view: 'voice' as const },
  { icon: AudioLines, label: 'Live voice', view: 'voice' as const },
  { icon: BrainCircuit, label: 'Memory', view: 'memory' as const },
  { icon: MessageSquareText, label: 'Conversations', disabled: true },
  { icon: Clock3, label: 'Activity', disabled: true },
  { icon: FolderKanban, label: 'Workspace', disabled: true },
  { icon: Blocks, label: 'Tools', disabled: true },
]

export function NavigationRail({ activeView, onNavigate, onSettings }: Props) {
  return (
    <nav className="navigation-rail" aria-label="Primary navigation">
      <div className="rail-logo">A</div>
      <div className="rail-items">
        {nav.map(({ icon: Icon, label, view, disabled }) => (
          <button
            className={`rail-button ${view === activeView ? 'active' : ''}`}
            disabled={disabled}
            title={disabled ? `${label} — coming soon` : label}
            onClick={() => view && onNavigate(view)}
            key={label}
          >
            <Icon size={19} strokeWidth={1.8} /><span className="rail-tooltip">{label}</span>
          </button>
        ))}
      </div>
      <button className="rail-button" onClick={onSettings} title="Settings"><Settings2 size={19} /><span className="rail-tooltip">Settings</span></button>
      <span className="rail-version">01</span>
    </nav>
  )
}
