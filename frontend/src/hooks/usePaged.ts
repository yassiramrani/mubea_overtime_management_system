import { useEffect, useState } from 'react'
import api, { errorMessage } from '../services/api'

export function usePaged<T>(path: string, filters: Record<string, string> = {}) {
  const query = JSON.stringify(filters)
  const scope = `${path}:${query}`
  const [paging, setPaging] = useState({ scope, page: 1 })
  const page = paging.scope === scope ? paging.page : 1
  // Remember each transition, including a return to an earlier filter set.
  if (paging.scope !== scope) setPaging({ scope, page: 1 })
  const setPage = (value: number) => setPaging({ scope, page: Math.max(1, value) })
  const [revision, setRevision] = useState(0)
  const requestKey = `${scope}:${page}:${revision}`
  const [result, setResult] = useState({ key: '', items: [] as T[], count: 0, next: false, error: '' })
  const current = result.key === requestKey
  useEffect(() => {
    const controller = new AbortController()
    api.get(path, { params: { ...JSON.parse(query), page }, signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setResult({ key: requestKey, items: data.results, count: data.count, next: Boolean(data.next), error: '' })
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        if (err.response?.status === 404 && page > 1) { setPaging({ scope, page: page - 1 }); return }
        setResult({ key: requestKey, items: [], count: 0, next: false, error: errorMessage(err) })
      })
    return () => controller.abort()
  }, [path, query, scope, page, requestKey])
  return {
    items: current ? result.items : [], page, setPage,
    count: current ? result.count : 0, next: current && result.next,
    loading: !current, error: current ? result.error : '',
    reload: () => setRevision((value) => value + 1),
  }
}
