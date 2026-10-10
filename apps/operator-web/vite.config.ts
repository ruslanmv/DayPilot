import { defineConfig, type Connect, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Dev requests to /api/* are proxied to the FastAPI gateway so the browser
// never receives the Vite HTML page for an API call (the classic
// "Unexpected token '<'" failure). Override the target when the API runs on a
// non-default port: DAYPILOT_API_TARGET=http://localhost:9000 make serve
const apiTarget = process.env.DAYPILOT_API_TARGET || process.env.VITE_DAYPILOT_API_TARGET || 'http://localhost:8080'

// The Echo Show display mode is a second page (echo/index.html), built by its own pass
// (vite.echo.config.ts) so this build's output is unchanged. `/echo` without the trailing
// slash would otherwise fall through to the console's SPA fallback in dev and `vite preview`;
// in production the gateway serves it (services/api-gateway/app/webserve.py).
const echoSlash: Connect.NextHandleFunction = (req, res, next) => {
  const [path, query] = (req.url || '').split('?')
  if (path === '/echo') {
    res.statusCode = 308
    res.setHeader('Location', '/echo/' + (query ? `?${query}` : ''))
    res.end()
    return
  }
  next()
}
const echoPage: Plugin = {
  name: 'daypilot-echo-page',
  configureServer: (server) => { server.middlewares.use(echoSlash) },
  configurePreviewServer: (server) => { server.middlewares.use(echoSlash) },
}

export default defineConfig({
  plugins: [react(), echoPage],
  build: {
    rollupOptions: {
      output: {
        // Keep React out of the main application chunk and cache it separately.
        manualChunks: { 'react-vendor': ['react', 'react-dom'] },
      },
    },
  },
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
