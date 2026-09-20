import { useQuery } from '@tanstack/react-query'
import { getIoTSensors } from '../api/hq'

export function useIoTSensors(stationId: string, category?: string, state?: string) {
  return useQuery({
    queryKey: ['iot-sensors', stationId, category, state],
    queryFn: () => getIoTSensors(stationId, category, state),
    refetchInterval: 90_000,
    enabled: Boolean(stationId),
    retry: false,
  })
}
