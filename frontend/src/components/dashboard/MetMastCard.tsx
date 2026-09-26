import { useSensors } from '../../hooks/useSensors'
import { useLanguage } from '../../context/LanguageContext'
import type { SensorSummary } from '../../api/hq'
import QualityBadge from '../ui/QualityBadge'

interface Props { stationId: string }

function find(sensors: SensorSummary[] | undefined, key: string) {
  return sensors?.find(s => s.sensor_id.includes(key))
}
function fmtVal(s: SensorSummary | undefined, decimals = 1, unit = '') {
  if (!s || s.latest_value == null) return '---'
  return `${s.latest_value.toFixed(decimals)} ${unit}`.trim()
}

export default function MetMastCard({ stationId }: Props) {
  const { data: sensors } = useSensors(stationId, 'weather')
  const { t } = useLanguage()

  const windSpd = find(sensors, 'wind_speed')
  const windDir = find(sensors, 'wind_dir')
  const pressure = find(sensors, 'pressure')
  const solarRad = find(sensors, 'solar_rad')

  const metrics = [
    {
      icon: 'air',
      label: t('met.wind_speed'),
      value: fmtVal(windSpd, 1, 'km/h'),
      sub: (windSpd?.latest_value ?? 0) > 30 ? 'Strong Breeze' : 'Moderate',
      color: (windSpd?.latest_value ?? 0) > 30 ? '#ea580c' : '#0b3b60',
      quality: windSpd?.quality,
    },
    {
      icon: 'explore',
      label: t('met.direction'),
      value: fmtVal(windDir, 0, '°'),
      sub: '247° WSW Azimuth',
      color: '#0b3b60',
      quality: windDir?.quality,
    },
    {
      icon: 'speed',
      label: t('met.pressure'),
      value: fmtVal(pressure, 0, 'hPa'),
      sub: 'Normal Barometric',
      color: '#0b3b60',
      quality: pressure?.quality,
    },
    {
      icon: 'wb_sunny',
      label: t('met.solar_rad'),
      value: fmtVal(solarRad, 0, 'W/m²'),
      sub: 'Polar Daylight Flux',
      color: '#0b3b60',
      quality: solarRad?.quality,
    },
  ]

  return (
    <div
      style={{
        width: '100%',
        background: '#ffffff',
        border: '1px solid #cbd5e1',
        boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.06)',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 185,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Official Header Strip */}
      <div
        style={{
          background: '#0b3b60',
          borderBottom: '2px solid #ff9933',
          padding: '6px 12px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          position: 'relative',
          zIndex: 3,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#ff9933' }}>
            cell_tower
          </span>
          <span style={{ fontSize: 11.5, fontWeight: 800, color: '#ffffff', letterSpacing: '0.04em' }}>
            {t('met.title')} (10M)
          </span>
        </div>
        <span
          style={{
            fontSize: 8.5,
            color: '#ffedd5',
            background: 'rgba(255, 153, 51, 0.25)',
            border: '1px solid rgba(255, 153, 51, 0.5)',
            padding: '1px 6px',
            fontWeight: 800,
            borderRadius: 2,
          }}
        >
          IMD-AWS-01
        </span>
      </div>

      {/* Sensor Grid */}
      <div style={{ flex: 1, padding: '10px 12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, background: '#f8fafc' }}>
        {metrics.map(({ icon, label, value, sub, color, quality }) => (
          <div
            key={label}
            style={{
              background: '#ffffff',
              border: `1px solid ${quality === 'FAILED' ? '#fecaca' : quality === 'SUSPECT' ? '#fde68a' : '#e2e8f0'}`,
              padding: '7px 10px',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
              <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.04em', color: '#64748b' }}>
                {label}
              </span>
              <span className="material-symbols-outlined" style={{ fontSize: 13, color: '#94a3b8' }}>
                {icon}
              </span>
            </div>
            <div style={{ fontSize: 15, fontWeight: 800, color, fontFamily: 'Inter', letterSpacing: '-0.01em' }}>
              {value}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
              <div style={{ fontSize: 8.5, fontWeight: 600, color: '#64748b' }}>{sub}</div>
              <QualityBadge quality={quality} size="sm" />
            </div>
          </div>
        ))}
      </div>

      {/* Official Calibration Strip */}
      <div
        style={{
          background: '#f1f5f9',
          borderTop: '1px solid #e2e8f0',
          padding: '4px 10px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: 8.5,
          color: '#475569',
        }}
      >
        <span>● Sensor Calibrated • 10m Tower</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {[windSpd, windDir, pressure, solarRad].some(s => s?.quality === 'FAILED') && (
            <QualityBadge quality="FAILED" size="sm" />
          )}
          {[windSpd, windDir, pressure, solarRad].some(s => s?.quality === 'SUSPECT') && (
            <QualityBadge quality="SUSPECT" size="sm" />
          )}
          {[windSpd, windDir, pressure, solarRad].every(s => !s || s?.quality === 'NOMINAL') && (
            <QualityBadge quality="NOMINAL" size="sm" />
          )}
          <span style={{ color: '#15803d', fontWeight: 700 }}>✓ IMD Certified</span>
        </div>
      </div>
    </div>
  )
}
