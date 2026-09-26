/**
 * QualityBadge — shows sensor data quality as a small coloured pill.
 *
 * NOMINAL  → green
 * SUSPECT  → yellow/amber
 * FAILED   → red
 */

interface Props {
  quality?: 'NOMINAL' | 'SUSPECT' | 'FAILED' | null
  size?: 'sm' | 'md'
}

const CONFIG = {
  NOMINAL: {
    label: 'NOMINAL',
    bg: '#dcfce7',
    color: '#15803d',
    border: '#bbf7d0',
    dot: '#16a34a',
  },
  SUSPECT: {
    label: 'SUSPECT',
    bg: '#fef9c3',
    color: '#a16207',
    border: '#fde68a',
    dot: '#ca8a04',
  },
  FAILED: {
    label: 'FAILED',
    bg: '#fee2e2',
    color: '#dc2626',
    border: '#fecaca',
    dot: '#ef4444',
  },
}

export default function QualityBadge({ quality, size = 'sm' }: Props) {
  if (!quality) return null

  const cfg = CONFIG[quality] ?? CONFIG.NOMINAL
  const fontSize = size === 'md' ? 10 : 9
  const padding = size === 'md' ? '2px 7px' : '1px 5px'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        fontSize,
        fontWeight: 800,
        letterSpacing: '0.04em',
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        borderRadius: 2,
        padding,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          background: cfg.dot,
          flexShrink: 0,
        }}
      />
      {cfg.label}
    </span>
  )
}
