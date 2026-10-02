import { useRef, useState } from 'react'
import { toast } from 'react-toastify'
import api, { errorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { usePaged } from '../hooks/usePaged'
import { Header, Pagination, LoadError, RequestDetails } from '../components/Workflow'
import type { OvertimeRequest } from '../types'
import RequestFilters, { initialRequestFilters } from '../components/RequestFilters'
import { estimatedTotal } from '../services/estimate'

const emptyForm = { title: '', description: '', reason: '', start_date: '', end_date: '', total_hours: '', hourly_rate: '', requires_employee_assignment: true }
export default function DepartmentManagerDashboard() {
  const { user } = useAuth()
  const [status, setStatus] = useState('')
  const [filters, setFilters] = useState(initialRequestFilters)
  const queue = usePaged<OvertimeRequest>('/requests/', { ...filters, status })
  const [showForm, setShowForm] = useState(false)
  const newRequestButton = useRef<HTMLButtonElement>(null)
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [withdrawId, setWithdrawId] = useState<number | null>(null)
  const [withdrawReason, setWithdrawReason] = useState('')
  const estimate = estimatedTotal(form.total_hours, form.hourly_rate)
  const closeForm = () => { setShowForm(false); newRequestButton.current?.focus() }
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      await api.post('/requests/', { ...form, department: user?.profile?.department, total_hours: form.total_hours, hourly_rate: form.hourly_rate || null })
      setForm(emptyForm); setShowForm(false); setStatus(''); setFilters(initialRequestFilters); queue.setPage(1); queue.reload()
      requestAnimationFrame(() => newRequestButton.current?.focus())
      toast.success('Request submitted. Approval notification queued.')
    } catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  const withdraw = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true)
    try { await api.post(`/requests/${withdrawId}/withdraw/`, { reason: withdrawReason }); setWithdrawId(null); queue.reload(); toast.success('Request withdrawn. Its history is preserved.') }
    catch (err) { toast.error(errorMessage(err)) }
    finally { setBusy(false) }
  }
  const departmentName = user?.profile?.department ? user.profile.department[0].toUpperCase() + user.profile.department.slice(1) : 'Your department'
  return <main className="dashboard-shell dashboard-dept"><Header title={`Plan overtime for ${departmentName}`} description="Submit and track advance overtime authorizations for your department." />
    <div className="toolbar"><p>Request the total employee-hours your department needs.</p><button ref={newRequestButton} className="primary-button" disabled={busy} aria-expanded={showForm} aria-controls="new-request-panel" onClick={() => { setShowForm(!showForm); setError('') }}>{showForm ? 'Close request form' : 'New overtime request'}</button></div>
    {showForm && <section className="request-form-panel" id="new-request-panel"><h2>New overtime request</h2><p className="muted form-intro">Five employees working three hours each means 15 employee-hours. This is an advance authorization, not a record of hours already worked.</p><form onSubmit={submit} aria-busy={busy}><fieldset className="request-form" disabled={busy}><legend className="sr-only">Overtime request details</legend>
      <div className="form-field full-width"><label htmlFor="title">Request title</label><input id="title" autoFocus required maxLength={200} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></div>
      <div className="form-field"><label htmlFor="start_date">Start date</label><input id="start_date" type="date" required value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} /></div>
      <div className="form-field"><label htmlFor="end_date">End date</label><input id="end_date" type="date" required min={form.start_date} value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} /></div>
      <div className="form-field"><label htmlFor="total_hours">Total employee-hours</label><input id="total_hours" type="number" required min="0.5" max="999.99" step="0.01" value={form.total_hours} onChange={(event) => setForm({ ...form, total_hours: event.target.value })} /></div>
      <div className="form-field"><label htmlFor="hourly_rate">Estimated rate per employee-hour (optional)</label><input id="hourly_rate" type="number" min="0" max="99999999.99" step="0.01" value={form.hourly_rate} onChange={(event) => setForm({ ...form, hourly_rate: event.target.value })} /></div>
      <div className="form-field full-width"><label htmlFor="description">Work description</label><textarea id="description" required rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></div>
      <div className="form-field full-width"><label htmlFor="reason">Why is overtime needed?</label><textarea id="reason" required rows={3} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} /></div>
      <label className="checkbox-control full-width"><input type="checkbox" checked={form.requires_employee_assignment} onChange={(event) => setForm({ ...form, requires_employee_assignment: event.target.checked })} />Require HR to select named employees before export</label>
      <div className="form-summary full-width" role="status"><strong>Request estimate</strong><span>{form.total_hours ? `${Number(form.total_hours).toLocaleString()} employee-hours` : 'Enter total employee-hours'}{estimate !== null && ` · Estimated total: ${Number(estimate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}</span><small>{form.requires_employee_assignment ? 'After approval, HR must select employees before exporting.' : 'After approval, HR can export this department authorization without names.'}</small></div>
      {error && <p className="error-notice full-width" role="alert">{error}</p>}
      <div className="form-actions full-width"><button type="button" className="ghost-button" disabled={busy} onClick={closeForm}>Close</button><button className="primary-button" disabled={busy}>{busy ? 'Submitting…' : 'Submit for approval'}</button></div>
    </fieldset></form></section>}
    <section className="history-panel"><div className="section-heading"><h2>Your requests</h2><label className="filter-control">Status<select value={status} onChange={(event) => { setStatus(event.target.value); queue.setPage(1) }}><option value="">All requests</option>{['pending', 'approved', 'rejected', 'withdrawn'].map((value) => <option key={value} value={value}>{value}</option>)}</select></label></div>
      <RequestFilters filters={filters} onChange={setFilters} refresh={queue.reload} loading={queue.loading} departments={false} disabled={busy} />
      {queue.error ? <LoadError error={queue.error} retry={queue.reload} /> : queue.loading ? <p role="status">Loading requests…</p> : queue.items.length === 0 ? <p className="empty-state">No requests match your filters. Clear the filters or use “New overtime request” to submit a plan.</p> : queue.items.map((item) => <article className="request-row" key={item.id}><div className="request-row-heading"><div><h3>{item.title}</h3><p className="muted">{item.request_id}</p></div><span className={`status-label status-${item.status}`}>{item.status}</span></div><p><strong>{item.total_hours} employee-hours</strong> · {item.start_date} to {item.end_date}</p>{item.rejection_reason && <p><strong>Rejection reason:</strong> {item.rejection_reason}</p>}{item.assignment && <p><strong>Assigned employees:</strong> {item.assignment.employees.map((employee) => employee.name).join(', ')}</p>}<RequestDetails item={item} />
      {item.status === 'pending' && <><button className="ghost-button" disabled={busy} onClick={() => { setWithdrawId(item.id); setWithdrawReason('') }}>Withdraw request</button>{withdrawId === item.id && <form className="inline-form" onSubmit={withdraw}><label htmlFor={`withdraw-${item.id}`}>Reason for withdrawal</label><textarea id={`withdraw-${item.id}`} required maxLength={2000} value={withdrawReason} onChange={(event) => setWithdrawReason(event.target.value)} autoFocus /><div className="inline-actions"><button className="small-button reject-button" disabled={busy || !withdrawReason.trim()}>Confirm withdrawal</button><button type="button" className="ghost-button" disabled={busy} onClick={() => setWithdrawId(null)}>Cancel</button></div></form>}</>}
      </article>)}<Pagination {...queue} onPage={queue.setPage} />
    </section></main>
}
