import { useState } from 'react'
import { toast } from 'react-toastify'
import api, { errorMessage } from '../services/api'
import { usePaged } from '../hooks/usePaged'
import { Header, Pagination, LoadError, RequestDetails } from '../components/Workflow'
import type { OvertimeRequest } from '../types'
import RequestFilters, { initialRequestFilters } from '../components/RequestFilters'

export default function HeadManagerDashboard() {
  const [status, setStatus] = useState('pending')
  const [filters, setFilters] = useState(initialRequestFilters)
  const queue = usePaged<OvertimeRequest>('/requests/', { ...filters, status })
  const [busy, setBusy] = useState<number | null>(null)
  const [rejectId, setRejectId] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const decide = async (item: OvertimeRequest, decision: 'approve' | 'reject') => {
    setBusy(item.id)
    try {
      await api.patch(`/requests/${item.id}/${decision}/`, decision === 'reject' ? { rejection_reason: reason.trim() } : {})
      toast.success(decision === 'approve' ? 'Request approved. HR notification queued.' : 'Request rejected. Manager notification queued.')
      setRejectId(null); setReason(''); queue.reload()
    } catch (error) { toast.error(errorMessage(error)); queue.reload() }
    finally { setBusy(null) }
  }
  return <main className="dashboard-shell dashboard-head"><Header title="Review overtime requests" description="Approve or reject advance authorizations across all departments." />
    <section className="history-panel"><div className="section-heading"><h2>Approval queue and history</h2><label className="filter-control">Status<select value={status} onChange={(event) => { setStatus(event.target.value); queue.setPage(1); setRejectId(null) }}><option value="pending">Pending approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="withdrawn">Withdrawn</option><option value="">All requests</option></select></label></div>
      <RequestFilters filters={filters} onChange={(value) => { setFilters(value); setRejectId(null) }} refresh={queue.reload} loading={queue.loading} disabled={busy !== null} />
      {queue.error ? <LoadError error={queue.error} retry={queue.reload} /> : queue.loading ? <p role="status">Loading requests…</p> : queue.items.length === 0 ? <p className="empty-state">No requests match your filters. Try another status or clear the filters.</p> : <div className="request-list">{queue.items.map((item) => <article className="request-row" key={item.id}>
        <div className="request-row-heading"><div><h3>{item.title}</h3><p className="muted">{item.request_id} · {item.department} · {item.requester_name || 'Department manager'}</p></div><span className={`status-label status-${item.status}`}>{item.status}</span></div>
        <p><strong>{item.total_hours} employee-hours</strong> · {item.start_date} to {item.end_date} · Estimated cost: {item.estimated_cost ?? 'Not provided'}</p><p><strong>Justification:</strong> {item.reason}</p>
        <RequestDetails item={item} />
        {item.status === 'pending' && <div className="decision-actions"><div className="inline-actions"><button className="small-button approve-button" disabled={busy !== null} onClick={() => decide(item, 'approve')}>{busy === item.id ? 'Saving…' : 'Approve request'}</button><button className="small-button reject-button" disabled={busy !== null} onClick={() => { setRejectId(item.id); setReason('') }}>Reject with reason</button></div>
        {rejectId === item.id && <form className="inline-form" onSubmit={(event) => { event.preventDefault(); void decide(item, 'reject') }}><label htmlFor={`reject-${item.id}`}>Reason for rejection</label><textarea id={`reject-${item.id}`} required maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} autoFocus /><div className="inline-actions"><button className="small-button reject-button" disabled={busy !== null || !reason.trim()}>Confirm rejection</button><button type="button" className="ghost-button" disabled={busy !== null} onClick={() => setRejectId(null)}>Cancel</button></div></form>}</div>}
      </article>)}</div>}
      <Pagination {...queue} onPage={queue.setPage} />
    </section></main>
}
