import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { JobRoleSummary, ResumeUploadResponse } from '../api/types'
import FileDropzone, { formatBytes } from '../components/FileDropzone'
import RolePicker from '../components/RolePicker'

export default function CandidatePage() {
  const [role, setRole] = useState<JobRoleSummary | null>(null)
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<ResumeUploadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = role !== null && files.length === 1 && !submitting

  async function handleSubmit() {
    if (!role || files.length !== 1) return

    setSubmitting(true)
    setError(null)
    setResult(null)

    try {
      setResult(await api.uploadResume(role.id, files[0]))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Upload failed. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

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

      {result && (
        <section className="section" style={{ marginTop: '1.75rem' }}>
          <div
            className={result.duplicate ? 'alert alert--info' : 'alert alert--success'}
          >
            {result.message}
          </div>

          <div className="card">
            <h2>Uploaded file</h2>
            <div className="table-wrap">
              <table>
                <tbody>
                  <tr>
                    <th>File</th>
                    <td>{result.resume.original_filename}</td>
                  </tr>
                  <tr>
                    <th>Size</th>
                    <td>{formatBytes(result.resume.file_size_bytes)}</td>
                  </tr>
                  <tr>
                    <th>Type</th>
                    <td>{result.resume.content_type}</td>
                  </tr>
                  <tr>
                    <th>Fingerprint</th>
                    <td>
                      <code>{result.resume.content_hash.slice(0, 16)}…</code>
                    </td>
                  </tr>
                  <tr>
                    <th>Parse status</th>
                    <td>{result.resume.parse_status}</td>
                  </tr>
                  <tr>
                    <th>Analysis status</th>
                    <td>{result.resume.analysis_status}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ marginTop: '0.9rem', marginBottom: 0 }}>
              Parsing lands on Day 2 and scoring on Day 3 — this record is already
              queued for both.
            </p>
          </div>
        </section>
      )}
    </main>
  )
}
