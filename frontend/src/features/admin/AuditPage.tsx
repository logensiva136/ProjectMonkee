// Route: "/admin/audit" — the audit trail.
// Endpoint: GET /api/v1/audit-logs (via useAuditLogs)

import { useState } from 'react'

import { Alert } from '@/components/ui/Alert'
import { Card } from '@/components/ui/Card'
import { EmptyState } from '@/components/ui/EmptyState'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { AuditRow } from '@/features/admin/AuditRow'
import { useAuditLogs } from '@/features/admin/api'
import { ApiError } from '@/lib/api'

// Prefix filters. A trailing dot asks the API for "every action in this group".
const ACTION_FILTERS = [
  { label: 'All', value: '' },
  { label: 'Authentication', value: 'auth.' },
  { label: 'Users', value: 'user.' },
  { label: 'Roles', value: 'role.' },
  { label: 'Settings', value: 'settings.' },
]

export function AuditPage() {
  const [action, setAction] = useState('')
  const [search, setSearch] = useState('')

  const logs = useAuditLogs({ action })

  // Client-side narrowing on top of the server filter: the server already
  // limited the page, so this is a cheap refinement, not the primary filter.
  const entries = (logs.data?.items ?? []).filter((entry) => {
    if (search === '') return true
    const haystack = `${entry.action} ${entry.actor_username ?? ''} ${entry.entity_type ?? ''} ${entry.entity_id ?? ''}`
    return haystack.toLowerCase().includes(search.toLowerCase())
  })

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <PageHeader
        title="Audit log"
        description="Every mutating action, who performed it, and what changed."
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {ACTION_FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              onClick={() => setAction(filter.value)}
              className={
                action === filter.value
                  ? 'rounded-md border border-accent px-2.5 py-1 text-sm text-accent'
                  : 'rounded-md border border-border px-2.5 py-1 text-sm text-text-muted hover:border-border-focus'
              }
            >
              {filter.label}
            </button>
          ))}
        </div>

        <Input
          // The `/` shortcut focuses whatever carries this attribute.
          data-search-input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Filter by actor, action or entity…"
          className="max-w-xs"
        />
      </div>

      {logs.isError ? (
        <Alert tone="error" title="Could not load the audit log">
          {logs.error instanceof ApiError ? logs.error.message : 'Unexpected error.'}
        </Alert>
      ) : (
        <Card
          title="Entries"
          meta={logs.data === undefined ? undefined : `${entries.length}`}
          className="overflow-hidden"
        >
          {logs.isPending ? (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-4/5" />
            </div>
          ) : entries.length === 0 ? (
            <EmptyState
              title="Nothing recorded yet"
              description="Actions appear here as soon as anyone changes something in the console."
            />
          ) : (
            <ul className="divide-y divide-border">
              {entries.map((entry) => (
                <AuditRow key={entry.id} entry={entry} />
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  )
}
