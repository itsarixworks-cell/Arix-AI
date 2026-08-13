module.exports = {
  apps: [
    {
      name: 'arix-backend',
      script: 'python3',
      args: '-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765',
      cwd: __dirname,
      autorestart: true,
      watch: false,
    },
    {
      name: 'arix-ui-preview',
      script: 'npm',
      args: '--prefix frontend run dev',
      cwd: __dirname,
      autorestart: true,
      watch: false,
    },
  ],
}
