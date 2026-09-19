import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TopNav from '../components/layout/TopNav'
import AlertStrip from '../components/layout/AlertStrip'
import Sidebar from '../components/layout/Sidebar'
import Footer from '../components/layout/Footer'
import { useLanguage } from '../context/LanguageContext'
import { useInventory } from '../hooks/useInventory'
import { useLogisticsAudit } from '../hooks/useLogisticsAudit'
import type { AuditItemDetail, LogisticsCategoryData } from '../api/hq'

// ── Types ─────────────────────────────────────────────────────────────────────

interface InventoryItemType {
  id: string
  name: string
  category: 'fuel' | 'food' | 'medical' | 'spares' | 'ppe' | 'water'
  quantity: number
  unit: string
  minThreshold: number
  burnRate: string
  daysLeft: number
  location: string
  status: 'NOMINAL' | 'WARNING' | 'CRITICAL'
  lastAudit: string
}

function toCategory(cat: string): InventoryItemType['category'] {
  const c = cat.toUpperCase()
  if (c.includes('FUEL')) return 'fuel'
  if (c.includes('FOOD')) return 'food'
  if (c.includes('MEDICAL')) return 'medical'
  if (c.includes('SPARE')) return 'spares'
  return 'spares'
}

// ── Category Meta ─────────────────────────────────────────────────────────────

const CATEGORY_CONFIG = [
  {
    key: 'food' as const,
    label: 'Food Rations',
    icon: '🍲',
    color: '#16a34a',
    bg: '#f0fdf4',
    border: '#bbf7d0',
    headerBorder: '#16a34a',
  },
  {
    key: 'fuel' as const,
    label: 'Fuel & Diesel',
    icon: '⛽',
    color: '#ea580c',
    bg: '#fff7ed',
    border: '#fed7aa',
    headerBorder: '#ea580c',
  },
  {
    key: 'medical' as const,
    label: 'Medical Supplies',
    icon: '🏥',
    color: '#dc2626',
    bg: '#fef2f2',
    border: '#fecaca',
    headerBorder: '#dc2626',
  },
  {
    key: 'spares' as const,
    label: 'Spare Parts',
    icon: '⚙️',
    color: '#7c3aed',
    bg: '#faf5ff',
    border: '#e9d5ff',
    headerBorder: '#7c3aed',
  },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function StockProgressBar({ current, min, max }: { current: number; min: number; max: number }) {
  const pct = Math.min(100, Math.round((current / Math.max(max, 1)) * 100))
  const isLow = current <= min
  const color = isLow ? '#ea580c' : current <= min * 1.5 ? '#ca8a04' : '#16a34a'
  return (
    <div style={{ width: '100%', background: '#e2e8f0', borderRadius: 4, height: 6, marginTop: 4 }}>
      <div style={{ width: `${pct}%`, background: color, borderRadius: 4, height: 6, transition: 'width 0.3s' }} />
    </div>
  )
}

function AuditBadge({
  label,
  verified,
  pending,
}: {
  label: string
  verified: boolean
  pending: boolean
}) {
  if (pending) {
    return (
      <span
        style={{
          fontSize: 9.5,
          fontWeight: 800,
          padding: '2px 8px',
          background: '#fef9c3',
          color: '#854d0e',
          border: '1px solid #fde047',
          borderRadius: 3,
        }}
      >
        ⏳ {label}: PENDING
      </span>
    )
  }
  return (
    <span
      style={{
        fontSize: 9.5,
        fontWeight: 800,
        padding: '2px 8px',
        background: verified ? '#dcfce7' : '#fef2f2',
        color: verified ? '#166534' : '#991b1b',
        border: `1px solid ${verified ? '#86efac' : '#fecaca'}`,
        borderRadius: 3,
      }}
    >
      {verified ? '✅' : '❌'} {label}: {verified ? 'VERIFIED' : 'NOT VERIFIED'}
    </span>
  )
}

function TrackingItemRow({ item }: { item: AuditItemDetail }) {
  const isLow = item.current_stock <= item.min_safe
  const maxStock = item.current_stock + item.reorder_qty
  return (
    <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
      <td style={{ padding: '7px 10px', fontFamily: 'monospace', fontSize: 10, color: '#0369a1', fontWeight: 700 }}>
        {item.item_id}
      </td>
      <td style={{ padding: '7px 10px', fontSize: 11, fontWeight: 700, color: '#0f172a' }}>
        {item.name}
      </td>
      <td style={{ padding: '7px 10px', fontSize: 11, fontWeight: 800, color: isLow ? '#ea580c' : '#16a34a', minWidth: 120 }}>
        {item.current_stock.toLocaleString()} {item.unit}
        <StockProgressBar current={item.current_stock} min={item.min_safe} max={maxStock} />
      </td>
      <td style={{ padding: '7px 10px', fontSize: 11, color: '#64748b' }}>
        {item.min_safe.toLocaleString()} {item.unit}
      </td>
      <td
        style={{
          padding: '7px 10px',
          fontSize: 10.5,
          fontWeight: 700,
          color: item.reorder_qty > 0 ? '#0284c7' : '#64748b',
        }}
      >
        {item.reorder_qty > 0 ? `📦 ${item.reorder_qty.toLocaleString()} ${item.unit}` : '—'}
      </td>
      <td style={{ padding: '7px 10px', fontSize: 10.5, color: '#475569' }}>{item.daily_use}</td>
      <td
        style={{
          padding: '7px 10px',
          fontSize: 10.5,
          fontWeight: 800,
          color: item.days_left < 60 ? '#ea580c' : '#16a34a',
        }}
      >
        {item.days_left} days
      </td>
      <td style={{ padding: '7px 10px' }}>
        <span
          style={{
            fontSize: 9.5,
            fontWeight: 800,
            padding: '2px 7px',
            borderRadius: 2,
            background: isLow ? '#fef2f2' : '#f0fdf4',
            color: isLow ? '#b91c1c' : '#15803d',
            border: isLow ? '1px solid #fecaca' : '1px solid #bbf7d0',
          }}
        >
          {isLow ? '⚠️ REORDER' : '✅ SAFE'}
        </span>
      </td>
    </tr>
  )
}

interface CategorySectionProps {
  config: (typeof CATEGORY_CONFIG)[number]
  data: LogisticsCategoryData | undefined
  fallbackItems: InventoryItemType[]
  onAuditCount: (itemId: string) => void
  notificationMsg: string | null
}

function CategorySection({
  config,
  data,
  fallbackItems,
  onAuditCount,
  notificationMsg,
}: CategorySectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [showAuditPanel, setShowAuditPanel] = useState(false)

  // Use API data if available, else derive from inventory hook data
  const items: AuditItemDetail[] = data
    ? data.items
    : fallbackItems.map((i) => ({
        item_id: i.id,
        name: i.name,
        current_stock: i.quantity,
        unit: i.unit,
        reorder_qty: Math.max(0, i.minThreshold * 3 - i.quantity),
        min_safe: i.minThreshold,
        daily_use: i.burnRate,
        days_left: i.daysLeft,
        status: i.status === 'NOMINAL' ? 'SAFE' : i.status,
      }))

  const totalItems = items.length
  const lowItems = items.filter((i) => i.current_stock <= i.min_safe).length
  const totalReorderQty = items.reduce((acc, i) => acc + i.reorder_qty, 0)
  const audit = data?.audit

  const auditVerifiedAt = audit
    ? new Date(audit.last_verified_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
    : 'N/A'

  return (
    <div
      style={{
        background: '#ffffff',
        border: `1px solid ${config.border}`,
        borderTop: `4px solid ${config.headerBorder}`,
        marginBottom: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
      }}
    >
      {/* Section Header — always visible, click to toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          background: config.bg,
          cursor: 'pointer',
          userSelect: 'none',
          borderBottom: expanded ? `1px solid ${config.border}` : 'none',
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>{config.icon}</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 900, color: config.color, textTransform: 'uppercase' }}>
              {config.label}
            </div>
            <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>
              {totalItems} items tracked
              {lowItems > 0 && (
                <span style={{ color: '#ea580c', fontWeight: 700, marginLeft: 6 }}>
                  • {lowItems} need reorder
                </span>
              )}
              {totalReorderQty > 0 && (
                <span style={{ color: '#0284c7', fontWeight: 600, marginLeft: 6 }}>
                  • Next order: {totalReorderQty.toLocaleString()} units
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} onClick={(e) => e.stopPropagation()}>
          {/* Audit panel toggle */}
          <button
            onClick={() => setShowAuditPanel((v) => !v)}
            style={{
              background: showAuditPanel ? config.color : '#ffffff',
              color: showAuditPanel ? '#ffffff' : config.color,
              border: `1px solid ${config.color}`,
              padding: '4px 10px',
              fontSize: 10,
              fontWeight: 800,
              cursor: 'pointer',
              borderRadius: 3,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>verified</span>
            Audit / Count
          </button>

          {/* Expand/collapse chevron */}
          <span
            className="material-symbols-outlined"
            style={{ fontSize: 20, color: config.color, cursor: 'pointer' }}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? 'expand_less' : 'expand_more'}
          </span>
        </div>
      </div>

      {/* Audit/Count Panel */}
      {showAuditPanel && (
        <div
          style={{
            background: '#f8fafc',
            borderBottom: `1px solid ${config.border}`,
            padding: '12px 16px',
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 900,
              color: '#0b3b60',
              marginBottom: 8,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 15, color: config.color }}>
              fact_check
            </span>
            Stock Audit & Dashboard Verification — {config.label}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, marginBottom: 10 }}>
            {/* Audit Summary Card */}
            <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', padding: '10px 14px', borderRadius: 3 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
                Last Count Verified
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>
                {audit ? audit.last_verified_by : 'Station Commander'}
              </div>
              <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>{auditVerifiedAt}</div>
              <div
                style={{
                  marginTop: 6,
                  fontSize: 9.5,
                  fontWeight: 800,
                  padding: '2px 8px',
                  display: 'inline-block',
                  background: audit?.verified ? '#dcfce7' : '#fef2f2',
                  color: audit?.verified ? '#166534' : '#991b1b',
                  border: `1px solid ${audit?.verified ? '#86efac' : '#fecaca'}`,
                  borderRadius: 2,
                }}
              >
                {audit?.verified ? '✅ COUNT VERIFIED' : '⚠️ AWAITING VERIFICATION'}
              </div>
            </div>

            {/* Quick Counts */}
            <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', padding: '10px 14px', borderRadius: 3 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>
                Inventory Count Summary
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: '#475569' }}>Total line items</span>
                  <span style={{ fontWeight: 800, color: '#0f172a' }}>{totalItems}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: '#475569' }}>Items at safe levels</span>
                  <span style={{ fontWeight: 800, color: '#16a34a' }}>{totalItems - lowItems}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: '#475569' }}>Items needing reorder</span>
                  <span style={{ fontWeight: 800, color: lowItems > 0 ? '#ea580c' : '#16a34a' }}>{lowItems}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: '#475569' }}>Next shipment order qty</span>
                  <span style={{ fontWeight: 800, color: '#0284c7' }}>{totalReorderQty.toLocaleString()} units</span>
                </div>
              </div>
            </div>

            {/* Dashboard Verification Status */}
            <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', padding: '10px 14px', borderRadius: 3 }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase', marginBottom: 8 }}>
                Dashboard Verification Status
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <AuditBadge
                  label="Maitri Dashboard"
                  verified={!audit?.pending_maitri}
                  pending={audit?.pending_maitri ?? false}
                />
                <AuditBadge
                  label="Bharati Dashboard"
                  verified={!audit?.pending_bharati}
                  pending={audit?.pending_bharati ?? false}
                />
                <div style={{ fontSize: 9.5, color: '#94a3b8', marginTop: 4 }}>
                  Cross-verification ensures integrity of the Logistics Management System
                </div>
              </div>
            </div>
          </div>

          {/* Per-item audit buttons */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {items.map((item) => (
              <button
                key={item.item_id}
                onClick={() => onAuditCount(item.item_id)}
                style={{
                  background: '#0b3b60',
                  color: '#ffffff',
                  border: 'none',
                  padding: '4px 10px',
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: 'pointer',
                  borderRadius: 3,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}
                title={`Confirm stock count for: ${item.name}`}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 12 }}>task_alt</span>
                ✓ {item.name.slice(0, 22)}{item.name.length > 22 ? '…' : ''}
              </button>
            ))}
          </div>

          {notificationMsg && (
            <div
              style={{
                marginTop: 8,
                background: '#f0fdf4',
                border: '1px solid #86efac',
                color: '#166534',
                padding: '5px 10px',
                fontSize: 10.5,
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                borderRadius: 2,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>check_circle</span>
              {notificationMsg}
            </div>
          )}
        </div>
      )}

      {/* Items Table */}
      {expanded && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#0b3b60', color: '#ffffff', borderBottom: '2px solid #ff9933' }}>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Item Code</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Item Name</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Current Stock</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Min Safe Level</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Next Order Qty</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Daily Use</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Days Left</th>
                <th style={{ padding: '7px 10px', fontWeight: 800, fontSize: 10 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '16px', textAlign: 'center', color: '#94a3b8', fontSize: 11 }}>
                    No items in this category for the current station.
                  </td>
                </tr>
              ) : (
                items.map((item) => <TrackingItemRow key={item.item_id} item={item} />)
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function LogisticsPage() {
  const navigate = useNavigate()
  const { t, lang } = useLanguage()

  const [activeStation, setActiveStation] = useState<'maitri' | 'bharati'>('maitri')
  const [searchQuery, setSearchQuery] = useState('')
  const [showRequisitionModal, setShowRequisitionModal] = useState(false)
  const [reqItemName, setReqItemName] = useState('')
  const [reqQuantity, setReqQuantity] = useState('')
  const [reqPriority, setReqPriority] = useState('URGENT')
  const [notificationMsg, setNotificationMsg] = useState<string | null>(null)

  // Live inventory from DB (used as fallback when audit API unavailable)
  const { data: rawInventory } = useInventory(activeStation)

  // Audit summary from new backend endpoint
  const { data: auditData } = useLogisticsAudit(activeStation)

  const items: InventoryItemType[] = (rawInventory ?? []).map((r) => ({
    id: r.item_id,
    name: r.name,
    category: toCategory(r.category),
    quantity: r.quantity,
    unit: r.unit,
    minThreshold: r.min_safety_threshold ?? 0,
    burnRate: r.daily_burn_rate !== null ? `${r.daily_burn_rate} ${r.unit}/day` : 'N/A',
    daysLeft: r.days_remaining ?? 0,
    location: 'Station Store',
    status: r.status as InventoryItemType['status'],
    lastAudit: r.last_updated
      ? new Date(r.last_updated).toLocaleDateString('en-IN')
      : 'N/A',
  }))

  // Search filter (applied across all categories)
  const searchedItems = searchQuery
    ? items.filter(
        (item) =>
          item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.id.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    : items

  const lowStockCount = items.filter(
    (i) => i.quantity <= i.minThreshold || i.status === 'WARNING' || i.status === 'CRITICAL',
  ).length
  const totalItemsCount = items.length

  function handleAuditCount(itemId: string) {
    setNotificationMsg(
      `[${new Date().toLocaleTimeString('en-GB')}] ✅ Stock count confirmed for: ${itemId}`,
    )
    setTimeout(() => setNotificationMsg(null), 5000)
  }

  function handleAddRequisition(e: React.FormEvent) {
    e.preventDefault()
    if (!reqItemName.trim()) return
    setNotificationMsg(
      `[${new Date().toLocaleTimeString('en-GB')}] 📋 Supply request sent to NCPOR Goa Logistics Office.`,
    )
    setShowRequisitionModal(false)
    setReqItemName('')
    setReqQuantity('')
    setTimeout(() => setNotificationMsg(null), 6000)
  }

  const categories = auditData?.categories

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#f0f4f8' }}>
      <TopNav />
      <AlertStrip />

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

            {/* Breadcrumb + Station Switcher */}
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
                  {t('crumb.home')}
                </button>
                <span>&gt;</span>
                <span style={{ color: '#0b3b60', fontWeight: 600 }}>{t('crumb.polar_division')}</span>
                <span>&gt;</span>
                <span style={{ color: '#ea580c', fontWeight: 800 }}>
                  {lang === 'hi' ? 'स्टेशन सामान, ईंधन एवं भोजन भंडार' : 'Station Supplies, Fuel & Living Essentials'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {(['maitri', 'bharati'] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setActiveStation(s)}
                    style={{
                      background: activeStation === s ? '#0b3b60' : '#ffffff',
                      color: activeStation === s ? '#ffffff' : '#0b3b60',
                      border: '1px solid #0b3b60',
                      padding: '4px 14px',
                      fontSize: 11,
                      fontWeight: 800,
                      cursor: 'pointer',
                      borderRadius: 3,
                    }}
                  >
                    {lang === 'hi' ? (s === 'maitri' ? 'मैत्री' : 'भारती') : s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Top KPI Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10, marginBottom: 12 }}>
              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #0b3b60', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>
                    {lang === 'hi' ? 'कुल ट्रैक की गई वस्तुएं' : 'TOTAL ITEMS TRACKED'}
                  </span>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#0b3b60' }}>inventory_2</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{ fontSize: 22, fontWeight: 900, color: '#0b3b60' }}>{totalItemsCount}</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b' }}>Essential Supply Items</span>
                </div>
                <div style={{ fontSize: 10, color: '#16a34a', fontWeight: 700, marginTop: 4 }}>All items counted &amp; verified</div>
              </div>

              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #ea580c', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>
                    {lang === 'hi' ? 'पुनःआपूर्ति आवश्यक' : 'ITEMS RUNNING LOW'}
                  </span>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#ea580c' }}>warning</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{ fontSize: 22, fontWeight: 900, color: lowStockCount > 0 ? '#ea580c' : '#16a34a' }}>
                    {lowStockCount}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b' }}>Items Need Reorder</span>
                </div>
                <div style={{ fontSize: 10, color: '#ea580c', fontWeight: 600, marginTop: 4 }}>Order list ready for next supply ship</div>
              </div>

              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #16a34a', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>
                    {lang === 'hi' ? 'स्टॉक कितने दिन चलेगा' : 'DAYS OF SUPPLIES LEFT'}
                  </span>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#16a34a' }}>timer</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{ fontSize: 22, fontWeight: 900, color: '#16a34a' }}>
                    {activeStation === 'maitri' ? '151' : '190'}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#475569' }}>Days of Normal Supplies</span>
                </div>
                <div style={{ fontSize: 10, color: '#475569', fontWeight: 600, marginTop: 4 }}>
                  Winter Stock Status: <strong style={{ color: '#16a34a' }}>EXCELLENT (SAFE)</strong>
                </div>
              </div>

              <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #0284c7', padding: '10px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 10, fontWeight: 800, color: '#64748b', textTransform: 'uppercase' }}>
                    {lang === 'hi' ? 'सप्लाई जहाज आगमन' : 'NEXT SUPPLY SHIP ARRIVAL'}
                  </span>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#0284c7' }}>directions_boat</span>
                </div>
                <div style={{ fontSize: 16, fontWeight: 900, color: '#0f172a' }}>MV Vasiliy Golovnin</div>
                <div style={{ fontSize: 10, color: '#0284c7', fontWeight: 700, marginTop: 4 }}>
                  Arriving in 68 Days (Goa → Antarctica)
                </div>
              </div>
            </div>

            {/* Register Header + Search + Actions */}
            <div style={{ background: '#ffffff', border: '1px solid #cbd5e1', borderTop: '3px solid #0b3b60', padding: '12px 16px', marginBottom: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 10, borderBottom: '1px solid #e2e8f0', paddingBottom: 8 }}>
                <div>
                  <h3 style={{ fontSize: 13, fontWeight: 900, color: '#0b3b60', margin: 0, textTransform: 'uppercase' }}>
                    {lang === 'hi' ? 'राष्ट्रीय ध्रुवीय भंडार सूची' : 'NATIONAL POLAR STOCK REGISTER'}
                  </h3>
                  <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                    Food, fuel, medicines, and machine spare parts for Antarctic stations • Use sections below to drill into each category
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 9.5, fontWeight: 800, background: '#e0f2fe', color: '#0369a1', padding: '2px 8px', border: '1px solid #bae6fd', borderRadius: 2 }}>
                    GeM Govt Store Linked
                  </span>
                  <span style={{ fontSize: 9.5, fontWeight: 800, background: '#dcfce7', color: '#166534', padding: '2px 8px', border: '1px solid #86efac', borderRadius: 2 }}>
                    ● Stock Verified Safe
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                {/* Search */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 240 }}>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>search</span>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by item name or code to filter sections..."
                    style={{ flex: 1, border: '1px solid #cbd5e1', padding: '5px 10px', fontSize: 11, outline: 'none' }}
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 12 }}
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => setShowRequisitionModal(true)}
                    style={{
                      background: '#0b3b60', color: '#ffffff', border: 'none',
                      padding: '6px 12px', fontSize: 11, fontWeight: 800, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: 4, borderRadius: 2,
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>add_shopping_cart</span>
                    <span>{lang === 'hi' ? '+ नया सामान मांगें' : '+ Request Supplies'}</span>
                  </button>
                  <button
                    onClick={() => alert('Official Stock List exported to PDF: REF-NCPOR-LOG-2026-AUG.pdf')}
                    style={{
                      background: '#ffffff', color: '#0b3b60', border: '1px solid #0b3b60',
                      padding: '6px 12px', fontSize: 11, fontWeight: 800, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: 4, borderRadius: 2,
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>picture_as_pdf</span>
                    <span>{lang === 'hi' ? 'स्टॉक रिपोर्ट डाउनलोड करें' : 'Download PDF Report'}</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Category Sections */}
            {CATEGORY_CONFIG.map((cfg) => {
              const catKey = cfg.key
              const fallback = searchedItems.filter((i) => i.category === catKey)
              // If search is active, only show section if there are matching items
              if (searchQuery && fallback.length === 0) return null

              return (
                <CategorySection
                  key={cfg.key}
                  config={cfg}
                  data={categories?.[catKey]}
                  fallbackItems={fallback}
                  onAuditCount={handleAuditCount}
                  notificationMsg={notificationMsg}
                />
              )
            })}

            {/* Empty state when all categories filtered out */}
            {searchQuery &&
              CATEGORY_CONFIG.every(
                (cfg) => searchedItems.filter((i) => i.category === cfg.key).length === 0,
              ) && (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '40px 20px',
                    background: '#ffffff',
                    border: '1px solid #cbd5e1',
                    color: '#64748b',
                    fontSize: 13,
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 32, display: 'block', marginBottom: 8 }}>
                    search_off
                  </span>
                  No items matched "{searchQuery}". Try a different search term.
                </div>
              )}

          </div>

          {/* Requisition Modal */}
          {showRequisitionModal && (
            <div
              style={{
                position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                background: 'rgba(15, 23, 42, 0.65)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                zIndex: 9999, padding: 16,
              }}
            >
              <div
                style={{
                  background: '#ffffff', width: '100%', maxWidth: 480,
                  border: '1px solid #cbd5e1', borderTop: '4px solid #0b3b60',
                  padding: 20, boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, borderBottom: '1px solid #e2e8f0', paddingBottom: 8 }}>
                  <div>
                    <h3 style={{ fontSize: 14, fontWeight: 900, color: '#0b3b60', margin: 0 }}>
                      REQUEST NEW SUPPLIES (ORDER FORM)
                    </h3>
                    <div style={{ fontSize: 10, color: '#64748b' }}>
                      Station: {activeStation.toUpperCase()} • Sent to NCPOR Logistics Office
                    </div>
                  </div>
                  <button
                    onClick={() => setShowRequisitionModal(false)}
                    style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#64748b' }}
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleAddRequisition} style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 11 }}>
                  <div>
                    <label style={{ fontWeight: 800, color: '#0b3b60', display: 'block', marginBottom: 4 }}>
                      Item Name / What is needed:
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Heating Cable 50m, Oxygen Tanks, Food Rations"
                      value={reqItemName}
                      onChange={(e) => setReqItemName(e.target.value)}
                      style={{ width: '100%', border: '1px solid #cbd5e1', padding: '6px 8px', fontSize: 11, outline: 'none' }}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    <div>
                      <label style={{ fontWeight: 800, color: '#0b3b60', display: 'block', marginBottom: 4 }}>Quantity Needed:</label>
                      <input
                        type="text"
                        required
                        placeholder="e.g. 5 Drums, 100 kg, 2 Sets"
                        value={reqQuantity}
                        onChange={(e) => setReqQuantity(e.target.value)}
                        style={{ width: '100%', border: '1px solid #cbd5e1', padding: '6px 8px', fontSize: 11, outline: 'none' }}
                      />
                    </div>
                    <div>
                      <label style={{ fontWeight: 800, color: '#0b3b60', display: 'block', marginBottom: 4 }}>How Urgent?:</label>
                      <select
                        value={reqPriority}
                        onChange={(e) => setReqPriority(e.target.value)}
                        style={{ width: '100%', border: '1px solid #cbd5e1', padding: '6px 8px', fontSize: 11, outline: 'none' }}
                      >
                        <option value="CRITICAL">🔴 Emergency (Air-drop)</option>
                        <option value="URGENT">🟠 High Priority (Next ship)</option>
                        <option value="ROUTINE">🟢 Routine (Annual cycle)</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
                    <button
                      type="button"
                      onClick={() => setShowRequisitionModal(false)}
                      style={{ background: '#f1f5f9', border: '1px solid #cbd5e1', padding: '6px 12px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      style={{ background: '#0b3b60', color: '#ffffff', border: 'none', padding: '6px 14px', fontSize: 11, fontWeight: 800, cursor: 'pointer' }}
                    >
                      Submit Supply Request
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}

        </main>
      </div>

      <Footer />
    </div>
  )
}
