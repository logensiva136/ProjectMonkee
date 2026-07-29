// Wizard step 2: organisation name, logo, timezone.
// Endpoints: POST /api/v1/setup/logo, POST /api/v1/setup/monogram-preview
//
// With no logo, a deterministic monogram is generated from the name. The
// preview comes from the backend so what is shown here is byte-identical to
// what the console renders later (SPEC §9.0 Rule 6).

import { useEffect, useState } from 'react'
import { Upload, X } from 'lucide-react'

import { Alert } from '@/components/ui/Alert'
import { Field } from '@/components/ui/Field'
import { Input } from '@/components/ui/Input'
import { usePreviewMonogram, useUploadLogo } from '@/features/setup/api'
import { ApiError } from '@/lib/api'

// A short list beats a 400-entry dropdown; anything else is editable later on
// /admin/settings.
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

interface Props {
  orgName: string
  timezone: string
  logoFilename: string | null
  logoUrl: string | null
  fallbackName: string
  onChange: (field: 'orgName' | 'timezone', value: string) => void
  onLogo: (filename: string | null, url: string | null) => void
}

export function StepOrganisation({
  orgName,
  timezone,
  logoFilename,
  logoUrl,
  fallbackName,
  onChange,
  onLogo,
}: Props) {
  const upload = useUploadLogo()
  const preview = usePreviewMonogram()
  const [monogramSvg, setMonogramSvg] = useState('')

  const previewName = orgName.trim() || fallbackName.trim()

  // Debounced: refresh the monogram 350ms after typing stops, rather than on
  // every keystroke. The cleanup cancels the pending timer when `previewName`
  // changes again — without it, every character would fire its own request.
  const mutate = preview.mutate
  useEffect(() => {
    if (!previewName || logoFilename !== null) return

    const timer = setTimeout(() => {
      mutate(previewName, { onSuccess: (result) => setMonogramSvg(result.svg) })
    }, 350)

    return () => clearTimeout(timer)
  }, [previewName, logoFilename, mutate])

  const uploadError = upload.error instanceof ApiError ? upload.error.message : null

  return (
    <div className="flex flex-col gap-4">
      <Field label="Organisation name" hint="Optional. Shown in the top bar and in alerts.">
        <Input
          value={orgName}
          onChange={(event) => onChange('orgName', event.target.value)}
          placeholder="Acme Bank Sdn Bhd"
          autoFocus
        />
      </Field>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-text-muted">Logo</span>
        <div className="flex items-center gap-4">
          <div className="size-16 shrink-0 overflow-hidden rounded-md border border-border">
            {logoUrl !== null ? (
              <img src={logoUrl} alt="Organisation logo" className="size-full object-contain" />
            ) : (
              // The backend returns trusted, self-generated SVG built from a
              // fixed template — no user markup reaches this.
              <div
                className="size-full [&>svg]:size-full"
                dangerouslySetInnerHTML={{ __html: monogramSvg }}
              />
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="inline-flex">
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file === undefined) return
                  upload.mutate(file, {
                    onSuccess: (result) => onLogo(result.filename, result.url),
                  })
                }}
              />
              <span className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-border bg-surface-2 px-3 text-sm hover:border-border-focus">
                <Upload className="size-3.5" />
                {upload.isPending ? 'Uploading…' : 'Upload logo'}
              </span>
            </label>

            {logoFilename !== null ? (
              <button
                type="button"
                onClick={() => onLogo(null, null)}
                className="inline-flex items-center gap-1 text-sm text-text-dim hover:text-text"
              >
                <X className="size-3" /> Remove, use generated mark
              </button>
            ) : (
              <span className="text-sm text-text-dim">PNG, JPG, WebP or SVG · max 2 MB</span>
            )}
          </div>
        </div>

        {uploadError !== null && <Alert tone="error">{uploadError}</Alert>}
      </div>

      <Field label="Timezone" hint="Timestamps are stored in UTC and displayed in this zone.">
        <select
          value={timezone}
          onChange={(event) => onChange('timezone', event.target.value)}
          className="h-9 w-full rounded-md border border-border bg-bg-subtle px-3 text-base text-text hover:border-border-focus focus:outline-none focus:ring-2 focus:ring-accent"
        >
          {TIMEZONES.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </Field>
    </div>
  )
}
