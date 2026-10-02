import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'react-toastify'
import { useAuth } from '../context/AuthContext'
import api, { errorMessage } from '../services/api'
import type { OvertimeRequest } from '../types'

const roleLabels: Record<string, string> = {
  dept_manager: 'Department manager',
  head_manager: 'Head manager',
  hr_manager: 'HR manager',
  admin: 'Administrator',
}

const departmentLabels: Record<string, string> = {
  logistics: 'Logistics', quality: 'Quality', production: 'Production', maintenance: 'Maintenance', planning: 'Planning',
}

export function Header({ title, description }: { title: string; description: string }) {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const signOut = async () => {
    setBusy(true)
    try { await logout() } catch (error) { toast.error(errorMessage(error, 'Unable to sign out. Please try again.')) }
    finally { setBusy(false) }
  }
  const role = user?.profile?.role || ''
  const department = user?.profile?.department
  return <header className="dashboard-header"><div><div className="workspace-marker" aria-label="Current workspace"><span className="workspace-badge">{roleLabels[role] || 'Workspace'}</span>{department && <span>Department: {departmentLabels[department] || department}</span>}</div><h1>{title}</h1><p className="muted">{description}</p></div><div className="inline-actions">{role === 'admin' && <nav aria-label="Workspaces"><Link to="/head-manager">Approvals</Link> <Link to="/hr-manager">HR exports</Link></nav>}<button className="ghost-button" disabled={busy} onClick={signOut}>{busy ? 'Signing out…' : 'Sign out'}</button></div></header>
}

export function Pagination({ page, count, next, loading, onPage }: { page: number; count: number; next: boolean; loading: boolean; onPage: (page: number) => void }) {
  return <nav className="pagination" aria-label="Pagination"><span>{count} {count === 1 ? 'record' : 'records'} · Page {page}</span><div className="inline-actions"><button className="ghost-button" disabled={page === 1 || loading} onClick={() => onPage(page - 1)}>Previous</button><button className="ghost-button" disabled={!next || loading} onClick={() => onPage(page + 1)}>Next</button></div></nav>
}

export function LoadError({ error, retry }: { error: string; retry: () => void }) {
  return <div className="error-notice" role="alert"><p>{error}</p><button className="ghost-button" onClick={retry}>Try again</button></div>
}

interface Event { id: number; actor_name: string; action: string; created_at: string; details: { reason?: string } }
export function RequestDetails({ item }: { item: OvertimeRequest }) {
  const [events, setEvents] = useState<Event[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = async () => {
    setBusy(true); setError('')
    try { setEvents((await api.get<Event[]>(`/requests/${item.id}/history/`)).data) }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  return <details className="request-details"><summary>Request details and history</summary><dl><dt>Work description</dt><dd>{item.description}</dd><dt>Justification</dt><dd>{item.reason}</dd><dt>Dates</dt><dd>{item.start_date} to {item.end_date}</dd><dt>Estimated cost</dt><dd>{item.estimated_cost ?? 'Not provided'}{item.hourly_rate !== null && ` (${item.hourly_rate} per employee-hour)`}</dd><dt>Employee selection</dt><dd>{item.requires_employee_assignment ? 'Names required before export' : 'Department authorization; names optional'}</dd>{item.rejection_reason && <><dt>Rejection reason</dt><dd>{item.rejection_reason}</dd></>}{item.approval_date && <><dt>Approved by</dt><dd>{item.approved_by_name || 'Head manager'} · {new Date(item.approval_date).toLocaleString()}</dd></>}<dt>Assigned employees</dt><dd>{item.assignment?.employees.map((employee) => employee.name).join(', ') || 'No employees assigned'}</dd>{item.assignment?.notes && <><dt>HR notes</dt><dd>{item.assignment.notes}</dd></>}</dl><button className="ghost-button" disabled={busy} onClick={load}>{busy ? 'Loading history…' : 'Load activity history'}</button>{error && <p role="alert">{error}</p>}{events && <ol className="activity-list">{events.length === 0 && <li>No recorded activity. This may be a legacy request.</li>}{events.map((event) => <li key={event.id}><strong>{event.action.replace(/_/g, ' ')}</strong> · {event.actor_name} · {new Date(event.created_at).toLocaleString()}{event.details.reason && <p>{event.details.reason}</p>}</li>)}</ol>}</details>
}
