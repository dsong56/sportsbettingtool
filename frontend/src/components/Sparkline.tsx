import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, Tooltip, ResponsiveContainer } from 'recharts'
import { fetchOddsHistory } from '../api'
import type { PropResult } from '../types'

interface Props {
  prop: PropResult
}

export default function Sparkline({ prop }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['history', prop.player_name, prop.stat_type, prop.line_score, prop.sport, prop.direction],
    queryFn: () => fetchOddsHistory({
      player_name: prop.player_name,
      stat_type:   prop.stat_type,
      line_score:  prop.line_score,
      sport:       prop.sport as any,
      direction:   prop.direction,
    }),
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <div className="h-10 w-24 bg-gray-800 animate-pulse rounded" />
  if (!data || data.length < 2) {
    return <span className="text-xs text-gray-600">no history</span>
  }

  const first = data[0].avg_odds
  const last  = data[data.length - 1].avg_odds
  const moved = last - first
  const color = moved < 0 ? '#34d399' : moved > 0 ? '#f87171' : '#6b7280'
  // Negative odds movement = odds shortened = more confident → good (green)

  return (
    <div className="flex items-center gap-1.5">
      <ResponsiveContainer width={80} height={32}>
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="avg_odds"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
          />
          <Tooltip
            contentStyle={{ background: '#1f2937', border: 'none', fontSize: 11 }}
            labelStyle={{ display: 'none' }}
            formatter={(v) => [typeof v === 'number' && v > 0 ? `+${v}` : v, '']}
          />
        </LineChart>
      </ResponsiveContainer>
      <span className="text-xs font-mono" style={{ color }}>
        {moved > 0 ? '+' : ''}{moved.toFixed(0)}
      </span>
    </div>
  )
}
