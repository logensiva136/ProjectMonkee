// Left navigation, built entirely from the panels GET /api/v1/me returns.
//
// There is no hardcoded route list here on purpose: what a role can see is
// backend state (`role_panel`), so adding a screen means seeding a panel row,
// not editing this file. Panel visibility is presentation — the API enforces
// permissions independently (SPEC §6.3).

import { NavLink } from 'react-router-dom'

import { PanelIcon } from '@/components/layout/PanelIcon'
import type { PanelOut } from '@/features/auth/api'
import { cn } from '@/lib/utils'

interface Props {
  panels: PanelOut[]
  /** Icon-only at tablet widths (SPEC §9.1 responsive rules). */
  collapsed?: boolean
  onNavigate?: () => void
}

export function Sidebar({ panels, collapsed = false, onNavigate }: Props) {
  // Group by nav_group, preserving the sort_order the API already applied.
  const groups: { name: string; panels: PanelOut[] }[] = []
  for (const panel of panels) {
    const existing = groups.find((group) => group.name === panel.nav_group)
    if (existing) existing.panels.push(panel)
    else groups.push({ name: panel.nav_group, panels: [panel] })
  }

  return (
    <nav
      aria-label="Main"
      className={cn(
        'flex h-full flex-col gap-5 overflow-y-auto border-r border-border bg-bg-subtle py-3',
        collapsed ? 'w-14 px-2' : 'w-56 px-3',
      )}
    >
      {groups.map((group) => (
        <div key={group.name} className="flex flex-col gap-0.5">
          {!collapsed && (
            <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wider text-text-dim">
              {group.name}
            </p>
          )}

          {group.panels.map((panel) => (
            <NavLink
              key={panel.key}
              to={panel.route}
              // `end` stops the "/" dashboard link matching every other route.
              end={panel.route === '/'}
              onClick={onNavigate}
              title={collapsed ? panel.name : undefined}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-base transition-colors',
                  collapsed && 'justify-center',
                  isActive
                    ? 'bg-surface-2 text-accent'
                    : 'text-text-muted hover:bg-surface-2 hover:text-text',
                )
              }
            >
              <PanelIcon name={panel.icon} className="size-4 shrink-0" />
              {!collapsed && <span className="truncate">{panel.name}</span>}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}
