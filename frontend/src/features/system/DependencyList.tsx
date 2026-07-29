// Dependency rows on the system status screen: Postgres and Redis, with the
// latency of the probe that checked them.
// Data comes from GET /api/v1/ready via useReady() in ./api.ts.

import { StatusDot } from '@/components/ui/StatusDot'
import type { DependencyCheck } from '@/features/system/api'

interface Props {
  checks: DependencyCheck[]
  databaseVersion: string | null
}

export function DependencyList({ checks, databaseVersion }: Props) {
  return (
    <ul className="divide-y divide-border">
      {checks.map((check) => (
        // React needs a stable `key` on every list item to tell rows apart
        // across re-renders. The dependency name is unique, so it serves.
        <li key={check.name} className="flex items-center gap-3 py-2 first:pt-0 last:pb-0">
          <StatusDot status={check.ok ? 'ok' : 'error'} />

          <span className="w-24 text-text">{check.name}</span>

          <span className="machine text-text-muted">
            {/* The generated type makes this `number | null | undefined` — the
                field is optional in the schema, so both must be handled. */}
            {check.latency_ms == null ? '—' : `${check.latency_ms.toFixed(1)} ms`}
          </span>

          {check.name === 'database' && databaseVersion !== null && (
            <span className="machine text-text-dim">pg {databaseVersion}</span>
          )}

          {check.detail !== null && check.detail !== undefined && (
            <span className="truncate text-sm text-sev-critical" title={check.detail}>
              {check.detail}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}
