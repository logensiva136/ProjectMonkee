// The `?` cheatsheet (SPEC §9.1). Calls no API.

import { useEffect } from 'react'

const SHORTCUTS: { keys: string[]; description: string }[] = [
  { keys: ['Ctrl', 'K'], description: 'Open the command palette' },
  { keys: ['g', 'd'], description: 'Go to the dashboard' },
  { keys: ['g', 'u'], description: 'Go to users' },
  { keys: ['g', 'a'], description: 'Go to alerts (Phase 3)' },
  { keys: ['g', 'v'], description: 'Go to vendors (Phase 5)' },
  { keys: ['g', 's'], description: 'Go to sources (Phase 2)' },
  { keys: ['/'], description: 'Focus the search box' },
  { keys: ['j'], description: 'Next row (Phase 3)' },
  { keys: ['k'], description: 'Previous row (Phase 3)' },
  { keys: ['e'], description: 'Acknowledge the selected alert (Phase 3)' },
  { keys: ['?'], description: 'Show this cheatsheet' },
  { keys: ['Esc'], description: 'Close a dialog' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export function ShortcutsHelp({ open, onClose }: Props) {
  // Escape closes it. Registered only while open, and torn down on close.
  useEffect(() => {
    if (!open) return
    function handle(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handle)
    return () => document.removeEventListener('keydown', handle)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md rounded-md border border-border bg-surface"
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <h2 className="text-base font-medium text-text">Keyboard shortcuts</h2>
          <button type="button" onClick={onClose} className="text-sm text-text-dim hover:text-text">
            Esc
          </button>
        </header>

        <dl className="max-h-[60vh] divide-y divide-border overflow-y-auto">
          {SHORTCUTS.map((shortcut) => (
            <div
              key={shortcut.description}
              className="flex items-center justify-between gap-4 px-4 py-2"
            >
              <dt className="text-base text-text-muted">{shortcut.description}</dt>
              <dd className="flex shrink-0 gap-1">
                {shortcut.keys.map((key) => (
                  <kbd
                    key={key}
                    className="machine rounded border border-border bg-bg-subtle px-1.5 py-0.5 text-xs text-text"
                  >
                    {key}
                  </kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
