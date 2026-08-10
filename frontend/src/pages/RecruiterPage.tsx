import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { BulkUploadResponse, JobRoleSummary } from '../api/types'
import FileDropzone from '../components/FileDropzone'
import RolePicker from '../components/RolePicker'

export default function RecruiterPage() {
  const [role, setRole] = useState<JobRoleSummary | null>(null)
  const [batchName, setBatchName] = useState('')
  const [email, setEmail] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<BulkUploadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = role !== null && files.length > 0 && !submitting

  async function handleSubmit() {
    if (!role || files.length === 0) return

    setSubmitting(true)
    setError(null)
    setResult(null)

    try {
      const batch = await api.createBatch({
        job_role_id: role.id,
        name: batchName.trim() || `${role.title} screening`,
        ...(email.trim() ? { recruiter_email: email.trim() } : {}),
      })
      setResult(await api.uploadBatchResumes(batch.id, files))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Bulk upload failed. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="container">
      <h1>Screen candidates in bulk</h1>
      <p className="muted">
        Upload every resume for an open position and get them scored, ranked and
        bucketed.
      </p>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">1</span> Choose the position
        </div>
        <RolePicker selectedId={role?.id ?? null} onSelect={setRole} />
      </section>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">2</span> Name this batch
        </div>
        <div className="card">
          <div className="field">
            <label htmlFor="batch-name">Batch name</label>
            <input
              id="batch-name"
              className="input"
              value={batchName}
              placeholder={role ? `${role.title} screening` : 'e.g. Q3 AI hiring'}
              onChange={(event) => setBatchName(event.target.value)}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="recruiter-email">Your email (optional)</label>
            <input
              id="recruiter-email"
              className="input"
              type="email"
              value={email}
              placeholder="hiring@company.com"
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
        </div>
      </section>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">3</span> Upload resumes
        </div>
        <FileDropzone multiple files={files} onChange={setFiles} />
      </section>

      {error && <div className="alert alert--error">{error}</div>}

      <button className="btn" disabled={!canSubmit} onClick={handleSubmit}>
        {submitting
          ? 'Uploading…'
          : `Upload ${files.length || ''} resume${files.length === 1 ? '' : 's'}`}
      </button>

      {result && (
        <section className="section" style={{ marginTop: '1.75rem' }}>
          <div className="stat-row">
            <div className="stat">
              <div className="stat__value">{result.received}</div>
              <div className="stat__label">Received</div>
            </div>
            <div className="stat">
              <div className="stat__value">{result.uploaded}</div>
              <div className="stat__label">Uploaded</div>
            </div>
            <div className="stat">
              <div className="stat__value">{result.duplicates}</div>
              <div className="stat__label">Duplicates</div>
            </div>
            <div className="stat">
              <div className="stat__value">{result.rejected}</div>
              <div className="stat__label">Rejected</div>
            </div>
          </div>

          <div className="card">
            <h2>Per-file result</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((item, index) => (
                    <tr key={`${item.filename}-${index}`}>
                      <td>{item.filename}</td>
                      <td>
                        <span className={`badge badge--${item.status}`}>
                          {item.status}
                        </span>
                      </td>
                      <td style={{ whiteSpace: 'normal' }}>
                        {item.error ?? <span className="muted">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ marginTop: '0.9rem', marginBottom: 0 }}>
              Batch <code>{result.batch_id.slice(0, 8)}…</code> is queued. Ranking and
              shortlisting arrive on Day 5.
            </p>
          </div>
        </section>
      )}
    </main>
  )
}
