import { AudioLines, Blocks, Clock3, FolderKanban, Home, MessageSquareText, Settings2 } from 'lucide-react'

interface Props { onSettings: () => void }

const nav = [
  { icon: Home, label: 'Command center' },
  { icon: AudioLines, label: 'Live voice', active: true },
  { icon: MessageSquareText, label: 'Conversations' },
  { icon: Clock3, label: 'Activity' },
  { icon: FolderKanban, label: 'Workspace' },
  { icon: Blocks, label: 'Tools', disabled: true },
]

export function NavigationRail({ onSettings }: Props) {
  return (
    <nav className="navigation-rail" aria-label="Primary navigation">
      <div className="rail-logo">A</div>
      <div className="rail-items">
        {nav.map(({ icon: Icon, label, active, disabled }) => (
          <button className={`rail-button ${active ? 'active' : ''}`} disabled={disabled} title={disabled ? `${label} — coming soon` : label} key={label}>
            <Icon size={19} strokeWidth={1.8} /><span className="rail-tooltip">{label}</span>
          </button>
        ))}
      </div>
      <button className="rail-button" onClick={onSettings} title="Settings"><Settings2 size={19} /><span className="rail-tooltip">Settings</span></button>
      <span className="rail-version">01</span>
    </nav>
  )
}
