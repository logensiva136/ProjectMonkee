// The panel visibility grid on /admin/roles — which screens each role sees.
// Data: GET /api/v1/panels and /api/v1/roles; saves via useUpdateRole.
//
// THIS IS NOT A SECURITY CONTROL. Ticking a box here adds a sidebar link;
// it grants no access. The endpoints behind every screen check permissions
// independently (SPEC §6.3), so a role with a panel but no permission sees the
// link and gets 403.

import { PanelIcon } from '@/components/layout/PanelIcon'
import type { PanelOut, RoleDetail } from '@/features/admin/api'

interface Props {
  roles: RoleDetail[]
  panels: PanelOut[]
  /** Called with the role's complete new panel list. */
  onToggle: (role: RoleDetail, panelKeys: string[]) => void
  disabled?: boolean
}

export function PanelMatrix({ roles, panels, onToggle, disabled = false }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-medium text-text-dim">
              Screen
            </th>
            {roles.map((role) => (
              <th key={role.id} className="px-2 py-2 text-center font-medium text-text-muted">
                <span className="block truncate">{role.name}</span>
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {panels.map((panel) => (
            <tr key={panel.key} className="border-b border-border hover:bg-surface-2">
              <td className="sticky left-0 z-10 bg-surface px-3 py-1.5">
                <span className="flex items-center gap-2 text-text">
                  <PanelIcon name={panel.icon} className="size-3.5 text-text-dim" />
                  {panel.name}
                </span>
                <span className="machine block text-xs text-text-dim">{panel.route}</span>
              </td>

              {roles.map((role) => {
                const visible = role.panel_keys.includes(panel.key)
                return (
                  <td key={role.id} className="px-2 py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={visible}
                      disabled={disabled}
                      aria-label={`${panel.name} visible to ${role.name}`}
                      onChange={() =>
                        onToggle(
                          role,
                          visible
                            ? role.panel_keys.filter((key) => key !== panel.key)
                            : [...role.panel_keys, panel.key],
                        )
                      }
                      className="size-4 accent-[rgb(var(--accent))]"
                    />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
