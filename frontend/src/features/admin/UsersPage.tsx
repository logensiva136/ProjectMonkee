// Route: "/admin/users" — user administration (SPEC §9.2).
// Endpoints: /api/v1/users (list, create, unlock, 2FA reset, delete), /api/v1/roles

import { useState } from 'react'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { CreateUserForm } from '@/features/admin/CreateUserForm'
import { ResetPasswordDialog } from '@/features/admin/ResetPasswordDialog'
import { UserTable } from '@/features/admin/UserTable'
import {
  useDeleteUser,
  useResetTwoFactor,
  useRoles,
  useUnlockUser,
  useUsers,
} from '@/features/admin/api'
import type { UserSummary } from '@/features/admin/api'
import { useSession } from '@/hooks/useSession'
import { ApiError } from '@/lib/api'

export function UsersPage() {
  const session = useSession()
  const users = useUsers()
  const roles = useRoles()
  const unlock = useUnlockUser()
  const resetTwoFactor = useResetTwoFactor()
  const remove = useDeleteUser()

  const [creating, setCreating] = useState(false)
  const [resetting, setResetting] = useState<UserSummary | null>(null)

  function report(error: unknown) {
    toast.error(error instanceof ApiError ? error.message : 'Something went wrong.')
  }

  function handleResetTwoFactor(user: UserSummary) {
    if (
      !window.confirm(
        `Clear two-factor for ${user.username}? They will re-enrol at their next sign-in, ` +
          'and all their sessions will end.',
      )
    ) {
      return
    }
    resetTwoFactor.mutate(user.id, {
      onSuccess: () => toast.success(`Two-factor cleared for ${user.username}.`),
      onError: report,
    })
  }

  function handleDelete(user: UserSummary) {
    if (!window.confirm(`Remove ${user.username}? Their audit history is kept.`)) return
    remove.mutate(user.id, {
      onSuccess: () => toast.success(`${user.username} removed.`),
      onError: report,
    })
  }

  if (users.isError) {
    return (
      <div className="p-4 sm:p-6">
        <Alert tone="error" title="Could not load users">
          {users.error instanceof ApiError ? users.error.message : 'Unexpected error.'}
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <PageHeader
        title="Users"
        description="Accounts, role assignment and account recovery."
        actions={
          <Button variant="primary" onClick={() => setCreating(!creating)}>
            <Plus className="size-4" />
            Add user
          </Button>
        }
      />

      {creating && (
        <Card title="New user">
          <CreateUserForm
            roles={roles.data ?? []}
            onCreated={() => {
              setCreating(false)
              toast.success('User created.')
            }}
            onCancel={() => setCreating(false)}
          />
        </Card>
      )}

      <Card
        title="Accounts"
        meta={users.data === undefined ? undefined : `${users.data.length}`}
        className="overflow-hidden"
      >
        {users.isPending ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-5/6" />
          </div>
        ) : users.data.length === 0 ? (
          <EmptyState
            title="No users yet"
            description="Add an account to give a colleague access to this console."
          />
        ) : (
          <UserTable
            users={users.data}
            currentUserId={session.me?.user.id ?? ''}
            onUnlock={(id) =>
              unlock.mutate(id, {
                onSuccess: () => toast.success('Account unlocked.'),
                onError: report,
              })
            }
            onResetTwoFactor={handleResetTwoFactor}
            onResetPassword={setResetting}
            onDelete={handleDelete}
          />
        )}
      </Card>

      {resetting !== null && (
        <ResetPasswordDialog
          user={resetting}
          onDone={() => {
            setResetting(null)
            toast.success('Password set. Their sessions were signed out.')
          }}
          onCancel={() => setResetting(null)}
        />
      )}
    </div>
  )
}
