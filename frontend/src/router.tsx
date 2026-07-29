// Route table. Adding a screen means adding a route here, creating
// features/<domain>/, and seeding a `panel` row in the backend (SPEC §6.3).
//
// Everything under <RequireAuth> needs a signed-in user. That guard is
// navigation convenience — the API enforces permissions on every endpoint
// independently, so a user who types an admin URL directly still gets 403 from
// the server.

import { createBrowserRouter } from 'react-router-dom'

import { RequireAuth } from '@/components/auth/RequireAuth'
import { AppLayout } from '@/components/layout/AppLayout'
import { AccountPage } from '@/features/account/AccountPage'
import { AuditPage } from '@/features/admin/AuditPage'
import { RolesPage } from '@/features/admin/RolesPage'
import { SettingsPage } from '@/features/admin/SettingsPage'
import { UsersPage } from '@/features/admin/UsersPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { MfaPage } from '@/features/auth/MfaPage'
import { SetupWizard } from '@/features/setup/SetupWizard'
import { NotFoundPage } from '@/features/system/NotFoundPage'
import { SystemStatusPage } from '@/features/system/SystemStatusPage'

export const router = createBrowserRouter([
  // --- unauthenticated ---
  { path: '/setup', element: <SetupWizard /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/login/mfa', element: <MfaPage /> },

  // --- everything else ---
  {
    path: '/',
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <SystemStatusPage /> },
          { path: 'account', element: <AccountPage /> },
          { path: 'admin/users', element: <UsersPage /> },
          { path: 'admin/roles', element: <RolesPage /> },
          { path: 'admin/settings', element: <SettingsPage /> },
          { path: 'admin/audit', element: <AuditPage /> },
          // Nginx serves index.html for unknown paths so the SPA can route
          // them, which means an unknown URL lands here rather than 404ing at
          // the web server.
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
])
