// Wizard step 5: confirm what is about to be created. Calls no API.

interface Props {
  fullName: string
  username: string
  email: string
  orgName: string
  timezone: string
  hasLogo: boolean
}

export function StepReview({ fullName, username, email, orgName, timezone, hasLogo }: Props) {
  const rows: { label: string; value: string; mono?: boolean }[] = [
    { label: 'Full name', value: fullName },
    { label: 'Username', value: username, mono: true },
    { label: 'Email', value: email, mono: true },
    { label: 'Organisation', value: orgName.trim() || '— none —' },
    { label: 'Logo', value: hasLogo ? 'Uploaded' : 'Generated monogram' },
    { label: 'Timezone', value: timezone, mono: true },
    { label: 'Role', value: 'Super Admin' },
    { label: 'Two-factor', value: 'Enabled and verified' },
  ]

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-text-muted">
        Everything is created in a single transaction: your account, the Super Admin role, the
        permission and panel definitions, and the instance settings.
      </p>

      <dl className="divide-y divide-border rounded-md border border-border">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline gap-4 px-3 py-2">
            <dt className="w-32 shrink-0 text-sm text-text-dim">{row.label}</dt>
            <dd className={row.mono === true ? 'machine text-text' : 'text-text'}>{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
