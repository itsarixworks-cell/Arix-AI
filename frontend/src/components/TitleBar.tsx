import { Activity, ShieldCheck } from 'lucide-react'

export function TitleBar() {
  return (
    <header className="titlebar" id="application-titlebar">
      <div className="titlebar-brand">
        <span className="brand-mark"><Activity size={14} strokeWidth={2.5} /></span>
        <span>ARIX</span><span className="brand-muted">DESKTOP</span>
      </div>
      <div className="titlebar-security"><ShieldCheck size={13} /> Local encrypted bridge</div>
    </header>
  )
}
