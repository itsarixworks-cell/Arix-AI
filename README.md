# Arix AI

Arix AI is a local, voice-first Windows desktop assistant. Phase 1 provides a premium Electron interface and a Python 3.11 bridge to the Google Gemini Live API for low-latency microphone conversation, native audio responses, live transcription, and text messages.

> Arix is intentionally a desktop application, not a hosted web application. The backend binds to `127.0.0.1` and the Gemini API key stays on the user's machine.

## Phase 1 features

- Electron desktop shell with a custom Windows title bar
- Responsive command-center interface built with React, TypeScript, Vite, and Tailwind CSS
- Animated audio orb, rings, waveform, and state colors
- Pipeline states: offline, connecting, listening, processing, speaking, and error
- Real-time 16 kHz PCM microphone capture
- Native Gemini PCM audio playback at the response sample rate
- Input and output live transcription
- Transient captions plus persistent conversation feed
- Secondary text input during an active live session
- In-app Gemini API key, model, voice, and system-instruction fields
- API key is held only in renderer memory and forwarded to the local backend for the current session; it is not persisted
- Modular local WebSocket protocol ready for future tools and automation

## Technology

| Layer | Technology |
| --- | --- |
| Desktop | Electron 43 |
| Interface | React 18, TypeScript, Vite 6, Tailwind CSS 3 |
| Backend | Python 3.11, FastAPI, Uvicorn |
| AI | `google-genai` 1.75, Gemini Live API |
| Transport | Local WebSocket at `ws://127.0.0.1:8765/ws/live` |
| Audio input | Mono PCM16, 16 kHz, little-endian |

Python **3.11** is the supported runtime. Dependency versions are pinned in `backend/requirements.txt` for repeatable Windows installation. Python 3.14 is not used because its ecosystem compatibility is still narrower for the future Windows automation and audio stack.

## Architecture

```text
Microphone / text
       │
       ▼
Electron renderer (React)
  ├─ audio resampling + level meter
  ├─ session UI and transcript state
  └─ PCM playback scheduler
       │ local WebSocket
       ▼
Python FastAPI bridge
  ├─ session validation
  ├─ Gemini Live lifecycle
  ├─ bounded real-time audio queue
  └─ event translation
       │ secure Gemini WebSocket
       ▼
Gemini 3.1 Flash Live Preview
```

The renderer never contacts Gemini directly. This isolates credentials and creates a clean boundary where tool execution, authorization, persistence, and Windows automation can be added later.

## Project structure

```text
Arix-AI/
├── frontend/
│   ├── electron/
│   │   ├── main.cjs              # Secure Electron main process
│   │   └── preload.cjs           # Minimal context bridge
│   └── src/
│       ├── components/            # Orb, navigation, transcript, settings
│       ├── hooks/                 # Live session and audio engines
│       ├── lib/audio.ts           # PCM conversion and decoding
│       ├── types/arix.ts          # Shared UI protocol types
│       ├── App.tsx
│       └── styles.css
├── backend/
│   ├── app/
│   │   ├── api/live.py            # Local WebSocket endpoint
│   │   ├── core/                  # Settings and message validation
│   │   ├── services/gemini_live.py
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── pyproject.toml
├── scripts/                       # Windows setup and launch helpers
└── package.json                   # Unified development commands
```

## Windows setup

### Prerequisites

1. Windows 10 or 11
2. [Python 3.11 (64-bit)](https://www.python.org/downloads/) with the Python launcher enabled
3. [Node.js 20 LTS or newer](https://nodejs.org/)
4. A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### Install

Clone the repository, open PowerShell in the repository, and run:

```powershell
.\scripts\setup-windows.ps1
```

Or use Command Prompt:

```bat
scripts\setup-windows.bat
```

### Start

```powershell
.\scripts\start-windows.ps1
```

The command starts the local Python bridge, Vite, and Electron together. Keep the terminal open while using this development build.

## User guide

1. Launch Arix.
2. Select **Configure** or the Settings icon.
3. Paste your Gemini API key into the in-app field.
4. Keep the default `gemini-3.1-flash-live-preview` model unless Google changes the preview model available to your account.
5. Choose a voice and optionally edit the system instruction.
6. Select **Start live session** and allow microphone access.
7. Speak naturally. The orb and waveform respond to microphone activity, and Arix's audio is played as it arrives.
8. Use the right-side composer to send text within the same live session.
9. Select **End live session** when finished.

The key is deliberately not stored. Enter it again after restarting the application. A future release can use Windows Credential Manager for opt-in encrypted persistence.

## Local endpoints and protocol

- `GET http://127.0.0.1:8765/health` — backend health information
- `WS ws://127.0.0.1:8765/ws/live` — live bidirectional session

First WebSocket message:

```json
{
  "type": "session.start",
  "apiKey": "...",
  "model": "gemini-3.1-flash-live-preview",
  "voice": "Kore",
  "systemInstruction": "You are Arix..."
}
```

Subsequent binary frames are raw PCM16 microphone chunks. Text frames use `{ "type": "text", "text": "..." }`. Server events include `session.ready`, `status`, `transcript`, `audio`, `turn.complete`, `interrupted`, and `error`.

## Development commands

```bash
npm run dev        # Backend + Vite + Electron
npm run build      # TypeScript and production renderer build
npm run typecheck  # TypeScript validation
npm run test       # Python tests and frontend lint
```

Backend only:

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 --reload
```

## Security notes

- The backend listens only on the loopback interface by default.
- WebSocket browser origins are restricted to local development origins and Electron's local file origin.
- The API key is excluded from logs and is never written by the app.
- Electron uses context isolation, sandboxing, and no Node.js integration in the renderer.
- No API key should be committed to Git. `.env` files are ignored.

## Testing status

- Frontend production build: passing
- TypeScript type-check: passing
- ESLint: passing
- Python unit/API tests: passing
- Gemini config construction against `google-genai`: passing
- Live Gemini conversation requires a valid user key and model access and should be verified on Windows with microphone permission

## Not implemented yet

The following are deliberately outside Phase 1:

- Screen sharing or vision frames
- Tool/function calling
- File and directory management
- Website or document generation
- Microsoft UI Automation and desktop control
- Conversation persistence and long-term memory
- Production installer containing an embedded Python runtime
- Secure persisted key storage

## Recommended next steps

1. Add Windows Credential Manager integration for optional key persistence.
2. Bundle a managed Python 3.11 runtime and backend process into the Electron installer.
3. Add a typed tool registry and confirmation policy before implementing UI Automation.
4. Add SQLite conversation history and session resumption.
5. Add screen capture only after explicit per-session consent controls.
6. Create a signed Windows installer through a Windows GitHub Actions runner.

## Deployment status

- Platform: Local Windows desktop
- Hosted deployment: Not applicable
- Repository: `https://github.com/itsarixworks-cell/Arix-AI`
- Phase: 1 — voice UI and Gemini Live bridge
