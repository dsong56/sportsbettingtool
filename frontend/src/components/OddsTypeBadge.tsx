import type { OddsType } from '../types'

interface Props {
  oddsType: OddsType
}

const CONFIG: Record<OddsType, { label: string; className: string }> = {
  demon:    { label: '👺 Demon',  className: 'bg-red-500/20 text-red-400 ring-1 ring-red-500/40' },
  goblin:   { label: '👹 Goblin', className: 'bg-green-500/20 text-green-400 ring-1 ring-green-500/40' },
  standard: { label: 'Standard',  className: 'bg-gray-700/50 text-gray-400 ring-1 ring-gray-600' },
}

export default function OddsTypeBadge({ oddsType }: Props) {
  const { label, className } = CONFIG[oddsType] ?? CONFIG.standard
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${className}`}>
      {label}
    </span>
  )
}
