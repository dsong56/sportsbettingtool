import { useState } from 'react'
import Dashboard from './pages/Dashboard'
import Portfolio from './pages/Portfolio'

type Page = 'dashboard' | 'portfolio'

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 z-20 bg-gray-950/80 backdrop-blur border-b border-gray-800">
        <div className="max-w-screen-xl mx-auto px-6 h-12 flex items-center gap-6">
          <span className="text-white font-bold text-lg tracking-tight">EV Bets</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage('dashboard')}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                page === 'dashboard' ? 'text-white bg-gray-800' : 'text-gray-400 hover:text-white'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setPage('portfolio')}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                page === 'portfolio' ? 'text-white bg-gray-800' : 'text-gray-400 hover:text-white'
              }`}
            >
              Portfolio
            </button>
          </div>
        </div>
      </nav>
      <div className="pt-12">
        {page === 'dashboard'  && <Dashboard onNavigatePortfolio={() => setPage('portfolio')} />}
        {page === 'portfolio'  && <Portfolio />}
      </div>
    </>
  )
}
