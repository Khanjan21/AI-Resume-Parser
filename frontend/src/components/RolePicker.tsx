import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { JobRoleSummary } from '../api/types'

interface Props {
  selectedId: string | null
  onSelect: (role: JobRoleSummary) => void
}

export default function RolePicker({ selectedId, onSelect }: Props) {
  const [roles, setRoles] = useState<JobRoleSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    api
      .listJobRoles()
      .then((page) => {
        if (!cancelled) setRoles(page.items)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach the API. Is the backend running on port 8000?',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <p className="muted">Loading roles…</p>
  if (error) return <div className="alert alert--error">{error}</div>

  return (
    <div className="role-grid">
      {roles.map((role) => (
        <button
          key={role.id}
          type="button"
          onClick={() => onSelect(role)}
          aria-pressed={selectedId === role.id}
          className={
            selectedId === role.id ? 'role-card role-card--selected' : 'role-card'
          }
        >
          <div className="role-card__title">{role.title}</div>
          <div className="role-card__summary">{role.summary}</div>
          <div className="chips">
            {role.required_skills.slice(0, 4).map((skill) => (
              <span key={skill} className="chip">
                {skill}
              </span>
            ))}
            {role.required_skills.length > 4 && (
              <span className="chip">+{role.required_skills.length - 4}</span>
            )}
          </div>
        </button>
      ))}
    </div>
  )
}
