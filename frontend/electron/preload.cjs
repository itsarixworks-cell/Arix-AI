const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('arixDesktop', {
  getVersion: () => ipcRenderer.invoke('app:version'),
  openExternal: (url) => ipcRenderer.invoke('app:open-external', url),
  platform: process.platform,
})
