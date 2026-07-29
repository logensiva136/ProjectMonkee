// Route: "/admin/roles" — roles, the permission matrix and the panel matrix.
// Endpoints: /api/v1/roles, /api/v1/permissions, /api/v1/panels

import { toast } from 'sonner'

import { Alert } from '@/components/ui/Alert'
import { Card } from '@/components/ui/Card'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { PanelMatrix } from '@/features/admin/PanelMatrix'
import { PermissionMatrix } from '@/features/admin/PermissionMatrix'
import { useAllPanels, usePermissions, useRoles, useUpdateRole } from '@/features/admin/api'
import type { RoleDetail } from '@/features/admin/api'
import { ApiError } from '@/lib/api'

export function RolesPage() {
  const roles = useRoles()
  const permissions = usePermissions()
  const panels = useAllPanels()
  const update = useUpdateRole()

  function savePermissions(role: RoleDetail, permissionKeys: string[]) {
    update.mutate(
      { id: role.id, body: { permission_keys: permissionKeys } },
      {
        onSuccess: () => toast.success(`${role.name} permissions updated.`),
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.message : 'Could not save.'),
      },
    )
  }

  function savePanels(role: RoleDetail, panelKeys: string[]) {
    update.mutate(
      { id: role.id, body: { panel_keys: panelKeys } },
      {
        onSuccess: () => toast.success(`${role.name} navigation updated.`),
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.message : 'Could not save.'),
      },
    )
  }

  const loading = roles.isPending || permissions.isPending || panels.isPending

  if (roles.isError) {
    return (
      <div className="p-4 sm:p-6">
        <Alert tone="error" title="Could not load roles">
          {roles.error instanceof ApiError ? roles.error.message : 'Unexpected error.'}
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <PageHeader title="Roles" description="What each role may do, and which screens it sees." />

      <Alert tone="info" title="Permissions are enforced by the API">
        Ticking a screen below only adds a sidebar link. Access is decided by the permission matrix,
        which the backend checks on every request — a role with a screen but no permission sees the
        link and is refused.
      </Alert>

      <Card
        title="Permissions"
        meta={roles.data === undefined ? undefined : `${roles.data.length} roles`}
        className="overflow-hidden"
      >
        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <PermissionMatrix
            roles={roles.data}
            permissions={permissions.data ?? []}
            onToggle={savePermissions}
            disabled={update.isPending}
          />
        )}
      </Card>

      <Card title="Screen visibility" meta="navigation only" className="overflow-hidden">
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <PanelMatrix
            roles={roles.data}
            panels={panels.data ?? []}
            onToggle={savePanels}
            disabled={update.isPending}
          />
        )}
      </Card>
    </div>
  )
}
