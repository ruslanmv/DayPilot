import { fileURLToPath } from 'node:url'
import { defineConfig, mergeConfig } from 'vite'

import base from './vite.config'

// Second build pass for the Echo Show display mode (`/echo`). It writes dist/echo/index.html
// and its own assets next to the console's build without touching them, so the desktop
// bundle stays exactly as the main pass produced it.
export default mergeConfig(base, defineConfig({
  build: {
    emptyOutDir: false,
    rollupOptions: {
      input: { echo: fileURLToPath(new URL('./echo/index.html', import.meta.url)) },
    },
  },
}))
