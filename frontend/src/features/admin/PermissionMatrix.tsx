// The permission grid on /admin/roles — a checkbox per (role, permission).
// Data: GET /api/v1/permissions and /api/v1/roles; saves via useUpdateRole.
//
// This grid is the SECURITY boundary. The panel grid beside it is presentation
// only (SPEC §6.3), which is why they are deliberately two separate tables
// rather than one merged one.

import { Fragment } from 'react'

import type { PermissionOut, RoleDetail } from '@/features/admin/api'
import { cn } from '@/lib/utils'

interface Props {
  roles: RoleDetail[]
  permissions: PermissionOut[]
  /** Called with the role's complete new permission list. */
  onToggle: (role: RoleDetail, permissionKeys: string[]) => void
  disabled?: boolean
}

export function PermissionMatrix({ roles, permissions, onToggle, disabled = false }: Props) {
  // Group by resource so related capabilities sit together.
  const groups: { resource: string; permissions: PermissionOut[] }[] = []
  for (const permission of permissions) {
    const existing = groups.find((group) => group.resource === permission.resource)
    if (existing) existing.permissions.push(permission)
    else groups.push({ resource: permission.resource, permissions: [permission] })
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-medium text-text-dim">
              Permission
            </th>
            {roles.map((role) => (
              <th key={role.id} className="px-2 py-2 text-center font-medium text-text-muted">
                <span className="block truncate">{role.name}</span>
                {role.key === 'super_admin' && (
                  <span className="block text-xs font-normal text-text-dim">all, fixed</span>
                )}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {groups.map((group) => (
            <Fragment key={group.resource}>
              <tr className="border-b border-border bg-bg-subtle">
                <td
                  colSpan={roles.length + 1}
                  className="machine px-3 py-1 text-xs uppercase tracking-wider text-text-dim"
                >
                  {group.resource}
                </td>
              </tr>

              {group.permissions.map((permission) => (
                <tr key={permission.key} className="border-b border-border hover:bg-surface-2">
                  <td className="sticky left-0 z-10 bg-surface px-3 py-1.5">
                    <span className="machine text-text">{permission.key}</span>
                    <span className="block text-xs text-text-dim">{permission.description}</span>
                  </td>

                  {roles.map((role) => {
                    const held = role.permission_keys.includes(permission.key)
                    // Super Admin holds everything by definition; the API
                    // refuses to narrow it, so the box is shown ticked and
                    // locked rather than pretending to be editable.
                    const locked = disabled || role.key === 'super_admin'

                    return (
                      <td key={role.id} className="px-2 py-1.5 text-center">
                        <input
                          type="checkbox"
                          checked={held}
                          disabled={locked}
                          aria-label={`${permission.key} for ${role.name}`}
                          onChange={() =>
                            onToggle(
                              role,
                              held
                                ? role.permission_keys.filter((key) => key !== permission.key)
                                : [...role.permission_keys, permission.key],
                            )
                          }
                          className={cn(
                            'size-4 accent-[rgb(var(--accent))]',
                            locked && 'cursor-not-allowed opacity-50',
                          )}
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
