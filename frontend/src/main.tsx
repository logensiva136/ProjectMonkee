// Browser entry point — the first file that runs. Mounts <App /> into the
// #root div in index.html.

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/App'
import '@/styles/index.css'

const container = document.getElementById('root')
if (container === null) {
  throw new Error('index.html is missing its #root element')
}

createRoot(container).render(
  // StrictMode double-invokes effects and renders in development only, to
  // surface side effects that are not idempotent. It does nothing in a
  // production build — if something breaks only in dev, suspect this.
  <StrictMode>
    <App />
  </StrictMode>,
)
