/**
 * STEP 5 — React Entry Point
 *
 * This is the first JavaScript file that runs.
 * It finds the <div id="root"> in index.html and mounts the React app inside it.
 * StrictMode is a development helper that warns you about potential issues.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
