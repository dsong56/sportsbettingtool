import type { PropResult } from '../types'

interface Props {
  prop: PropResult
}

function countAgreements(prop: PropResult): number {
  const { direction, market_prob, historical_prob, movement_signal } = prop
  const isOver = direction === 'Over'
  let count = 0
  if (isOver ? market_prob > 0.5 : market_prob < 0.5) count++
  if (isOver ? historical_prob > 0.5 : historical_prob < 0.5) count++
  // movement_signal > 0 = steam toward Over; ignore near-zero (neutral)
  if (Math.abs(movement_signal) > 0.05) {
    if (isOver ? movement_signal > 0 : movement_signal < 0) count++
  }
  return count
}

export default function SignalBadge({ prop }: Props) {
  const agreements = countAgreements(prop)
  const hasMovement = Math.abs(prop.movement_signal) > 0.05
  const total = hasMovement ? 3 : 2

  if (agreements === total && total === 3) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/40">
        ⚡ All agree
      </span>
    )
  }
  if (agreements >= 2) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-yellow-500/20 text-yellow-400 ring-1 ring-yellow-500/40">
        2/{total} agree
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-700/50 text-gray-400 ring-1 ring-gray-600">
      Split
    </span>
  )
}
