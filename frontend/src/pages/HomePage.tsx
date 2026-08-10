import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <main className="container">
      <h1>AI-powered resume screening</h1>
      <p className="muted" style={{ maxWidth: '60ch' }}>
        Pick a role, upload resumes, and get ATS scores, skill matching and ranked
        shortlists backed by semantic search and LLM explanations.
      </p>

      <div className="choice-grid">
        <Link to="/candidate" className="choice-card">
          <h2>I'm a candidate</h2>
          <p className="muted">
            Upload your resume for a specific role and see how well it matches —
            ATS score, job-fit score, matched and missing skills, plus concrete
            suggestions to improve it.
          </p>
        </Link>

        <Link to="/recruiter" className="choice-card">
          <h2>I'm a recruiter</h2>
          <p className="muted">
            Bulk-upload resumes against an open position and get every candidate
            scored, ranked and bucketed into Strong Match, Consider or Weak Match.
          </p>
        </Link>
      </div>

      <section className="section" style={{ marginTop: '2.5rem' }}>
        <h2>Build roadmap</h2>
        <ol className="roadmap">
          <li>
            <strong>Day 1 — shipped.</strong> Job-role catalogue, database, upload
            pipeline with validation and de-duplication.
          </li>
          <li>Day 2 — resume and job-description parsing.</li>
          <li>Day 3 — ATS scoring.</li>
          <li>Day 4 — semantic and skill matching.</li>
          <li>Day 5 — candidate ranking and shortlisting.</li>
          <li>Day 6 — RAG, LLM explanations, recruiter AI chat.</li>
          <li>Day 7 — evaluation benchmark, Docker, deployment.</li>
        </ol>
      </section>
    </main>
  )
}
