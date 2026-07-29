// One audit entry, expandable to show the before/after diff.
// Data comes from GET /api/v1/audit-logs via the parent.

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import type { AuditLogOut } from '@/features/admin/api'
import { cn, formatDateTime } from '@/lib/utils'

interface Props {
  entry: AuditLogOut
}

/** Colour the verb: destructive actions should be findable by eye. */
function toneFor(action: string): string {
  if (action.includes('deleted') || action.includes('revoked') || action.includes('locked')) {
    return 'text-sev-critical'
  }
  if (action.includes('reset') || action.includes('reuse')) return 'text-sev-medium'
  if (action.includes('created') || action.includes('completed')) return 'text-ok'
  return 'text-text'
}

export function AuditRow({ entry }: Props) {
  const [expanded, setExpanded] = useState(false)
  const hasDiff = entry.before !== null || entry.after !== null

  return (
    <li>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        disabled={!hasDiff}
        aria-expanded={expanded}
        className="flex w-full items-center gap-3 px-1 py-2 text-left hover:bg-surface-2 disabled:cursor-default"
      >
        <span className="w-4 shrink-0 text-text-dim">
          {hasDiff ? (
            expanded ? (
              <ChevronDown className="size-3.5" />
            ) : (
              <ChevronRight className="size-3.5" />
            )
          ) : null}
        </span>

        <span className={cn('machine w-56 shrink-0 truncate text-sm', toneFor(entry.action))}>
          {entry.action}
        </span>

        <span className="w-28 shrink-0 truncate text-sm text-text-muted">
          {entry.actor_username ?? '—'}
        </span>

        <span className="machine hidden min-w-0 flex-1 truncate text-xs text-text-dim md:block">
          {entry.entity_type !== null && `${entry.entity_type} ${entry.entity_id ?? ''}`}
        </span>

        <span className="machine shrink-0 text-xs text-text-dim">
          {formatDateTime(entry.created_at)}
        </span>
      </button>

      {expanded && hasDiff && (
        <div className="grid gap-3 border-t border-border bg-bg-subtle px-8 py-3 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs uppercase tracking-wider text-text-dim">Before</p>
            <pre className="machine overflow-x-auto rounded border border-border bg-surface p-2 text-xs text-text-muted">
              {entry.before === null ? '—' : JSON.stringify(entry.before, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-1 text-xs uppercase tracking-wider text-text-dim">After</p>
            <pre className="machine overflow-x-auto rounded border border-border bg-surface p-2 text-xs text-text-muted">
              {entry.after === null ? '—' : JSON.stringify(entry.after, null, 2)}
            </pre>
          </div>

          {entry.request_id !== null && (
            <p className="machine text-xs text-text-dim md:col-span-2">
              request {entry.request_id}
              {entry.ip !== null && ` · ${entry.ip}`}
            </p>
          )}
        </div>
      )}
    </li>
  )
}
