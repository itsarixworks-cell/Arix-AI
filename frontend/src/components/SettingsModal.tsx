import { ExternalLink, Eye, EyeOff, KeyRound, Settings2, Shield, X } from 'lucide-react'
import { useState } from 'react'
import type { SessionConfig } from '../types/arix'

interface Props { open: boolean; value: SessionConfig; onChange: (value: SessionConfig) => void; onClose: () => void }

export function SettingsModal({ open, value, onChange, onClose }: Props) {
  const [showKey, setShowKey] = useState(false)
  if (!open) return null
  const update = (field: keyof SessionConfig, fieldValue: string) => onChange({ ...value, [field]: fieldValue })
  const openDocs = () => window.arixDesktop?.openExternal('https://aistudio.google.com/apikey') ?? window.open('https://aistudio.google.com/apikey')

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.currentTarget === event.target && onClose()}>
      <section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header><div className="settings-symbol"><Settings2 size={20} /></div><div><span className="eyebrow">CONFIGURATION</span><h2 id="settings-title">Live session settings</h2></div><button className="icon-button close" onClick={onClose}><X size={18} /></button></header>
        <div className="settings-body">
          <label className="field-label"><span><KeyRound size={15} /> Gemini API key</span><div className="secret-input"><input type={showKey ? 'text' : 'password'} value={value.apiKey} onChange={(event) => update('apiKey', event.target.value)} placeholder="AIza…" autoComplete="off" /><button onClick={() => setShowKey((current) => !current)}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div><small><Shield size={12} /> Sent only to the local Python backend for this session. It is not saved.</small></label>
          <div className="field-grid">
            <label className="field-label"><span>Live model</span><input value={value.model} onChange={(event) => update('model', event.target.value)} /></label>
            <label className="field-label"><span>Voice</span><select value={value.voice} onChange={(event) => update('voice', event.target.value)}><option value="Kore">Kore</option><option value="Aoede">Aoede</option><option value="Charon">Charon</option><option value="Fenrir">Fenrir</option><option value="Puck">Puck</option></select></label>
          </div>
          <label className="field-label"><span>System instruction</span><textarea value={value.systemInstruction} onChange={(event) => update('systemInstruction', event.target.value)} rows={4} /></label>
          <button className="text-link" onClick={openDocs}><ExternalLink size={14} /> Create or manage a key in Google AI Studio</button>
        </div>
        <footer><span>Settings apply to the next live session.</span><button className="primary-compact" onClick={onClose}>Save settings</button></footer>
      </section>
    </div>
  )
}
