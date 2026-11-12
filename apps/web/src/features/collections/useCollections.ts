import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../../app/useAuth'
import type { CollectionItem } from '../../shared/api/types'

export function useCollections() {
  const { request, token } = useAuth()
  return useQuery({
    queryKey: ['collections', token],
    queryFn: () => request<{ items: CollectionItem[] }>('/collections').then((r) => r.items),
    enabled: !!token,
  })
}
