import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  fetchPredictionsSummary, fetchUnresolvedPredictions, resolvePrediction, trainMlModel,
} from '../api'
import Toast from '../components/Toast'
import type { PredictionsSummary, UnresolvedPrediction } from '../types'

// Palette validated against the gray-950 surface (OKLCH band + CVD + contrast)
const COLOR_MARKET = '#6366f1'   // indigo — matches market signal elsewhere in the app
const COLOR_HISTORICAL = '#059669'
const COLOR_MOVEMENT = '#ea580c'
const COLOR_DIM = '#4b5563'      // buckets with too few samples
const GRID_COLOR = '#1f2937'
const TOOLTIP_STYLE = {
  backgroundColor: '#111827',
  border: '1px solid #374151',
  borderRadius: '0.5rem',
  fontSize: '0.75rem',
} as const
const AXIS_TICK = { fill: '#6b7280', fontSize: 11 } as const

const MIN_BUCKET_N = 10  // below this a calibration dot is dimmed as low-sample

function StatPill({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-3 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function ChartCard({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-sm font-medium text-gray-300">{title}</p>
      {sub && <p className="text-xs text-gray-600 mb-3">{sub}</p>}
      {children}
    </div>
  )
}

function CalibrationCurve({ summary }: { summary: PredictionsSummary }) {
  const data = summary.calibration_buckets.map(b => ({
    predicted: Math.round(b.predicted_avg * 1000) / 10,
    actual:    Math.round(b.actual_rate * 1000) / 10,
    count:     b.count,
  }))
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" />
          <XAxis
            type="number" dataKey="predicted" domain={[0, 100]} tickCount={6}
            tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: GRID_COLOR }}
            label={{ value: 'Predicted %', position: 'insideBottom', offset: -2, fill: '#6b7280', fontSize: 11 }}
          />
          <YAxis
            type="number" domain={[0, 100]} tickCount={6} width={40}
            tick={AXIS_TICK} tickLine={false} axisLine={false}
            label={{ value: 'Actual %', angle: -90, position: 'insideLeft', fill: '#6b7280', fontSize: 11 }}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#9ca3af' }}
                   itemStyle={{ color: '#e5e7eb' }} cursor={{ stroke: '#374151' }} />
          <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]}
                         stroke="#4b5563" strokeDasharray="4 4" />
          <Scatter name="Actual hit rate" dataKey="actual" fill={COLOR_MARKET} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.count >= MIN_BUCKET_N ? COLOR_MARKET : COLOR_DIM} />
            ))}
          </Scatter>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function RollingAccuracy({ summary }: { summary: PredictionsSummary }) {
  const data = summary.rolling_accuracy.map(p => ({
    date:     p.date,
    winRate:  Math.round(p.win_rate * 1000) / 10,
    count:    p.count,
  }))
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false}
                 axisLine={{ stroke: GRID_COLOR }} minTickGap={40} />
          <YAxis domain={[0, 100]} tickCount={6} width={40} tick={AXIS_TICK}
                 tickLine={false} axisLine={false}
                 tickFormatter={(v: number) => `${v}%`} />
          <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#9ca3af' }}
                   itemStyle={{ color: '#e5e7eb' }} />
          <ReferenceLine y={50} stroke="#4b5563" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="winRate" name="30-day win rate %"
                stroke={COLOR_MARKET} strokeWidth={2} dot={false} activeDot={{ r: 4 }}
                isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function SignalCorrelation({ summary }: { summary: PredictionsSummary }) {
  const a = summary.signal_attribution
  const data = [
    { name: 'Market',     r: a.market_correlation ?? 0,     n: a.market_n,     color: COLOR_MARKET,     missing: a.market_correlation === null },
    { name: 'Historical', r: a.historical_correlation ?? 0, n: a.historical_n, color: COLOR_HISTORICAL, missing: a.historical_correlation === null },
    { name: 'Steam',      r: a.movement_correlation ?? 0,   n: a.movement_n,   color: COLOR_MOVEMENT,   missing: a.movement_correlation === null },
  ].map(d => ({ ...d, label: d.missing ? 'n/a' : d.r.toFixed(3) }))

  return (
    <div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 16, bottom: 0, left: 0 }} barCategoryGap="30%">
            <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: GRID_COLOR }} />
            <YAxis width={44} tick={AXIS_TICK} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#9ca3af' }}
                     itemStyle={{ color: '#e5e7eb' }} cursor={{ fill: '#1f2937', opacity: 0.4 }} />
            <ReferenceLine y={0} stroke="#4b5563" />
            <Bar dataKey="r" name="Pearson r vs outcome" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.missing ? COLOR_DIM : d.color} />
              ))}
              <LabelList dataKey="label" position="top" fill="#9ca3af" fontSize={11} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 text-xs text-gray-600 mt-2 px-1">
        {data.map(d => (
          <span key={d.name} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: d.missing ? COLOR_DIM : d.color }} />
            {d.name}: n={d.n}
          </span>
        ))}
      </div>
    </div>
  )
}

function ResolutionTable({ toast }: { toast: (msg: string, type: 'success' | 'error') => void }) {
  const qc = useQueryClient()
  const [pendingId, setPendingId] = useState<number | null>(null)

  const { data: unresolved = [], isFetching } = useQuery<UnresolvedPrediction[]>({
    queryKey: ['predictions-unresolved'],
    queryFn: fetchUnresolvedPredictions,
    staleTime: 30_000,
  })

  const mutation = useMutation({
    mutationFn: ({ id, result }: { id: number; result: 'over' | 'under' }) =>
      resolvePrediction(id, result),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['predictions-unresolved'] })
      qc.invalidateQueries({ queryKey: ['predictions-summary'] })
      qc.invalidateQueries({ queryKey: ['bets'] })
    },
    onError: () => toast('Failed to resolve prediction', 'error'),
    onSettled: () => setPendingId(null),
  })

  const resolve = (id: number, result: 'over' | 'under') => {
    setPendingId(id)
    mutation.mutate({ id, result })
  }

  return (
    <div>
      <p className="text-sm font-medium text-gray-300 mb-1">
        Pending resolutions {isFetching && <span className="text-gray-600">· refreshing…</span>}
      </p>
      <p className="text-xs text-gray-600 mb-2">
        Past-dated predictions the nightly resolver couldn't settle automatically.
        Mark where the actual stat landed relative to the line.
      </p>
      <div className="w-full overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-900 border-b border-gray-800">
            <tr>
              {['Player', 'Prop', 'Pick', 'Game date', 'Predicted', 'Actual result'].map(h => (
                <th key={h} className="px-3 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {unresolved.map(p => (
              <tr key={p.id} className="hover:bg-gray-800/60 transition-colors">
                <td className="px-3 py-2.5">
                  <p className="font-medium text-gray-200">{p.player_name}</p>
                  <p className="text-xs text-gray-500">{p.sport}</p>
                </td>
                <td className="px-3 py-2.5 text-gray-400 whitespace-nowrap">
                  {p.line_score} {p.stat_type}
                </td>
                <td className="px-3 py-2.5">
                  <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                    p.direction === 'Over' ? 'bg-blue-500/20 text-blue-400' : 'bg-rose-500/20 text-rose-400'
                  }`}>
                    {p.direction}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-gray-400">{p.game_date ?? '—'}</td>
                <td className="px-3 py-2.5 font-mono text-gray-400">
                  {(p.predicted_prob * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => resolve(p.id, 'over')}
                      disabled={pendingId === p.id}
                      className="px-3 py-1 rounded-lg text-xs font-semibold bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 transition-colors disabled:opacity-50"
                    >
                      Over
                    </button>
                    <button
                      onClick={() => resolve(p.id, 'under')}
                      disabled={pendingId === p.id}
                      className="px-3 py-1 rounded-lg text-xs font-semibold bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 transition-colors disabled:opacity-50"
                    >
                      Under
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {unresolved.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-600 text-sm">
                  Nothing pending — all past predictions are resolved.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function Calibration() {
  const qc = useQueryClient()
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const { data: summary } = useQuery<PredictionsSummary>({
    queryKey: ['predictions-summary'],
    queryFn: fetchPredictionsSummary,
    staleTime: 30_000,
  })

  const trainMutation = useMutation({
    mutationFn: trainMlModel,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['predictions-summary'] })
      setToast({
        message: `Model trained on ${res.n_samples} predictions — holdout accuracy ${(res.accuracy * 100).toFixed(1)}%`,
        type: 'success',
      })
    },
    onError: (err: unknown) => {
      const detail = isAxiosError(err) && typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Training failed'
      setToast({ message: detail, type: 'error' })
    },
  })

  const canTrain = summary !== undefined && summary.total_resolved >= summary.ml.min_required

  return (
    <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white">Calibration</h1>
          {summary?.ml.active && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300">
              ML model active
            </span>
          )}
        </div>
        {canTrain && (
          <button
            onClick={() => trainMutation.mutate()}
            disabled={trainMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-purple-600 hover:bg-purple-500 text-white transition-colors disabled:opacity-60"
          >
            {trainMutation.isPending && (
              <span className="inline-block w-3.5 h-3.5 border-2 border-purple-300 border-t-white rounded-full animate-spin" />
            )}
            {trainMutation.isPending ? 'Training…' : summary?.ml.model_exists ? 'Retrain ML Model' : 'Train ML Model'}
          </button>
        )}
      </div>

      {/* Summary pills */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatPill label="Resolved predictions" value={String(summary?.total_resolved ?? 0)}
                  sub={summary && !canTrain ? `${summary.ml.min_required} needed for ML` : undefined} />
        <StatPill label="Win rate"
                  value={summary && summary.total_resolved > 0 ? `${(summary.win_rate * 100).toFixed(1)}%` : '—'} />
        <StatPill label="Brier score"
                  value={summary && summary.total_resolved > 0 ? summary.brier_score.toFixed(3) : '—'}
                  sub="lower is better · 0.25 = coin flip" />
        <StatPill label="ML model"
                  value={summary?.ml.active ? 'Active' : summary?.ml.model_exists ? 'Trained' : 'Off'}
                  sub={summary?.ml.active ? 'replacing blend' : 'weighted blend in use'} />
      </div>

      {summary && summary.total_resolved === 0 ? (
        <div className="text-center py-16 text-gray-600 space-y-3 bg-gray-900 border border-gray-800 rounded-xl">
          <p className="text-4xl">📈</p>
          <p className="text-lg font-medium text-gray-500">No resolved predictions yet</p>
          <p className="text-sm max-w-md mx-auto">
            Every scrape logs predictions; the nightly resolver settles them after games finish.
            Charts appear once outcomes accumulate.
          </p>
        </div>
      ) : summary ? (
        <>
          <div className="grid lg:grid-cols-2 gap-4">
            <ChartCard
              title="Calibration curve"
              sub={`Predicted probability vs. actual hit rate per 5% bucket — a calibrated model tracks the diagonal. Gray dots have n < ${MIN_BUCKET_N}.`}
            >
              <CalibrationCurve summary={summary} />
            </ChartCard>
            <ChartCard
              title="Signal attribution"
              sub="Pearson correlation of each signal with the actual outcome, computed over rows where the signal is present."
            >
              <SignalCorrelation summary={summary} />
            </ChartCard>
          </div>

          <ChartCard title="Rolling accuracy" sub="Win rate over the trailing 30 days, per game date. Dashed line = 50%.">
            <RollingAccuracy summary={summary} />
          </ChartCard>
        </>
      ) : null}

      <ResolutionTable toast={(message, type) => setToast({ message, type })} />

      {toast && <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />}
    </main>
  )
}
