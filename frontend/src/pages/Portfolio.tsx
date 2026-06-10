import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import {
  fetchPaperSummary, fetchPaperBets, cancelPaperBet,
  resetPaperBankroll, updatePaperSettings,
  type PaperBet, type PaperSummary,
} from '../api'

function StatCard({ label, value, sub, color = 'text-white' }: {
  label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-2xl font-bold font-mono ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function StatusBadge({ status }: { status: PaperBet['status'] }) {
  const map: Record<string, string> = {
    pending:   'bg-yellow-500/20 text-yellow-400',
    won:       'bg-emerald-500/20 text-emerald-400',
    lost:      'bg-red-500/20 text-red-400',
    partial:   'bg-blue-500/20 text-blue-400',
    cancelled: 'bg-gray-700 text-gray-500',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${map[status] ?? ''}`}>
      {status}
    </span>
  )
}

function BetRow({ bet, onCancel }: { bet: PaperBet; onCancel?: () => void }) {
  const [open, setOpen] = useState(false)
  const pl = bet.profit_loss ?? 0

  return (
    <>
      <tr
        className="border-b border-gray-800 hover:bg-gray-800/40 cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
          {new Date(bet.placed_at).toLocaleDateString()}
        </td>
        <td className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">
          {bet.n_picks}-Pick {bet.play_type === 'power' ? 'Power' : 'Flex'}
        </td>
        <td className="px-4 py-3 text-sm font-mono text-gray-200">${bet.stake.toFixed(2)}</td>
        <td className="px-4 py-3 text-sm font-mono text-gray-400">${bet.potential_payout.toFixed(2)}</td>
        <td className="px-4 py-3">
          <StatusBadge status={bet.status} />
        </td>
        <td className="px-4 py-3 text-sm font-mono">
          {bet.status !== 'pending' && bet.status !== 'cancelled' ? (
            <span className={pl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {pl >= 0 ? '+' : ''}${pl.toFixed(2)}
            </span>
          ) : (
            <span className="text-gray-600">—</span>
          )}
        </td>
        <td className="px-4 py-3">
          {bet.status === 'pending' && (
            <button
              onClick={e => { e.stopPropagation(); onCancel?.() }}
              className="text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              Cancel
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-gray-800">
          <td colSpan={7} className="px-4 py-3 bg-gray-900/50">
            <div className="space-y-1">
              {bet.picks.map((p, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="text-gray-300">
                    {p.player_name} — {p.direction} {p.line_score} {p.stat_type}
                    {p.matchup && <span className="text-gray-600 ml-1">({p.matchup})</span>}
                  </span>
                  <span className="text-indigo-300 font-mono">{(p.blended_prob * 100).toFixed(1)}%</span>
                </div>
              ))}
              {bet.hits !== null && (
                <p className="text-xs text-gray-500 pt-1">
                  Result: {bet.hits}/{bet.n_picks} picks hit
                </p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function Portfolio() {
  const qc = useQueryClient()
  const [showReset, setShowReset]           = useState(false)
  const [newBankroll, setNewBankroll]       = useState('')
  const [editingBankroll, setEditingBankroll] = useState(false)

  const { data: summary, isLoading: summaryLoading } = useQuery<PaperSummary>({
    queryKey: ['paper-summary'],
    queryFn: fetchPaperSummary,
    staleTime: 30_000,
  })

  const { data: bets = [] } = useQuery<PaperBet[]>({
    queryKey: ['paper-bets'],
    queryFn: () => fetchPaperBets(),
    staleTime: 30_000,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['paper-summary'] })
    qc.invalidateQueries({ queryKey: ['paper-bets'] })
  }

  async function handleCancel(id: number) {
    await cancelPaperBet(id)
    refresh()
  }

  async function handleReset() {
    await resetPaperBankroll()
    setShowReset(false)
    refresh()
  }

  async function handleUpdateBankroll() {
    const val = parseFloat(newBankroll)
    if (!val || val <= 0) return
    await updatePaperSettings(val)
    setEditingBankroll(false)
    setNewBankroll('')
    refresh()
  }

  const pl = summary?.total_pl ?? 0
  const roi = summary?.roi_pct ?? 0

  const pending = bets.filter(b => b.status === 'pending')
  const settled = bets.filter(b => b.status !== 'pending')

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <div className="max-w-screen-xl mx-auto px-6 py-8 space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Paper Trading Portfolio</h1>
            <p className="text-sm text-gray-500 mt-1">
              Track virtual bets to validate the model before using real money
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setEditingBankroll(true)}
              className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition-colors"
            >
              Set bankroll
            </button>
            <button
              onClick={() => setShowReset(true)}
              className="text-sm text-red-400 hover:text-red-300 border border-red-900 hover:border-red-700 px-3 py-1.5 rounded-lg transition-colors"
            >
              Reset
            </button>
          </div>
        </div>

        {/* Set bankroll modal */}
        {editingBankroll && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-80 space-y-4">
              <h3 className="text-white font-semibold">Set Starting Bankroll</h3>
              <div className="flex items-center gap-2">
                <span className="text-gray-400">$</span>
                <input
                  type="number" min={1} step={1}
                  value={newBankroll}
                  onChange={e => setNewBankroll(e.target.value)}
                  placeholder="100"
                  className="flex-1 bg-gray-800 border border-gray-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <p className="text-xs text-amber-400/70">This will reset your current bankroll to the new amount.</p>
              <div className="flex gap-3">
                <button onClick={() => setEditingBankroll(false)} className="flex-1 py-2 text-sm text-gray-400 border border-gray-700 rounded-lg">Cancel</button>
                <button onClick={handleUpdateBankroll} className="flex-1 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg">Confirm</button>
              </div>
            </div>
          </div>
        )}

        {/* Reset confirmation */}
        {showReset && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-80 space-y-4">
              <h3 className="text-white font-semibold">Reset Portfolio?</h3>
              <p className="text-sm text-gray-400">All pending bets will be cancelled and your bankroll reset to ${summary?.starting_bankroll.toFixed(2)}. Settled bet history is preserved.</p>
              <div className="flex gap-3">
                <button onClick={() => setShowReset(false)} className="flex-1 py-2 text-sm text-gray-400 border border-gray-700 rounded-lg">Cancel</button>
                <button onClick={handleReset} className="flex-1 py-2 text-sm font-semibold bg-red-700 hover:bg-red-600 text-white rounded-lg">Reset</button>
              </div>
            </div>
          </div>
        )}

        {summaryLoading ? (
          <div className="text-center py-20 text-gray-600">Loading…</div>
        ) : (
          <>
            {/* Summary stats */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard
                label="Bankroll"
                value={`$${(summary?.current_bankroll ?? 0).toFixed(2)}`}
                sub={`Started at $${(summary?.starting_bankroll ?? 0).toFixed(2)}`}
              />
              <StatCard
                label="Total P&L"
                value={`${pl >= 0 ? '+' : ''}$${pl.toFixed(2)}`}
                sub={`ROI: ${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%`}
                color={pl >= 0 ? 'text-emerald-400' : 'text-red-400'}
              />
              <StatCard
                label="Win rate"
                value={`${summary?.win_rate ?? 0}%`}
                sub={`${summary?.wins ?? 0}W / ${summary?.losses ?? 0}L`}
              />
              <StatCard
                label="Pending"
                value={String(summary?.pending_bets ?? 0)}
                sub={`$${(summary?.pending_at_risk ?? 0).toFixed(2)} at risk`}
              />
            </div>

            {/* Bankroll chart */}
            {(summary?.bankroll_history?.length ?? 0) > 1 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <p className="text-sm font-medium text-gray-300 mb-4">Bankroll over time</p>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={summary!.bankroll_history}>
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
                    <YAxis
                      tick={{ fontSize: 11, fill: '#6b7280' }}
                      tickFormatter={v => `$${v}`}
                      domain={['auto', 'auto']}
                    />
                    <Tooltip
                      contentStyle={{ background: '#1f2937', border: 'none', fontSize: 12 }}
                      formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Bankroll']}
                    />
                    <ReferenceLine
                      y={summary!.starting_bankroll}
                      stroke="#4b5563"
                      strokeDasharray="4 2"
                    />
                    <Line
                      type="monotone"
                      dataKey="bankroll"
                      stroke="#6366f1"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* By play type */}
            {(summary?.by_type?.length ?? 0) > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
                <p className="text-sm font-medium text-gray-300 mb-3">Results by play type</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {summary!.by_type.map(t => {
                    const tpl = t.payout - t.staked
                    return (
                      <div key={`${t.play_type}_${t.n_picks}`} className="bg-gray-800 rounded-lg p-3">
                        <p className="text-xs text-gray-500">{t.n_picks}-Pick {t.play_type === 'power' ? 'Power' : 'Flex'}</p>
                        <p className="text-sm font-semibold text-white mt-1">{t.wins}/{t.bets} wins</p>
                        <p className={`text-xs font-mono mt-0.5 ${tpl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {tpl >= 0 ? '+' : ''}${tpl.toFixed(2)}
                        </p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Pending bets */}
            {pending.length > 0 && (
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-800">
                  <p className="text-sm font-medium text-gray-300">Pending Bets ({pending.length})</p>
                </div>
                <BetsTable bets={pending} onCancel={handleCancel} />
              </div>
            )}

            {/* Settled history */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-800">
                <p className="text-sm font-medium text-gray-300">Bet History</p>
              </div>
              {settled.length === 0 ? (
                <p className="px-5 py-8 text-center text-gray-600 text-sm">
                  No settled bets yet. Place paper trades from the Optimal Parlays section.
                </p>
              ) : (
                <BetsTable bets={settled} />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function BetsTable({ bets, onCancel }: { bets: PaperBet[]; onCancel?: (id: number) => void }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-800/50">
          <tr>
            {['Date', 'Type', 'Stake', 'Max payout', 'Status', 'P&L', ''].map(h => (
              <th key={h} className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bets.map(b => (
            <BetRow key={b.id} bet={b} onCancel={onCancel ? () => onCancel(b.id) : undefined} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
