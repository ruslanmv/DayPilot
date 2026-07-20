import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev requests to /api/* are proxied to the FastAPI gateway so the browser
// never receives the Vite HTML page for an API call (the classic
// "Unexpected token '<'" failure). Override the target when the API runs on a
// non-default port: DAYPILOT_API_TARGET=http://localhost:9000 make serve
const apiTarget = process.env.DAYPILOT_API_TARGET || process.env.VITE_DAYPILOT_API_TARGET || 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
