import { useQuery } from '@tanstack/react-query'
import { getLogisticsAuditSummary } from '../api/hq'

export function useLogisticsAudit(stationId: string) {
  return useQuery({
    queryKey: ['logistics-audit', stationId],
    queryFn: () => getLogisticsAuditSummary(stationId),
    refetchInterval: 120_000,
    enabled: Boolean(stationId),
    retry: false,         // graceful fallback if backend not yet deployed
  })
}
