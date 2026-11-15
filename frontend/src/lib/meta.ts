import { useQuery } from '@tanstack/react-query'
import { api, type Meta, type ParamSpec } from './api'

export function useMeta() {
  const q = useQuery({ queryKey: ['meta'], queryFn: api.meta, staleTime: Infinity })
  const specs: Record<string, ParamSpec> = {}
  q.data?.parameters.forEach(p => { specs[p.key] = p })
  return { meta: q.data as Meta | undefined, specs, loading: q.isLoading, error: q.error }
}

/** Fields of a distribution expressed in the parameter's own unit (scaled for display). */
export const SCALED_FIELDS = new Set(['mean', 'sd', 'low', 'high', 'mode', 'bound', 'values'])
