import api from './client'

// ── Types ────────────────────────────────────────────────────────────────────

export interface StationStatus {
  station_id: string
  display_name: string
  link_state: 'UP' | 'DEGRADED' | 'DOWN'
  last_heartbeat_at: string | null
  queue_depth_bytes: number | null
  open_critical_alerts: number | null
  open_high_alerts: number | null
  services_healthy: boolean | null
  minutes_since_heartbeat: number | null
}

export interface DashboardSummaryOut {
  stations: StationStatus[]
  total_open_critical: number
  total_open_high: number
  total_open_alerts: number
  generated_at: string
}
export type DashboardData = DashboardSummaryOut

export interface AlertOut {
  alert_id: string
  station_id: string
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  domain: string
  asset_id: string | null
  triggered_at: string
  description: string
  ack_state: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
  acknowledged_by: string | null
  acknowledged_at: string | null
  resolved_at: string | null
  black_box_activated: boolean
  synced_to_cloud: boolean
  duration_open_s: number
}

export interface PaginatedAlerts {
  items: AlertOut[]
  total: number
  page: number
  page_size: number
}

export interface SensorSummary {
  station_id: string
  sensor_id: string
  domain: string
  latest_value: number | null
  latest_unit: string | null
  latest_ts: string | null
  readings_count_24h: number
}

export interface AnalyticsOut {
  station_id: string
  period_hours: number
  alert_counts_by_severity: Record<string, number>
  total_readings: number
  avg_readings_per_hour: number
  open_alerts_total: number
}

export interface InventoryItem {
  item_id: string
  station_id: string
  category: string
  name: string
  quantity: number
  unit: string
  min_safety_threshold: number | null
  daily_burn_rate: number | null
  days_remaining: number | null
  last_updated: string | null
  status: 'NOMINAL' | 'WARNING' | 'CRITICAL'
}

export interface AssetOut {
  asset_id: string
  station_id: string
  asset_type: string
  name: string
  latitude: number | null
  longitude: number | null
  elevation_m: number | null
  status: string
  commissioned_at: string | null
}

export interface ResupplyLineItem {
  line_item_id: string
  item_name: string
  quantity_delivered: number
  unit: string
}

export interface ResupplyManifest {
  manifest_id: string
  station_id: string
  expedition_name: string | null
  voyage_year: number
  ship_name: string | null
  departure_date: string | null
  arrival_window_start: string | null
  arrival_window_end: string | null
  status: 'PLANNED' | 'IN_TRANSIT' | 'DELIVERED'
  notes: string | null
  line_items: ResupplyLineItem[]
}

export interface AIPrediction {
  prediction_id: string
  station_id: string
  model_name: string
  target_metric: string
  predicted_value: number | null
  confidence_lower: number | null
  confidence_upper: number | null
  risk_level: string
  predicted_for_date: string | null
  generated_at: string
}

export interface HealthOut {
  status: string
  service?: string
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function getDashboard(): Promise<DashboardSummaryOut> {
  const { data } = await api.get<DashboardSummaryOut>('/hq/dashboard')
  return data
}

export async function getHealth(): Promise<HealthOut> {
  const { data } = await api.get<HealthOut>('/hq/health')
  return data
}

export async function getStations(): Promise<StationStatus[]> {
  const { data } = await api.get<StationStatus[]>('/hq/stations')
  return data
}

export async function getStationStatus(stationId: string): Promise<StationStatus> {
  const { data } = await api.get<StationStatus>(`/hq/stations/${stationId}/status`)
  return data
}

export async function getAlerts(params?: {
  station_id?: string
  ack_state?: string
  domain?: string
  severity?: string
  page?: number
  page_size?: number
}): Promise<PaginatedAlerts> {
  const { data } = await api.get<PaginatedAlerts>('/hq/alerts', { params })
  return data
}

export async function getAlert(alertId: string): Promise<AlertOut> {
  const { data } = await api.get<AlertOut>(`/hq/alerts/${alertId}`)
  return data
}

export async function acknowledgeAlert(alertId: string, note?: string): Promise<AlertOut> {
  const { data } = await api.patch<AlertOut>(`/hq/alerts/${alertId}/acknowledge`, {
    acknowledged_by: note ?? 'HQ Operator',
  })
  return data
}

export async function getSensors(
  stationId: string,
  domain?: string,
): Promise<SensorSummary[]> {
  const { data } = await api.get<SensorSummary[]>(
    `/hq/stations/${stationId}/sensors`,
    { params: domain ? { domain } : undefined },
  )
  return data
}

export async function getSensorHistory(
  stationId: string,
  sensorId: string,
  hours = 24,
): Promise<Array<{ timestamp_utc: string; value: number; unit: string; quality: string }>> {
  const { data } = await api.get(
    `/hq/stations/${stationId}/sensors/${encodeURIComponent(sensorId)}`,
    { params: { hours } },
  )
  return data
}

export async function getAnalytics(
  stationId: string,
  periodHours = 24,
): Promise<AnalyticsOut> {
  const { data } = await api.get<AnalyticsOut>(
    `/hq/stations/${stationId}/analytics`,
    { params: { hours: periodHours } },
  )
  return data
}

export async function getInventory(
  stationId: string,
  category?: string,
): Promise<InventoryItem[]> {
  const { data } = await api.get<InventoryItem[]>(
    `/hq/stations/${stationId}/inventory`,
    { params: category ? { category } : undefined },
  )
  return data
}

export async function getAssets(
  stationId: string,
  assetType?: string,
): Promise<AssetOut[]> {
  const { data } = await api.get<AssetOut[]>(
    `/hq/stations/${stationId}/assets`,
    { params: assetType ? { asset_type: assetType } : undefined },
  )
  return data
}

export async function getResupply(stationId?: string): Promise<ResupplyManifest[]> {
  const { data } = await api.get<ResupplyManifest[]>(
    '/hq/resupply',
    { params: stationId ? { station_id: stationId } : undefined },
  )
  return data
}

export async function getPredictions(stationId: string): Promise<AIPrediction[]> {
  const { data } = await api.get<AIPrediction[]>(
    `/hq/stations/${stationId}/predictions`,
  )
  return data
}

export async function getReportData(
  reportType: string,
  stationId?: string,
): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>('/hq/report', {
    params: { report_type: reportType, ...(stationId ? { station_id: stationId } : {}) },
  })
  return data
}

export async function downloadReportFile(
  reportType: string,
  stationId?: string,
): Promise<{ filename: string; content: string }> {
  const { data } = await api.get<{ filename: string; content: string }>(
    '/hq/report/download',
    { params: { report_type: reportType, ...(stationId ? { station_id: stationId } : {}) } },
  )
  return data
}

// ── Logistics Audit Summary ───────────────────────────────────────────────────

export interface AuditItemDetail {
  item_id: string
  name: string
  current_stock: number
  unit: string
  reorder_qty: number
  min_safe: number
  daily_use: string
  days_left: number
  status: 'SAFE' | 'WARNING' | 'CRITICAL'
}

export interface CategoryAudit {
  last_verified_by: string
  last_verified_at: string
  verified: boolean
  pending_maitri: boolean
  pending_bharati: boolean
}

export interface LogisticsCategoryData {
  total_items: number
  items: AuditItemDetail[]
  audit: CategoryAudit
}

export interface LogisticsAuditSummary {
  station_id: string
  categories: {
    food: LogisticsCategoryData
    fuel: LogisticsCategoryData
    medical: LogisticsCategoryData
    spares: LogisticsCategoryData
  }
  generated_at: string
  data_source: string
}

export async function getLogisticsAuditSummary(
  stationId: string,
): Promise<LogisticsAuditSummary> {
  const { data } = await api.get<LogisticsAuditSummary>(
    '/hq/logistics/audit-summary',
    { params: { station_id: stationId } },
  )
  return data
}

// ── IoT Sensor Registry ───────────────────────────────────────────────────────

export interface SensorParameter {
  key: string
  label: string
  value: number | string
  unit: string
  normal_range: string
}

export interface IoTSensor {
  sensor_id: string
  name: string
  category: string
  icon: string
  state: 'online' | 'offline'
  location: string
  parameters: SensorParameter[]
}

export interface IoTCategory {
  key: string
  label: string
  icon: string
}

export interface IoTSensorResponse {
  station_id: string
  sensors: IoTSensor[]
  total: number
  online: number
  offline: number
  categories: IoTCategory[]
  generated_at: string
  data_source: string
}

export async function getIoTSensors(
  stationId: string,
  category?: string,
  state?: string,
): Promise<IoTSensorResponse> {
  const { data } = await api.get<IoTSensorResponse>('/hq/iot/sensors', {
    params: {
      station_id: stationId,
      ...(category ? { category } : {}),
      ...(state ? { state } : {}),
    },
  })
  return data
}
