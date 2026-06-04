import { useEffect, useState } from 'react'

interface Props {
  message: string
  type: 'success' | 'error'
  onDismiss: () => void
}

export default function Toast({ message, type, onDismiss }: Props) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const show = setTimeout(() => setVisible(true), 10)
    return () => clearTimeout(show)
  }, [])

  const handleClose = () => {
    setVisible(false)
    setTimeout(onDismiss, 300)
  }

  const base = 'fixed bottom-6 right-6 z-50 flex items-start gap-3 px-5 py-4 rounded-xl shadow-2xl text-sm transition-all duration-300 max-w-sm'
  const styles = type === 'success'
    ? 'bg-emerald-900/95 border border-emerald-500/40 text-emerald-300'
    : 'bg-red-900/95 border border-red-500/40 text-red-300'
  const opacity = visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'

  return (
    <div className={`${base} ${styles} ${opacity}`}>
      <span className="mt-0.5 text-base shrink-0">{type === 'success' ? '✓' : '✕'}</span>
      <div className="flex-1 min-w-0">
        <p className="font-medium leading-snug">{message}</p>
      </div>
      <button
        onClick={handleClose}
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity text-lg leading-none mt-0.5"
      >
        ×
      </button>
    </div>
  )
}
