import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy keeps the browser on one origin in dev, so CORS never bites.
    // 127.0.0.1 rather than localhost: Node resolves localhost to ::1 first,
    // and uvicorn binds IPv4 only, which shows up as ECONNREFUSED ::1:8000.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
