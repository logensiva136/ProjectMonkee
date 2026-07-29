// Global keyboard shortcuts (SPEC §9.1).
//
//   Ctrl/Cmd+K   command palette
//   g then d     dashboard
//   g then a     alerts        (Phase 3)
//   g then v     vendors       (Phase 5)
//   /            focus search
//   ?            shortcut cheatsheet
//
// The `g d` form is a "chord": press g, then the next key within a second is
// read as the second half. That is why a timer is involved.

import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

const CHORD_TIMEOUT_MS = 1000

const CHORDS: Record<string, string> = {
  d: '/',
  a: '/alerts',
  v: '/vendors',
  s: '/feeds/sources',
  u: '/admin/users',
}

interface Options {
  onOpenPalette: () => void
  onShowHelp: () => void
}

/** True when the user is typing, so shortcuts must not hijack the keystroke. */
function isTypingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

export function useKeyboardShortcuts({ onOpenPalette, onShowHelp }: Options): void {
  const navigate = useNavigate()

  useEffect(() => {
    // Held between events to remember a pending `g`. A ref would work too, but
    // the listener closes over this directly and it never needs to re-render.
    let awaitingChord = false
    let chordTimer: number | undefined

    function handle(event: KeyboardEvent) {
      // Ctrl/Cmd+K works even inside an input — it is how you escape one.
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpenPalette()
        return
      }

      if (isTypingInto(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return
      }

      if (awaitingChord) {
        awaitingChord = false
        window.clearTimeout(chordTimer)
        const destination = CHORDS[event.key.toLowerCase()]
        if (destination !== undefined) {
          event.preventDefault()
          navigate(destination)
        }
        return
      }

      if (event.key === 'g') {
        awaitingChord = true
        // Forget the pending `g` after a second, so typing "g" then wandering
        // off does not silently swallow an unrelated later keypress.
        chordTimer = window.setTimeout(() => {
          awaitingChord = false
        }, CHORD_TIMEOUT_MS)
        return
      }

      if (event.key === '/') {
        const search = document.querySelector<HTMLInputElement>('[data-search-input]')
        if (search !== null) {
          event.preventDefault()
          search.focus()
        }
        return
      }

      if (event.key === '?') {
        event.preventDefault()
        onShowHelp()
      }
    }

    document.addEventListener('keydown', handle)
    return () => {
      document.removeEventListener('keydown', handle)
      window.clearTimeout(chordTimer)
    }
  }, [navigate, onOpenPalette, onShowHelp])
}
