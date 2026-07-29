// Command palette on Ctrl/Cmd+K (SPEC §9.1).
//
// Phase 1 offers navigation and theme switching. "Poll source", "start scan"
// and entity jump land in later phases, as the entities they act on arrive.
//
// Data: the panels from GET /api/v1/me, so the palette can only offer screens
// the user actually has.

import { useEffect, useState } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'

import { PanelIcon } from '@/components/layout/PanelIcon'
import type { PanelOut } from '@/features/auth/api'
import { useThemeStore } from '@/stores/theme'

interface Props {
  panels: PanelOut[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ panels, open, onOpenChange }: Props) {
  const navigate = useNavigate()
  const toggleTheme = useThemeStore((state) => state.toggleTheme)
  const [search, setSearch] = useState('')

  // Clear the query whenever the palette closes, so reopening starts fresh
  // rather than showing the last search's results.
  useEffect(() => {
    if (!open) setSearch('')
  }, [open])

  function run(action: () => void) {
    onOpenChange(false)
    action()
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-[12vh]"
      onClick={() => onOpenChange(false)}
    >
      <Command
        label="Command palette"
        // Stop a click inside the dialog reaching the backdrop handler above.
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-md border border-border bg-surface shadow-2xl"
      >
        <Command.Input
          value={search}
          onValueChange={setSearch}
          autoFocus
          placeholder="Jump to a screen, or run a command…"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-base text-text outline-none placeholder:text-text-dim"
        />

        <Command.List className="max-h-80 overflow-y-auto p-1.5">
          <Command.Empty className="px-3 py-6 text-center text-sm text-text-dim">
            Nothing matches that.
          </Command.Empty>

          <Command.Group
            heading="Go to"
            className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-text-dim"
          >
            {panels.map((panel) => (
              <Command.Item
                key={panel.key}
                value={`${panel.name} ${panel.nav_group} ${panel.route}`}
                onSelect={() => run(() => navigate(panel.route))}
                className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-2 text-base text-text-muted data-[selected=true]:bg-surface-2 data-[selected=true]:text-text"
              >
                <PanelIcon name={panel.icon} className="size-4" />
                {panel.name}
                <span className="machine ml-auto text-xs text-text-dim">{panel.route}</span>
              </Command.Item>
            ))}
          </Command.Group>

          <Command.Group
            heading="Actions"
            className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-text-dim"
          >
            <Command.Item
              value="toggle theme dark light appearance"
              onSelect={() => run(toggleTheme)}
              className="cursor-pointer rounded px-2 py-2 text-base text-text-muted data-[selected=true]:bg-surface-2 data-[selected=true]:text-text"
            >
              Toggle dark / light theme
            </Command.Item>
          </Command.Group>
        </Command.List>
      </Command>
    </div>
  )
}
