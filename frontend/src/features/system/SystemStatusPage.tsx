// Route: "/" — system status screen.
//
// Phase 0's proof that the stack is wired end to end: the browser reaches nginx,
// nginx proxies /api to FastAPI, FastAPI reaches Postgres and Redis, and Celery
// beat is stamping heartbeats through the broker. The dashboard proper (SPEC
// §9.2) replaces this at Phase 2.
//
// Endpoints: GET /api/v1/health, GET /api/v1/ready (via ./api.ts)

import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { StatusDot } from '@/components/ui/StatusDot'
import { DependencyList } from '@/features/system/DependencyList'
import { HeartbeatPanel } from '@/features/system/HeartbeatPanel'
import { useHealth, useReady } from '@/features/system/api'
import { formatDateTime } from '@/lib/utils'

export function SystemStatusPage() {
  const health = useHealth()
  const ready = useReady()

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-text">System status</h1>
          <p className="text-text-muted">
            Phase 0 foundation. Collection, rules and delivery arrive in later phases.
          </p>
        </div>
        {health.data !== undefined && (
          <span className="machine text-text-dim">
            v{health.data.version} · {health.data.environment}
          </span>
        )}
      </header>

      <Card
        title="Dependencies"
        meta={ready.data === undefined ? undefined : ready.data.status}
        action={
          ready.data !== undefined && (
            <span className="flex items-center gap-2 text-sm text-text-muted">
              <StatusDot status={ready.data.status === 'ready' ? 'ok' : 'error'} />
              {ready.data.status === 'ready' ? 'All reachable' : 'Degraded'}
            </span>
          )
        }
      >
        {/* `isPending` is true only before the first response. Rendering the
            skeleton on it — rather than on `isFetching` — stops the panel
            flickering every time the 10s poll refreshes. */}
        {ready.isPending ? (
          <div className="flex flex-col gap-2.5">
            <Skeleton className="h-5 w-full" />
            <Skeleton className="h-5 w-4/5" />
          </div>
        ) : ready.isError ? (
          <p className="text-sev-critical">Could not reach the API.</p>
        ) : (
          <DependencyList
            checks={ready.data.checks}
            databaseVersion={ready.data.database_version ?? null}
          />
        )}
      </Card>

      <Card title="Scheduler heartbeat" meta="every 30s">
        {ready.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : ready.isError ? (
          <p className="text-sev-critical">Could not reach the API.</p>
        ) : (
          <HeartbeatPanel heartbeat={ready.data.heartbeat ?? null} />
        )}
      </Card>

      <Card title="API">
        {health.isPending ? (
          <Skeleton className="h-10 w-full" />
        ) : health.isError ? (
          <p className="text-sev-critical">Could not reach the API.</p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-4">
            <div>
              <dt className="text-sm text-text-dim">Application</dt>
              <dd className="text-text">{health.data.app}</dd>
            </div>
            <div>
              <dt className="text-sm text-text-dim">Version</dt>
              <dd className="machine">{health.data.version}</dd>
            </div>
            <div>
              <dt className="text-sm text-text-dim">Environment</dt>
              <dd className="machine">{health.data.environment}</dd>
            </div>
            <div>
              <dt className="text-sm text-text-dim">Server time</dt>
              <dd className="machine">{formatDateTime(health.data.time)}</dd>
            </div>
          </dl>
        )}
      </Card>
    </div>
  )
}
