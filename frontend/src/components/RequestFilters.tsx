import { useEffect, useId, useRef, useState } from 'react'

export const initialRequestFilters = { search: '', department: '', ordering: '-created_at' }
export type RequestFilterValues = typeof initialRequestFilters

export default function RequestFilters({ filters, onChange, refresh, loading, departments = true, disabled = false }: {
  filters: RequestFilterValues
  onChange: (filters: RequestFilterValues) => void
  refresh: () => void
  loading: boolean
  departments?: boolean
  disabled?: boolean
}) {
  const id = useId()
  const searchInput = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState(filters.search)
  useEffect(() => { setQuery(filters.search) }, [filters.search])
  const active = Boolean(query || filters.search || filters.department || filters.ordering !== '-created_at')
  return <form className="request-filters" aria-label="Find requests" onSubmit={(event) => {
    event.preventDefault()
    onChange({ ...filters, search: query.trim() })
  }}>
    <div className="form-field request-search"><label htmlFor={`${id}-search`}>Find a request</label><div className="search-input-group"><input ref={searchInput} id={`${id}-search`} type="search" placeholder="Title, request ID or description" value={query} disabled={disabled} onChange={(event) => setQuery(event.target.value)} /><button className="ghost-button" disabled={disabled}>Search</button></div></div>
    {departments && <div className="form-field"><label htmlFor={`${id}-department`}>Department</label><select id={`${id}-department`} value={filters.department} disabled={disabled} onChange={(event) => onChange({ ...filters, department: event.target.value })}><option value="">All departments</option>{['logistics', 'quality', 'production', 'maintenance', 'planning'].map((department) => <option key={department} value={department}>{department[0].toUpperCase() + department.slice(1)}</option>)}</select></div>}
    <div className="form-field"><label htmlFor={`${id}-order`}>Sort by</label><select id={`${id}-order`} value={filters.ordering} disabled={disabled} onChange={(event) => onChange({ ...filters, ordering: event.target.value })}><option value="-created_at">Newest first</option><option value="created_at">Oldest first</option><option value="-total_hours">Most employee-hours</option><option value="total_hours">Fewest employee-hours</option></select></div>
    <div className="inline-actions filter-actions">{active && <button className="ghost-button" type="button" disabled={disabled} onClick={() => { setQuery(''); onChange({ ...initialRequestFilters }); searchInput.current?.focus() }}>Clear filters</button>}<button className="ghost-button" type="button" disabled={disabled || loading} onClick={refresh}>Refresh</button></div>
  </form>
}
