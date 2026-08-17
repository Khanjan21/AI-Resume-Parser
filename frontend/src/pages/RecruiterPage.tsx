import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { BatchDetail, BulkUploadResponse, JobRoleSummary, ResumeDetail, ShortlistCategory } from '../api/types'
import FileDropzone from '../components/FileDropzone'
import RolePicker from '../components/RolePicker'

type JdMode = 'text' | 'file'

const POLL_INTERVAL_MS = 2000

function isResumeTerminal(resume: ResumeDetail): boolean {
  if (resume.parse_status === 'failed') return true
  if (resume.parse_status !== 'parsed') return false
  return resume.analysis_status === 'completed' || resume.analysis_status === 'failed'
}

function candidateName(resume: ResumeDetail): string {
  const name = resume.parsed_data?.full_name
  return typeof name === 'string' && name.trim() ? name : resume.original_filename
}

function categoryLabel(category: ShortlistCategory | null): string {
  if (category === 'strong_match') return 'Strong match'
  if (category === 'consider') return 'Consider'
  if (category === 'weak_match') return 'Weak match'
  return 'Scoring…'
}

function categoryBadgeClass(category: ShortlistCategory | null): string {
  if (category === 'strong_match') return 'badge badge--strong-match'
  if (category === 'consider') return 'badge badge--consider'
  if (category === 'weak_match') return 'badge badge--weak-match'
  return 'badge badge--pending'
}

export default function RecruiterPage() {
  const [role, setRole] = useState<JobRoleSummary | null>(null)
  const [jdMode, setJdMode] = useState<JdMode>('text')
  const [jdText, setJdText] = useState('')
  const [jdFile, setJdFile] = useState<File[]>([])
  const [batchName, setBatchName] = useState('')
  const [email, setEmail] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<BulkUploadResponse | null>(null)
  const [batchDetail, setBatchDetail] = useState<BatchDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const hasJd = jdMode === 'text' ? jdText.trim().length > 0 : jdFile.length > 0
  const canSubmit = role !== null && files.length > 0 && !submitting
  const stillScoring = batchDetail !== null && batchDetail.resumes.some((r) => !isResumeTerminal(r))

  // Polls the batch until every resume finishes parsing and (if it succeeds)
  // scoring — both run in the background, so ranking/categories only settle
  // in gradually after the upload response comes back.
  useEffect(() => {
    if (!batchDetail || !stillScoring) return

    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const next = await api.getBatch(batchDetail.id)
        if (!cancelled) setBatchDetail(next)
      } catch {
        // Transient network hiccup — the next tick will retry.
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [batchDetail, stillScoring])

  async function handleSubmit() {
    if (!role || files.length === 0) return

    setSubmitting(true)
    setError(null)
    setResult(null)
    setBatchDetail(null)

    try {
      let jobDescriptionId: string | undefined

      if (hasJd) {
        const jd = await api.createJobDescription({
          title: role.title,
          job_role_id: role.id,
          ...(jdMode === 'text' ? { raw_text: jdText.trim() } : { file: jdFile[0] }),
        })
        jobDescriptionId = jd.id
      }

      const batch = await api.createBatch({
        job_role_id: role.id,
        name: batchName.trim() || `${role.title} screening`,
        ...(email.trim() ? { recruiter_email: email.trim() } : {}),
        ...(jobDescriptionId ? { job_description_id: jobDescriptionId } : {}),
      })
      setResult(await api.uploadBatchResumes(batch.id, files))
      setBatchDetail(await api.getBatch(batch.id))
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
          <span className="step-label__num">2</span> Add the job description
          <span className="muted" style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
            {' '}
            (optional)
          </span>
        </div>
        <div className="card">
          <p className="muted" style={{ marginTop: 0, fontSize: '0.85rem' }}>
            Paste the job posting or upload it as a file. This gets parsed and matched
            against each candidate — without it, resumes are still screened against the
            role's general skill vocabulary.
          </p>

          <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.9rem' }}>
            <button
              type="button"
              className={jdMode === 'text' ? 'btn' : 'btn btn--ghost'}
              onClick={() => setJdMode('text')}
            >
              Paste text
            </button>
            <button
              type="button"
              className={jdMode === 'file' ? 'btn' : 'btn btn--ghost'}
              onClick={() => setJdMode('file')}
            >
              Upload a file
            </button>
          </div>

          {jdMode === 'text' ? (
            <textarea
              className="input"
              rows={6}
              style={{ resize: 'vertical', fontFamily: 'inherit' }}
              value={jdText}
              placeholder="Paste the full job description here…"
              onChange={(event) => setJdText(event.target.value)}
            />
          ) : (
            <FileDropzone files={jdFile} onChange={setJdFile} />
          )}
        </div>
      </section>

      <section className="section">
        <div className="step-label">
          <span className="step-label__num">3</span> Name this batch
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
          <span className="step-label__num">4</span> Upload resumes
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
              Batch <code>{result.batch_id.slice(0, 8)}…</code> is queued
              {hasJd ? ', linked to the job description you provided' : ''}.
            </p>
          </div>
        </section>
      )}

      {batchDetail && batchDetail.resumes.length > 0 && (
        <section className="section">
          <h2>Ranked results</h2>

          {stillScoring && (
            <div className="alert alert--info">
              Parsing and scoring resumes… This updates automatically — no need
              to refresh.
            </div>
          )}

          <div className="stat-row">
            <div className="stat">
              <div className="stat__value">{batchDetail.category_counts.strong_match}</div>
              <div className="stat__label">Strong match</div>
            </div>
            <div className="stat">
              <div className="stat__value">{batchDetail.category_counts.consider}</div>
              <div className="stat__label">Consider</div>
            </div>
            <div className="stat">
              <div className="stat__value">{batchDetail.category_counts.weak_match}</div>
              <div className="stat__label">Weak match</div>
            </div>
            <div className="stat">
              <div className="stat__value">{batchDetail.category_counts.unscored}</div>
              <div className="stat__label">Still scoring</div>
            </div>
          </div>

          <div className="card">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Candidate</th>
                    <th>Score</th>
                    <th>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {batchDetail.resumes.map((resume, index) => (
                    <tr key={resume.id}>
                      <td>{index + 1}</td>
                      <td>{candidateName(resume)}</td>
                      <td>
                        {resume.score?.final_score != null
                          ? `${Math.round(resume.score.final_score)}%`
                          : <span className="muted">—</span>}
                      </td>
                      <td>
                        <span className={categoryBadgeClass(resume.score?.category ?? null)}>
                          {resume.parse_status === 'failed' || resume.analysis_status === 'failed'
                            ? 'Failed'
                            : categoryLabel(resume.score?.category ?? null)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </main>
  )
}
