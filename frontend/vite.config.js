/**
 * STEP 3 — Vite Configuration
 *
 * Vite is the build tool. It does two things:
 *  1. In development: runs a fast local server with hot reload (changes appear instantly)
 *  2. In production: compiles all your React code into plain HTML/CSS/JS files
 *
 * The "proxy" below is important for development:
 *  When React makes a request to /api/..., Vite forwards it to Django at port 8000.
 *  This avoids CORS issues during development.
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
