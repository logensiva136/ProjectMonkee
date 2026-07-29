// Monospace status strip pinned to the bottom of the viewport (SPEC §9.1):
//
//   ● api: healthy   db ok   redis ok   beat 12:04:11
//
// Source counts and queue depth join it in Phase 2, once there are sources and
// a collection queue to count.
//
// Endpoint: GET /api/v1/ready via useReady() in features/system/api.ts

import { StatusDot } from '@/components/ui/StatusDot'
import { useReady } from '@/features/system/api'
import type { Status } from '@/components/ui/StatusDot'

export function StatusStrip() {
  const ready = useReady()

  const overall: Status = ready.isPending
    ? 'unknown'
    : ready.isError || ready.data?.status !== 'ready'
      ? 'error'
      : 'ok'

  const checks = ready.data?.checks ?? []
  const heartbeat = ready.data?.heartbeat ?? null

  return (
    <footer className="sticky bottom-0 z-20 border-t border-border bg-bg-subtle">
      <div className="flex h-8 items-center gap-4 overflow-x-auto px-4 font-mono text-xs text-text-muted">
        <span className="flex shrink-0 items-center gap-1.5">
          <StatusDot status={overall} />
          api: {ready.isPending ? 'checking' : (ready.data?.status ?? 'unreachable')}
        </span>

        {checks.map((check) => (
          <span key={check.name} className="shrink-0">
            {check.name} {check.ok ? 'ok' : 'down'}
          </span>
        ))}

        {heartbeat !== null && (
          <span className="shrink-0">
            beat {heartbeat.stale ? 'stale' : `${Math.round(heartbeat.age_seconds)}s`} · tick{' '}
            {heartbeat.count}
          </span>
        )}
      </div>
    </footer>
  )
}
