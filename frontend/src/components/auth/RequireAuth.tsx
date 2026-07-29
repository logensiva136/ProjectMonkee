// Route guard. Wraps every screen that needs a signed-in user.
//
// This is convenience and navigation only. The backend enforces permissions on
// every endpoint independently (SPEC §6.3) — removing this component would make
// the UI ugly, not insecure.

import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { Skeleton } from '@/components/ui/Skeleton'
import { useSession } from '@/hooks/useSession'

export function RequireAuth() {
  const session = useSession()
  const location = useLocation()

  // Wait for the silent refresh to settle. Redirecting before it does would
  // bounce every signed-in user to /login on each page reload.
  if (!session.isReady) {
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (session.needsSetup) {
    return <Navigate to="/setup" replace />
  }

  if (!session.isAuthenticated) {
    // `state.from` lets the login screen return the user where they were going.
    // `replace` keeps the guarded URL out of history, so Back does not bounce.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
