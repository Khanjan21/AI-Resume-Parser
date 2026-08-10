import { NavLink, Route, Routes } from 'react-router-dom'
import CandidatePage from './pages/CandidatePage'
import HomePage from './pages/HomePage'
import RecruiterPage from './pages/RecruiterPage'

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? 'nav__link nav__link--active' : 'nav__link'
}

export default function App() {
  return (
    <div className="app">
      <nav className="nav">
        <NavLink to="/" className="nav__brand">
          AI Resume Screening
        </NavLink>
        <div className="nav__links">
          <NavLink to="/candidate" className={navClass}>
            For Candidates
          </NavLink>
          <NavLink to="/recruiter" className={navClass}>
            For Recruiters
          </NavLink>
        </div>
      </nav>

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/candidate" element={<CandidatePage />} />
        <Route path="/recruiter" element={<RecruiterPage />} />
      </Routes>
    </div>
  )
}
