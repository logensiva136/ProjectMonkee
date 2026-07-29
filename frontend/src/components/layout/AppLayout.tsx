// Application chrome: top bar, sidebar, routed content, status strip.
// Data: GET /api/v1/me via useSession().
//
// Responsive behaviour (SPEC §9.1):
//   < 1024px  sidebar becomes a drawer, opened from the top bar
//   >= 1024px full sidebar alongside the content
//
// <Outlet /> is React Router's placeholder for whichever child route matched —
// the equivalent of a Jinja `{% block content %}`.

import { useCallback, useState } from 'react'
import { X } from 'lucide-react'
import { Outlet } from 'react-router-dom'

import { CommandPalette } from '@/components/layout/CommandPalette'
import { ShortcutsHelp } from '@/components/layout/ShortcutsHelp'
import { Sidebar } from '@/components/layout/Sidebar'
import { StatusStrip } from '@/components/layout/StatusStrip'
import { TopBar } from '@/components/layout/TopBar'
import { Button } from '@/components/ui/Button'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSession } from '@/hooks/useSession'

export function AppLayout() {
  const session = useSession()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // `useCallback` keeps these callbacks identical between renders. Without it
  // they would be new functions each time, and the shortcut hook's effect —
  // which lists them as dependencies — would tear down and reattach its
  // document listener on every render.
  const openPalette = useCallback(() => setPaletteOpen(true), [])
  const showHelp = useCallback(() => setHelpOpen(true), [])

  useKeyboardShortcuts({ onOpenPalette: openPalette, onShowHelp: showHelp })

  const panels = session.me?.panels ?? []

  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <TopBar
        me={session.me}
        onOpenPalette={openPalette}
        onOpenDrawer={() => setDrawerOpen(true)}
      />

      <div className="flex flex-1">
        <div className="hidden lg:block">
          <Sidebar panels={panels} />
        </div>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

      <StatusStrip />

      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setDrawerOpen(false)}
        >
          <div className="h-full w-64 bg-bg-subtle" onClick={(event) => event.stopPropagation()}>
            <div className="flex h-12 items-center justify-between border-b border-border px-3">
              <span className="font-mono text-sm tracking-[0.18em] text-text">HAYABUSA</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close navigation"
              >
                <X className="size-4" />
              </Button>
            </div>
            <Sidebar panels={panels} onNavigate={() => setDrawerOpen(false)} />
          </div>
        </div>
      )}

      <CommandPalette panels={panels} open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}
