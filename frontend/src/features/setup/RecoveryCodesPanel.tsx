// Shown once, after onboarding completes: the ten single-use recovery codes.
// Calls no API — the codes arrive in the /setup/complete response.
//
// This is the only time they exist in plaintext; the backend stores Argon2
// hashes. The acknowledgement checkbox gates entry to the console so the codes
// cannot be skipped past by reflex.

import { useState } from 'react'
import { Check, Copy, Download } from 'lucide-react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'

interface Props {
  codes: string[]
  orgName: string | null
  onContinue: () => void
}

export function RecoveryCodesPanel({ codes, orgName, onContinue }: Props) {
  const [copied, setCopied] = useState(false)
  const [acknowledged, setAcknowledged] = useState(false)

  async function copyAll() {
    await navigator.clipboard.writeText(codes.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function download() {
    const header = [
      `HAYABUSA recovery codes${orgName !== null ? ` — ${orgName}` : ''}`,
      `Generated ${new Date().toISOString()}`,
      '',
      'Each code works once, in place of your authenticator code.',
      'Store these somewhere safe and offline.',
      '',
    ].join('\n')

    // Build the file in memory and click a temporary link — the standard way to
    // trigger a download without a server round trip. The object URL is revoked
    // afterwards so the blob can be garbage collected.
    const blob = new Blob([header + codes.join('\n') + '\n'], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'hayabusa-recovery-codes.txt'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col gap-4">
      <Alert tone="warning" title="Save these now">
        These ten codes are shown once and cannot be retrieved later. Each works a single time in
        place of your authenticator code.
      </Alert>

      <ul className="grid grid-cols-2 gap-2 rounded-md border border-border bg-bg-subtle p-3">
        {codes.map((code) => (
          <li key={code} className="machine text-center tracking-wider text-text">
            {code}
          </li>
        ))}
      </ul>

      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={copyAll} className="flex-1">
          {copied ? <Check className="size-4 text-ok" /> : <Copy className="size-4" />}
          {copied ? 'Copied' : 'Copy all'}
        </Button>
        <Button type="button" variant="secondary" onClick={download} className="flex-1">
          <Download className="size-4" />
          Download
        </Button>
      </div>

      <label className="flex cursor-pointer items-start gap-2.5 text-sm text-text-muted">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
          className="mt-0.5 size-4 shrink-0 accent-[rgb(var(--accent))]"
        />
        I have saved these recovery codes somewhere safe.
      </label>

      <Button type="button" variant="primary" onClick={onContinue} disabled={!acknowledged}>
        Enter HAYABUSA
      </Button>
    </div>
  )
}
