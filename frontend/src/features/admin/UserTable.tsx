// The user list on /admin/users.
// Data: GET /api/v1/users; actions call the mutations in ./api.ts.
//
// Column priority for the SPEC §9.1 responsive rules: username and status are
// always shown; roles appear from `sm`, last sign-in from `lg`.

import { KeyRound, Lock, ShieldOff, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { StatusDot } from '@/components/ui/StatusDot'
import type { UserSummary } from '@/features/admin/api'
import { formatDateTime } from '@/lib/utils'

interface Props {
  users: UserSummary[]
  currentUserId: string
  onUnlock: (id: string) => void
  onResetTwoFactor: (user: UserSummary) => void
  onResetPassword: (user: UserSummary) => void
  onDelete: (user: UserSummary) => void
}

export function UserTable({
  users,
  currentUserId,
  onUnlock,
  onResetTwoFactor,
  onResetPassword,
  onDelete,
}: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text-dim">
            <th className="px-3 py-2 font-medium">User</th>
            <th className="hidden px-3 py-2 font-medium sm:table-cell">Roles</th>
            <th className="px-3 py-2 font-medium">Status</th>
            <th className="hidden px-3 py-2 font-medium lg:table-cell">Last sign-in</th>
            <th className="px-3 py-2 text-right font-medium">Actions</th>
          </tr>
        </thead>

        <tbody className="divide-y divide-border">
          {users.map((user) => (
            <tr key={user.id} className="hover:bg-surface-2">
              <td className="px-3 py-2">
                <div className="flex items-center gap-2.5">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-[10px] font-semibold text-text-muted">
                    {user.initials}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-text">
                      {user.full_name}
                      {user.id === currentUserId && (
                        <span className="ml-1.5 text-xs text-text-dim">(you)</span>
                      )}
                    </p>
                    <p className="machine truncate text-xs text-text-dim">{user.username}</p>
                  </div>
                </div>
              </td>

              <td className="hidden px-3 py-2 sm:table-cell">
                <div className="flex flex-wrap gap-1">
                  {user.role_keys.length === 0 ? (
                    <span className="text-text-dim">— none —</span>
                  ) : (
                    user.role_keys.map((key) => (
                      <span
                        key={key}
                        className="machine rounded border border-border px-1.5 py-0.5 text-xs text-text-muted"
                      >
                        {key}
                      </span>
                    ))
                  )}
                </div>
              </td>

              <td className="px-3 py-2">
                <span className="flex items-center gap-2">
                  <StatusDot status={user.is_locked ? 'error' : user.is_active ? 'ok' : 'warn'} />
                  <span className="text-text-muted">
                    {user.is_locked ? 'Locked' : user.is_active ? 'Active' : 'Disabled'}
                  </span>
                  {!user.totp_enabled && (
                    <span className="text-xs text-sev-medium" title="No second factor enrolled">
                      no 2FA
                    </span>
                  )}
                </span>
              </td>

              <td className="hidden px-3 py-2 lg:table-cell">
                <span className="machine text-text-muted">
                  {user.last_login_at === null ? 'never' : formatDateTime(user.last_login_at)}
                </span>
              </td>

              <td className="px-3 py-2">
                <div className="flex justify-end gap-1">
                  {user.is_locked && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onUnlock(user.id)}
                      title="Unlock account"
                    >
                      <Lock className="size-3.5" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onResetPassword(user)}
                    title="Set a new password"
                  >
                    <KeyRound className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onResetTwoFactor(user)}
                    disabled={!user.totp_enabled}
                    title="Clear two-factor enrolment"
                  >
                    <ShieldOff className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(user)}
                    // The API refuses this too; disabling it here just avoids a
                    // pointless round trip to be told so.
                    disabled={user.id === currentUserId}
                    title="Remove user"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
