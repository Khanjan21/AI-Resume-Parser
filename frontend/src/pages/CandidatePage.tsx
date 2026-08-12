import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { JobRoleSummary, ResumeDetail, ResumeUploadResponse } from '../api/types'
import FileDropzone, { formatBytes } from '../components/FileDropzone'
import RolePicker from '../components/RolePicker'

const POLL_INTERVAL_MS = 2000

function isTerminal(detail: ResumeDetail): boolean {
  if (detail.parse_status === 'failed') return true
  if (detail.parse_status !== 'parsed') return false
  return detail.analysis_status === 'completed' || detail.analysis_status === 'failed'
}

function statusBadgeClass(status: string): string {
  if (status === 'parsed' || status === 'completed') return 'badge badge--uploaded'
  if (status === 'failed') return 'badge badge--rejected'
  if (status === 'processing') return 'badge badge--processing'
  return 'badge badge--pending'
}

function scoreBarClass(value: number): string {
  if (value >= 70) return 'score-bar__fill score-bar__fill--good'
  if (value >= 40) return 'score-bar__fill score-bar__fill--warn'
  return 'score-bar__fill score-bar__fill--bad'
}

function overallLabel(value: number): string {
  if (value >= 75) return 'Strong match'
  if (value >= 50) return 'Good potential'
  if (value >= 25) return 'Needs some work'
  return 'Needs significant improvement'
}

function ScoreHero({ value }: { value: number }) {
  const rounded = Math.round(value)
  return (
    <div className="score-hero">
      <div className="score-hero__value">{rounded}%</div>
      <div className="score-hero__bar-wrap">
        <div className="score-hero__label">{overallLabel(value)}</div>
        <div className="score-bar">
          <div
            className={scoreBarClass(value)}
            style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export default function CandidatePage() {
  const [role, setRole] = useState<JobRoleSummary | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [uploadInfo, setUploadInfo] = useState<{ duplicate: boolean; message: string } | null>(
    null,
  )
  const [detail, setDetail] = useState<ResumeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = role !== null && files.length === 1 && !submitting

  // Polls the resume until parsing (and, if it succeeds, scoring) finishes —
  // both run in the background, so the upload response alone only ever shows
  // the "pending" snapshot from the instant the file landed.
  useEffect(() => {
    if (!detail || isTerminal(detail)) return

    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const next = await api.getResume(detail.id)
        if (!cancelled) setDetail(next)
      } catch {
        // Transient network hiccup — the next tick will retry.
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [detail])

  async function handleSubmit() {
    if (!role || files.length !== 1) return

    setSubmitting(true)
    setError(null)
    setUploadInfo(null)
    setDetail(null)

    try {
      const result: ResumeUploadResponse = await api.uploadResume(role.id, files[0])
      setUploadInfo({ duplicate: result.duplicate, message: result.message })
      setDetail(await api.getResume(result.resume.id))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Upload failed. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  const stillWorking = detail !== null && !isTerminal(detail)
  const score = detail?.score ?? null

  return (
    <main className="container">
      <h1>Check your resume against a role</h1>
      <p className="muted">
        Upload once and get an ATS score, job-fit score, matched and missing skills.
      </p>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">1</span> Choose a role
        </div>
        <RolePicker selectedId={role?.id ?? null} onSelect={setRole} />
      </section>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">2</span> Upload your resume
        </div>
        <FileDropzone files={files} onChange={setFiles} />
      </section>

      {error && <div className="alert alert--error">{error}</div>}

      <button className="btn" disabled={!canSubmit} onClick={handleSubmit}>
        {submitting ? 'Uploading…' : 'Upload resume'}
      </button>
      {!role && (
        <span className="muted" style={{ marginLeft: '0.75rem', fontSize: '0.85rem' }}>
          Select a role first
        </span>
      )}

      {detail && (
        <section className="section" style={{ marginTop: '1.75rem' }}>
          {uploadInfo && (
            <div className={uploadInfo.duplicate ? 'alert alert--info' : 'alert alert--success'}>
              {uploadInfo.message}
            </div>
          )}

          <div className="card" style={{ marginBottom: stillWorking || score ? '1.25rem' : 0 }}>
            <h2>Uploaded file</h2>
            <div className="table-wrap">
              <table>
                <tbody>
                  <tr>
                    <th>File</th>
                    <td>{detail.original_filename}</td>
                  </tr>
                  <tr>
                    <th>Size</th>
                    <td>{formatBytes(detail.file_size_bytes)}</td>
                  </tr>
                  <tr>
                    <th>Type</th>
                    <td>{detail.content_type}</td>
                  </tr>
                  <tr>
                    <th>Fingerprint</th>
                    <td>
                      <code>{detail.content_hash.slice(0, 16)}…</code>
                    </td>
                  </tr>
                  <tr>
                    <th>Parse status</th>
                    <td>
                      <span className={statusBadgeClass(detail.parse_status)}>
                        {detail.parse_status}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <th>Analysis status</th>
                    <td>
                      <span className={statusBadgeClass(detail.analysis_status)}>
                        {detail.analysis_status}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {stillWorking && (
            <div className="alert alert--info">
              {detail.parse_status !== 'parsed'
                ? 'Reading your resume…'
                : 'Scoring your resume against the role…'}{' '}
              This updates automatically — no need to refresh.
            </div>
          )}

          {detail.parse_status === 'failed' && (
            <div className="alert alert--error">
              Couldn't read this file: {detail.parse_error ?? 'unknown error.'}
            </div>
          )}

          {detail.parse_status === 'parsed' && detail.analysis_status === 'failed' && (
            <div className="alert alert--error">
              Couldn't score this resume: {detail.analysis_error ?? 'unknown error.'}
            </div>
          )}

          {score && (
            <div className="card">
              <h2>Your match for {role?.title ?? 'this role'}</h2>

              {score.final_score !== null ? (
                <ScoreHero value={score.final_score} />
              ) : (
                <div className="alert alert--info" style={{ marginBottom: '1.25rem' }}>
                  Your overall score is still being finalized —{' '}
                  <button
                    type="button"
                    className="btn btn--ghost"
                    style={{ padding: '0.15rem 0.6rem', fontSize: '0.82rem' }}
                    onClick={() => api.getResume(detail!.id).then(setDetail)}
                  >
                    check again
                  </button>
                </div>
              )}

              {score.matched_skills.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.9rem', marginBottom: '0.4rem' }}>Matched skills</h3>
                  <div className="chips" style={{ marginTop: 0, marginBottom: '1rem' }}>
                    {score.matched_skills.map((skill) => (
                      <span key={skill} className="chip">
                        {skill}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {score.missing_skills.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.9rem', marginBottom: '0.4rem' }}>Missing skills</h3>
                  <div className="chips" style={{ marginTop: 0, marginBottom: '1rem' }}>
                    {score.missing_skills.map((skill) => (
                      <span key={skill} className="chip">
                        {skill}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {score.suggestions.length > 0 && (
                <>
                  <h3 style={{ fontSize: '0.9rem', marginBottom: '0.6rem' }}>
                    Suggestions to strengthen your resume
                  </h3>
                  <ul className="suggestions-list">
                    {score.suggestions.map((suggestion) => (
                      <li key={suggestion}>{suggestion}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </section>
      )}
    </main>
  )
}
