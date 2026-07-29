// Celery scheduler heartbeat panel.
//
// This is the visible proof that beat -> broker -> worker is a closed loop. If
// `age` climbs past ~90s the scheduler has stalled, which means collection has
// silently stopped — the failure a monitoring platform can least afford.
//
// Data comes from GET /api/v1/ready via useReady() in ./api.ts.

import { StatusDot } from '@/components/ui/StatusDot'
import type { HeartbeatInfo } from '@/features/system/api'
import { formatAge, formatDateTime } from '@/lib/utils'

interface Props {
  heartbeat: HeartbeatInfo | null
}

export function HeartbeatPanel({ heartbeat }: Props) {
  if (heartbeat === null) {
    return (
      <div className="flex items-center gap-3 text-text-muted">
        <StatusDot status="unknown" />
        <span>No heartbeat recorded yet — the worker or beat process may not be running.</span>
      </div>
    )
  }

  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-4">
      <Field label="State">
        <span className="flex items-center gap-2">
          <StatusDot status={heartbeat.stale ? 'warn' : 'ok'} />
          <span className={heartbeat.stale ? 'text-sev-medium' : 'text-ok'}>
            {heartbeat.stale ? 'Stale' : 'Live'}
          </span>
        </span>
      </Field>

      <Field label="Last run">
        <span className="machine">{formatAge(heartbeat.age_seconds)}</span>
      </Field>

      <Field label="Ticks">
        <span className="machine">{heartbeat.count.toLocaleString()}</span>
      </Field>

      <Field label="Worker">
        <span className="machine truncate" title={heartbeat.worker}>
          {heartbeat.worker}
        </span>
      </Field>

      <div className="col-span-2 sm:col-span-4">
        <dt className="text-sm text-text-dim">Timestamp</dt>
        <dd className="machine text-text-muted">{formatDateTime(heartbeat.at)}</dd>
      </div>
    </dl>
  )
}

// Used three times in this file only, so it stays here rather than becoming a
// shared component (SPEC §9.0 Rule 3: extract on the third repetition elsewhere).
interface FieldProps {
  label: string
  children: React.ReactNode
}

function Field({ label, children }: FieldProps) {
  return (
    <div>
      <dt className="text-sm text-text-dim">{label}</dt>
      <dd className="text-text">{children}</dd>
    </div>
  )
}
