// Route: "/admin/settings" — organisation identity and instance defaults.
// Endpoints: GET/PATCH /api/v1/settings, POST /api/v1/settings/logo

import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Skeleton } from '@/components/ui/Skeleton'
import { OrgAvatar } from '@/components/layout/OrgAvatar'
import { useSettings, useUpdateSettings } from '@/features/admin/api'
import { ApiError, apiUpload } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'

const TIMEZONES = [
  'Asia/Kuala_Lumpur',
  'Asia/Singapore',
  'Asia/Jakarta',
  'Asia/Bangkok',
  'Asia/Hong_Kong',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/London',
  'America/New_York',
  'UTC',
]

export function SettingsPage() {
  const settings = useSettings()
  const update = useUpdateSettings()

  const [orgName, setOrgName] = useState('')
  const [timezone, setTimezone] = useState('Asia/Kuala_Lumpur')
  const [brandColor, setBrandColor] = useState('#22D3EE')
  const [uploading, setUploading] = useState(false)

  // Seed the form once the server data arrives. Without this the inputs would
  // stay empty, because their initial state was set before the fetch resolved.
  const loaded = settings.data
  useEffect(() => {
    if (loaded === undefined) return
    setOrgName(loaded.org_name ?? '')
    setTimezone(loaded.timezone)
    setBrandColor(loaded.brand_color)
  }, [loaded])

  function save() {
    update.mutate(
      { org_name: orgName.trim() || null, timezone, brand_color: brandColor },
      {
        onSuccess: () => toast.success('Settings saved.'),
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.message : 'Could not save.'),
      },
    )
  }

  async function uploadLogo(file: File) {
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const result = await apiUpload('/settings/logo', form)
      update.mutate(
        { logo_filename: result.filename },
        { onSuccess: () => toast.success('Logo updated.') },
      )
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  if (settings.isPending) {
    return (
      <div className="flex flex-col gap-3 p-4 sm:p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (settings.isError) {
    return (
      <div className="p-4 sm:p-6">
        <Alert tone="error" title="Could not load settings">
          {settings.error instanceof ApiError ? settings.error.message : 'Unexpected error.'}
        </Alert>
      </div>
    )
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <PageHeader title="Settings" description="Organisation identity and instance defaults." />

      <Card title="Organisation">
        <div className="flex flex-col gap-4">
          <Field label="Name" hint="Shown in the top bar and in delivered alerts.">
            <Input value={orgName} onChange={(event) => setOrgName(event.target.value)} />
          </Field>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-text-muted">Logo</span>
            <div className="flex items-center gap-4">
              <OrgAvatar
                logoUrl={settings.data.org_logo_url}
                initials={settings.data.org_initials}
                size="md"
              />
              <label className="inline-flex">
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file !== undefined) void uploadLogo(file)
                  }}
                />
                <span className="inline-flex h-8 cursor-pointer items-center rounded-md border border-border bg-surface-2 px-3 text-sm hover:border-border-focus">
                  {uploading ? 'Uploading…' : 'Replace logo'}
                </span>
              </label>
              {settings.data.org_logo_url !== null && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    update.mutate(
                      { logo_filename: '' },
                      { onSuccess: () => toast.success('Reverted to the generated mark.') },
                    )
                  }
                >
                  Use generated mark
                </Button>
              )}
            </div>
            <span className="text-sm text-text-dim">PNG, JPG, WebP or SVG · max 2 MB</span>
          </div>

          <Field label="Accent colour" hint="Links, focus rings and the active navigation item.">
            <div className="flex gap-2">
              <input
                type="color"
                value={brandColor}
                onChange={(event) => setBrandColor(event.target.value)}
                className="h-9 w-14 cursor-pointer rounded-md border border-border bg-bg-subtle p-1"
              />
              <Input mono value={brandColor} readOnly className="max-w-32" />
            </div>
          </Field>
        </div>
      </Card>

      <Card title="Regional">
        <Field label="Timezone" hint="Timestamps are stored in UTC and rendered in this zone.">
          <select
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            className="h-9 w-full rounded-md border border-border bg-bg-subtle px-3 text-base text-text hover:border-border-focus focus:outline-none focus:ring-2 focus:ring-accent"
          >
            {TIMEZONES.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </Field>
      </Card>

      <Card title="Instance">
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-text-dim">Set up</dt>
            <dd className="machine text-text-muted">
              {settings.data.setup_completed_at === null
                ? '—'
                : formatDateTime(settings.data.setup_completed_at)}
            </dd>
          </div>
        </dl>
      </Card>

      <div className="flex justify-end">
        <Button variant="primary" onClick={save} disabled={update.isPending}>
          {update.isPending ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </div>
  )
}
