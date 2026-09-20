import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TopNav from '../components/layout/TopNav'
import AlertStrip from '../components/layout/AlertStrip'
import Sidebar from '../components/layout/Sidebar'
import Footer from '../components/layout/Footer'
import { useIoTSensors } from '../hooks/useIoTSensors'
import type { IoTSensor, SensorParameter } from '../api/hq'

// ── Types ─────────────────────────────────────────────────────────────────────

type StationId = 'maitri' | 'bharati'

// ── Category config (colours + icons) ────────────────────────────────────────

const CAT_META: Record<string, { color: string; bg: string; border: string; emoji: string }> = {
  temperature:    { color: '#dc2626', bg: '#fef2f2', border: '#fecaca', emoji: '🌡️' },
  pressure:       { color: '#7c3aed', bg: '#faf5ff', border: '#e9d5ff', emoji: '🔵' },
  fuel:           { color: '#ea580c', bg: '#fff7ed', border: '#fed7aa', emoji: '⛽' },
  seismic:        { color: '#92400e', bg: '#fefce8', border: '#fde68a', emoji: '🌍' },
  wildlife:       { color: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0', emoji: '🐧' },
  radiation:      { color: '#ca8a04', bg: '#fefce8', border: '#fef08a', emoji: '☀️' },
  meteorological: { color: '#0284c7', bg: '#f0f9ff', border: '#bae6fd', emoji: '🌬️' },
  structural:     { color: '#475569', bg: '#f8fafc', border: '#cbd5e1', emoji: '🏗️' },
  air_quality:    { color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc', emoji: '💨' },
  oceanographic:  { color: '#1d4ed8', bg: '#eff6ff', border: '#bfdbfe', emoji: '🌊' },
  fire_safety:    { color: '#b91c1c', bg: '#fef2f2', border: '#fecaca', emoji: '🔥' },
  communications: { color: '#6d28d9', bg: '#f5f3ff', border: '#ddd6fe', emoji: '📡' },
}

const DEFAULT_META = { color: '#64748b', bg: '#f8fafc', border: '#e2e8f0', emoji: '🔌' }

function getCatMeta(cat: string) {
  return CAT_META[cat] ?? DEFAULT_META
}

// ── Sensor Detail Modal ───────────────────────────────────────────────────────

function ParameterRow({ param }: { param: SensorParameter }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '7px 0',
        borderBottom: '1px solid #f1f5f9',
        fontSize: 11,
        gap: 12,
      }}
    >
      <div style={{ color: '#475569', fontWeight: 600, flexShrink: 0 }}>{param.label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ fontWeight: 900, color: '#0f172a', fontSize: 13 }}>
          {typeof param.value === 'number' ? param.value.toLocaleString() : param.value}
          {param.unit && (
            <span style={{ fontSize: 10, color: '#64748b', fontWeight: 600, marginLeft: 3 }}>
              {param.unit}
            </span>
          )}
        </span>
        <span style={{ fontSize: 9.5, color: '#94a3b8', background: '#f8fafc', border: '1px solid #e2e8f0', padding: '1px 6px', borderRadius: 2, whiteSpace: 'nowrap' }}>
          {param.normal_range}
        </span>
      </div>
    </div>
  )
}

function SensorDetailModal({
  sensor,
  onClose,
}: {
  sensor: IoTSensor
  onClose: () => void
}) {
  const meta = getCatMeta(sensor.category)
  const isOnline = sensor.state === 'online'
  const catLabel = sensor.category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(15, 23, 42, 0.72)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#ffffff',
          width: '100%',
          maxWidth: 520,
          border: `1px solid ${meta.border}`,
          borderTop: `5px solid ${meta.color}`,
          boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div style={{ padding: '14px 18px', borderBottom: `1px solid ${meta.border}`, background: meta.bg }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 22, color: meta.color }}>
                  {sensor.icon}
                </span>
                <span
                  style={{
                    fontSize: 9.5,
                    fontWeight: 800,
                    padding: '2px 8px',
                    background: meta.color,
                    color: '#ffffff',
                    borderRadius: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {catLabel}
                </span>
              </div>
              <div style={{ fontSize: 15, fontWeight: 900, color: '#0f172a', lineHeight: 1.3 }}>
                {sensor.name}
              </div>
              <div style={{ fontSize: 10, color: '#64748b', marginTop: 3 }}>
                📍 {sensor.location}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#64748b', padding: 0, lineHeight: 1 }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Sensor ID + State Banner */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '8px 18px',
            background: isOnline ? '#f0fdf4' : '#fef2f2',
            borderBottom: `1px solid ${isOnline ? '#bbf7d0' : '#fecaca'}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color: '#0369a1' }}>
              {sensor.sensor_id}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: isOnline ? '#16a34a' : '#dc2626',
                boxShadow: isOnline ? '0 0 6px #16a34a' : '0 0 6px #dc2626',
              }}
            />
            <span
              style={{
                fontSize: 11,
                fontWeight: 800,
                color: isOnline ? '#15803d' : '#b91c1c',
              }}
            >
              {isOnline ? 'ONLINE — Transmitting' : 'OFFLINE — No data received'}
            </span>
          </div>
        </div>

        {/* Parameters */}
        <div style={{ padding: '14px 18px' }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 800,
              color: '#64748b',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              marginBottom: 8,
            }}
          >
            Operational Parameters
          </div>
          {!isOnline && (
            <div
              style={{
                background: '#fef2f2',
                border: '1px solid #fecaca',
                padding: '8px 12px',
                marginBottom: 10,
                fontSize: 11,
                color: '#b91c1c',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>warning</span>
              Sensor offline — values shown are last known readings. Possible causes: blizzard event,
              power failure, or physical damage. Last contact unknown.
            </div>
          )}
          {sensor.parameters.map((p) => (
            <ParameterRow key={p.key} param={p} />
          ))}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '10px 18px',
            borderTop: '1px solid #e2e8f0',
            background: '#f8fafc',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontSize: 9.5, color: '#94a3b8' }}>
            Data source: hardcoded_v1 • Will link to live telemetry via Maitri/Bharati dashboards
          </span>
          <button
            onClick={onClose}
            style={{
              background: '#0b3b60',
              color: '#ffffff',
              border: 'none',
              padding: '5px 14px',
              fontSize: 10.5,
              fontWeight: 800,
              cursor: 'pointer',
              borderRadius: 2,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Sensor Card ───────────────────────────────────────────────────────────────

function SensorCard({ sensor, onClick }: { sensor: IoTSensor; onClick: () => void }) {
  const meta = getCatMeta(sensor.category)
  const isOnline = sensor.state === 'online'
  const catLabel = sensor.category.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      style={{
        background: '#ffffff',
        border: `1px solid ${meta.border}`,
        borderTop: `4px solid ${meta.color}`,
        padding: '12px 14px',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s, transform 0.1s',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        outline: 'none',
      }}
      onMouseOver={(e) => {
        const el = e.currentTarget as HTMLElement
        el.style.boxShadow = `0 4px 16px rgba(0,0,0,0.12)`
        el.style.transform = 'translateY(-2px)'
      }}
      onMouseOut={(e) => {
        const el = e.currentTarget as HTMLElement
        el.style.boxShadow = 'none'
        el.style.transform = 'translateY(0)'
      }}
    >
      {/* Category tag */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          style={{
            fontSize: 9,
            fontWeight: 800,
            padding: '1px 6px',
            background: meta.bg,
            color: meta.color,
            border: `1px solid ${meta.border}`,
            borderRadius: 2,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}
        >
          {meta.emoji} {catLabel}
        </span>
        {/* Online/Offline pill */}
        <span
          style={{
            fontSize: 9.5,
            fontWeight: 800,
            padding: '2px 8px',
            borderRadius: 10,
            background: isOnline ? '#dcfce7' : '#fee2e2',
            color: isOnline ? '#15803d' : '#b91c1c',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: isOnline ? '#16a34a' : '#dc2626',
              animation: isOnline ? 'pulse 2s infinite' : 'none',
            }}
          />
          {isOnline ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>

      {/* Icon + Name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            width: 36,
            height: 36,
            background: meta.bg,
            border: `1px solid ${meta.border}`,
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20, color: meta.color }}>
            {sensor.icon}
          </span>
        </div>
        <div>
          <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a', lineHeight: 1.35 }}>
            {sensor.name}
          </div>
          <div style={{ fontSize: 9.5, color: '#94a3b8', marginTop: 1 }}>
            📍 {sensor.location}
          </div>
        </div>
      </div>

      {/* Sensor ID */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 2 }}>
        <span style={{ fontFamily: 'monospace', fontSize: 9.5, color: '#0369a1', fontWeight: 700 }}>
          {sensor.sensor_id}
        </span>
        <span style={{ fontSize: 9.5, color: '#64748b', display: 'flex', alignItems: 'center', gap: 3 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 11 }}>info</span>
          Tap for details
        </span>
      </div>

      {/* Offline overlay warning */}
      {!isOnline && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(254, 242, 242, 0.45)',
            pointerEvents: 'none',
            borderTop: '4px solid #dc2626',
          }}
        />
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function InfrastructurePage() {
  const navigate = useNavigate()
  const [activeStation, setActiveStation] = useState<StationId>('maitri')
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedState, setSelectedState] = useState<'all' | 'online' | 'offline'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSensor, setSelectedSensor] = useState<IoTSensor | null>(null)

  const { data: sensorData, isLoading } = useIoTSensors(activeStation)

  const allSensors: IoTSensor[] = sensorData?.sensors ?? []
  const categories = sensorData?.categories ?? []
  const onlineCount = sensorData?.online ?? 0
  const offlineCount = sensorData?.offline ?? 0
  const totalCount = sensorData?.total ?? 0

  // Filtering
  const filtered = allSensors.filter((s) => {
    const catMatch = selectedCategory === 'all' || s.category === selectedCategory
    const stateMatch = selectedState === 'all' || s.state === selectedState
    const searchMatch =
      !searchQuery ||
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.sensor_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.location.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.category.toLowerCase().includes(searchQuery.toLowerCase())
    return catMatch && stateMatch && searchMatch
  })

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#f0f4f8' }}>
      <TopNav />
      <AlertStrip />

      {/* Pulse animation keyframes */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.5); }
          50% { opacity: 0.8; box-shadow: 0 0 0 4px rgba(22, 163, 74, 0); }
        }
      `}</style>

      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar
          activeStation={activeStation}
          onSwitchStation={() =>
            setActiveStation((s) => (s === 'maitri' ? 'bharati' : 'maitri'))
          }
        />

        <main
          id="main-content"
          style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#f0f4f8' }}
        >
          <div style={{ flex: 1, padding: '10px 14px' }}>

            {/* Breadcrumb */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: 11,
                color: '#64748b',
                marginBottom: 10,
                padding: '6px 12px',
                background: '#ffffff',
                border: '1px solid #cbd5e1',
                boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 15, color: '#0b3b60' }}>home</span>
                <button
                  onClick={() => navigate('/')}
                  style={{ background: 'none', border: 'none', color: '#0b3b60', fontWeight: 700, cursor: 'pointer', padding: 0, fontSize: 11 }}
                >
                  Home
                </button>
                <span>›</span>
                <span style={{ color: '#0b3b60', fontWeight: 600 }}>Polar Operations</span>
                <span>›</span>
                <span style={{ color: '#ea580c', fontWeight: 800 }}>IoT Sensor Telemetry Command</span>
              </div>
            </div>

            {/* Page Hero Banner */}
            <div
              style={{
                background: 'linear-gradient(135deg, #0b3b60 0%, #1e4d78 60%, #0b3b60 100%)',
                color: '#ffffff',
                padding: '14px 20px',
                marginBottom: 12,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 10,
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              {/* Decorative grid lines */}
              <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)', backgroundSize: '20px 20px', pointerEvents: 'none' }} />

              <div style={{ position: 'relative' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 28, color: '#ff9933' }}>sensors</span>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 900, letterSpacing: '0.02em' }}>
                      📡 ANTARCTIC IoT SENSOR TELEMETRY COMMAND
                    </div>
                    <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                      Real-time sensor monitoring for Maitri &amp; Bharati Research Stations • NCPOR / MoES
                    </div>
                  </div>
                </div>
              </div>

              {/* Station Switcher */}
              <div style={{ display: 'flex', gap: 8, position: 'relative' }}>
                {(['maitri', 'bharati'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setActiveStation(s)
                      setSelectedCategory('all')
                      setSelectedState('all')
                      setSearchQuery('')
                    }}
                    style={{
                      background: activeStation === s ? '#ff9933' : 'rgba(255,255,255,0.1)',
                      border: activeStation === s ? '2px solid #ff9933' : '2px solid rgba(255,255,255,0.25)',
                      color: '#ffffff',
                      padding: '7px 18px',
                      fontWeight: 900,
                      fontSize: 12,
                      cursor: 'pointer',
                      borderRadius: 3,
                      letterSpacing: '0.06em',
                      transition: 'all 0.15s',
                    }}
                  >
                    {s === 'maitri' ? '🏔️ MAITRI' : '🌊 BHARATI'}
                  </button>
                ))}
              </div>
            </div>

            {/* KPI Summary Row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10, marginBottom: 12 }}>
              {/* Total */}
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #0b3b60', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>TOTAL SENSORS</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#0b3b60' }}>sensors</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 900, color: '#0b3b60' }}>{totalCount}</div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                  {activeStation === 'maitri' ? 'Maitri Station' : 'Bharati Station'}
                </div>
              </div>

              {/* Online */}
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #16a34a', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>ONLINE</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#16a34a' }}>wifi</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 900, color: '#16a34a' }}>{onlineCount}</div>
                <div style={{ fontSize: 10, color: '#16a34a', fontWeight: 700, marginTop: 2 }}>
                  ● Transmitting data
                </div>
              </div>

              {/* Offline */}
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #dc2626', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>OFFLINE / ANOMALY</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#dc2626' }}>wifi_off</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 900, color: offlineCount > 0 ? '#dc2626' : '#16a34a' }}>
                  {offlineCount}
                </div>
                <div style={{ fontSize: 10, color: offlineCount > 0 ? '#dc2626' : '#16a34a', fontWeight: 700, marginTop: 2 }}>
                  {offlineCount > 0 ? '⚠️ Requires attention' : '✅ All sensors nominal'}
                </div>
              </div>

              {/* Network Health */}
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #0284c7', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>NETWORK HEALTH</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#0284c7' }}>health_and_safety</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 900, color: '#0284c7' }}>
                  {totalCount > 0 ? `${Math.round((onlineCount / totalCount) * 100)}%` : '—'}
                </div>
                <div style={{ fontSize: 10, color: '#0284c7', fontWeight: 700, marginTop: 2 }}>
                  Sensor uptime ratio
                </div>
              </div>

              {/* Categories */}
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #7c3aed', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>CATEGORIES</span>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#7c3aed' }}>category</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 900, color: '#7c3aed' }}>
                  {[...new Set(allSensors.map((s) => s.category))].length}
                </div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>Sensor domains</div>
              </div>
            </div>

            {/* Offline Alert Banner */}
            {offlineCount > 0 && (
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderLeft: '4px solid #dc2626',
                  padding: '8px 14px',
                  marginBottom: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 11,
                }}
              >
                <span className="material-symbols-outlined" style={{ color: '#dc2626', fontSize: 18, flexShrink: 0 }}>warning</span>
                <div>
                  <strong style={{ color: '#b91c1c' }}>
                    SENSOR OFFLINE ALERT: {offlineCount} sensor{offlineCount > 1 ? 's' : ''} not transmitting
                  </strong>
                  <span style={{ color: '#7f1d1d', marginLeft: 6 }}>
                    — Possible causes: blizzard event, power loss, or physical damage. Review offline sensors below.
                  </span>
                </div>
              </div>
            )}

            {/* Filter Bar */}
            <div
              style={{
                background: '#ffffff',
                border: '1px solid #cbd5e1',
                borderTop: '3px solid #0b3b60',
                padding: '12px 16px',
                marginBottom: 12,
                boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid #e2e8f0', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <h3 style={{ fontSize: 13, fontWeight: 900, color: '#0b3b60', margin: 0, textTransform: 'uppercase' }}>
                    IoT Sensor Registry — {activeStation === 'maitri' ? 'Maitri' : 'Bharati'} Station
                  </h3>
                  <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                    Click any sensor card to view operational parameters and real-time readings
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, background: '#e0f2fe', color: '#0369a1', padding: '2px 8px', border: '1px solid #bae6fd', borderRadius: 2 }}>
                    NCPOR Telemetry Network
                  </span>
                  <span style={{ fontSize: 9.5, fontWeight: 800, background: '#dcfce7', color: '#166534', padding: '2px 8px', border: '1px solid #86efac', borderRadius: 2 }}>
                    ● Live Dashboard Ready
                  </span>
                </div>
              </div>

              {/* Search + State Filter */}
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 220 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 17, color: '#64748b' }}>search</span>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by sensor name, ID, location, or category..."
                    style={{ flex: 1, border: '1px solid #cbd5e1', padding: '5px 10px', fontSize: 11, outline: 'none' }}
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 14 }}
                    >
                      ✕
                    </button>
                  )}
                </div>
                {/* State filter pills */}
                <div style={{ display: 'flex', gap: 6 }}>
                  {(['all', 'online', 'offline'] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setSelectedState(s)}
                      style={{
                        background: selectedState === s
                          ? s === 'online' ? '#16a34a' : s === 'offline' ? '#dc2626' : '#0b3b60'
                          : '#f1f5f9',
                        color: selectedState === s ? '#ffffff' : '#334155',
                        border: 'none',
                        padding: '4px 12px',
                        fontSize: 10.5,
                        fontWeight: 800,
                        cursor: 'pointer',
                        borderRadius: 3,
                        textTransform: 'uppercase',
                      }}
                    >
                      {s === 'all' ? `All (${totalCount})` : s === 'online' ? `🟢 Online (${onlineCount})` : `🔴 Offline (${offlineCount})`}
                    </button>
                  ))}
                </div>
              </div>

              {/* Category chips */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button
                  onClick={() => setSelectedCategory('all')}
                  style={{
                    background: selectedCategory === 'all' ? '#0b3b60' : '#f1f5f9',
                    color: selectedCategory === 'all' ? '#ffffff' : '#334155',
                    border: 'none',
                    padding: '4px 10px',
                    fontSize: 10,
                    fontWeight: 800,
                    cursor: 'pointer',
                    borderRadius: 3,
                  }}
                >
                  All Categories
                </button>
                {categories.map((cat) => {
                  const meta = getCatMeta(cat.key)
                  const count = allSensors.filter((s) => s.category === cat.key).length
                  return (
                    <button
                      key={cat.key}
                      onClick={() => setSelectedCategory(cat.key)}
                      style={{
                        background: selectedCategory === cat.key ? meta.color : meta.bg,
                        color: selectedCategory === cat.key ? '#ffffff' : meta.color,
                        border: `1px solid ${meta.border}`,
                        padding: '4px 10px',
                        fontSize: 10,
                        fontWeight: 700,
                        cursor: 'pointer',
                        borderRadius: 3,
                      }}
                    >
                      {meta.emoji} {cat.label} ({count})
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Sensor Cards Grid */}
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#64748b', fontSize: 13 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 32, display: 'block', marginBottom: 8, color: '#0b3b60' }}>
                  sensors
                </span>
                Loading sensor registry...
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', background: '#ffffff', border: '1px solid #cbd5e1', color: '#64748b', fontSize: 13 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 32, display: 'block', marginBottom: 8 }}>search_off</span>
                No sensors match your current filters.
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                  gap: 12,
                }}
              >
                {filtered.map((sensor) => (
                  <SensorCard
                    key={sensor.sensor_id}
                    sensor={sensor}
                    onClick={() => setSelectedSensor(sensor)}
                  />
                ))}
              </div>
            )}

            {/* Dashboard Link Note */}
            <div
              style={{
                marginTop: 14,
                background: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderLeft: '4px solid #0284c7',
                padding: '8px 14px',
                fontSize: 10.5,
                color: '#0369a1',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15, flexShrink: 0 }}>info</span>
              <span>
                <strong>Dashboard Integration:</strong> These sensor cards are designed to link to the Maitri and Bharati
                station dashboards once they are live. The <code style={{ background: '#e0f2fe', padding: '1px 4px', borderRadius: 2 }}>GET /api/v1/hq/iot/sensors</code> endpoint
                (filterable by <code style={{ background: '#e0f2fe', padding: '1px 4px', borderRadius: 2 }}>station_id</code>, <code style={{ background: '#e0f2fe', padding: '1px 4px', borderRadius: 2 }}>category</code>, and <code style={{ background: '#e0f2fe', padding: '1px 4px', borderRadius: 2 }}>state</code>) is ready
                for consumption by both dashboards.
              </span>
            </div>

          </div>

          {/* Sensor Detail Modal */}
          {selectedSensor && (
            <SensorDetailModal
              sensor={selectedSensor}
              onClose={() => setSelectedSensor(null)}
            />
          )}
        </main>
      </div>

      <Footer />
    </div>
  )
}
