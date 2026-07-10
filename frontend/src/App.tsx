import { useState } from 'react'
import Dashboard from './pages/Dashboard'
import Portfolio from './pages/Portfolio'
import Calibration from './pages/Calibration'

type Page = 'dashboard' | 'portfolio' | 'calibration'

const PAGES: { id: Page; label: string }[] = [
  { id: 'dashboard',   label: 'Dashboard' },
  { id: 'portfolio',   label: 'Portfolio' },
  { id: 'calibration', label: 'Calibration' },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <header className="border-b border-gray-800 bg-gray-900/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center gap-8">
          <span className="text-xl font-bold text-white tracking-tight">EV Bets</span>
          <nav className="flex items-center gap-1">
            {PAGES.map(p => (
              <button
                key={p.id}
                onClick={() => setPage(p.id)}
                className={`px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
                  page === p.id
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`}
              >
                {p.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {page === 'dashboard'   && <Dashboard />}
      {page === 'portfolio'   && <Portfolio />}
      {page === 'calibration' && <Calibration />}
    </div>
  )
}
