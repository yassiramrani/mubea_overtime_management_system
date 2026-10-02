import { useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { toast } from 'react-toastify'
import api, { downloadCsv, errorMessage } from '../services/api'
import { usePaged } from '../hooks/usePaged'
import { Header, Pagination, LoadError, RequestDetails } from '../components/Workflow'
import type { OvertimeRequest, User, ExportBatch } from '../types'
import RequestFilters, { initialRequestFilters } from '../components/RequestFilters'

function AssignmentEditor({ item, onSaved, onCancel }: { item: OvertimeRequest; onSaved: () => void; onCancel: () => void }) {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const employees = usePaged<User>('/users/', { search })
  const [selected, setSelected] = useState<Record<number, string>>(Object.fromEntries((item.assignment?.employees || []).map((employee) => [employee.id, employee.name])))
  const [notes, setNotes] = useState(item.assignment?.notes || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const searchInput = useRef<HTMLInputElement>(null)
  const save = async () => {
    setBusy(true); setError(''); setConflict(false)
    try {
      await api.post('/assignments/', { overtime_request: item.id, assigned_employees: Object.keys(selected).map(Number), expected_version: item.version, notes })
      toast.success('Employee assignment saved. Manager notification queued.'); onSaved()
    } catch (err) { setError(errorMessage(err)); setConflict(isAxiosError(err) && err.response?.status === 409) }
    finally { setBusy(false) }
  }
  return <section className="assignment-editor" aria-label={`Assign employees to ${item.title}`} aria-busy={busy}><h4>Employee selection</h4><form className="inline-actions" onSubmit={(event) => { event.preventDefault(); setSearch(query.trim()); employees.setPage(1) }}><label htmlFor={`employee-search-${item.id}`}>Find employee</label><input ref={searchInput} autoFocus disabled={busy} id={`employee-search-${item.id}`} type="search" value={query} onChange={(event) => setQuery(event.target.value)} /><button className="ghost-button" disabled={busy}>Search</button></form>
    <p role="status">{Object.keys(selected).length} {Object.keys(selected).length === 1 ? 'employee' : 'employees'} selected</p>
    {Object.keys(selected).length > 0 && <div className="selected-employees"><p className="muted">Remove a selected employee here even if they no longer appear in the directory.</p><ul aria-label="Selected employees">{Object.entries(selected).map(([id, name]) => <li key={id}><span>{name}</span><button className="ghost-button" disabled={busy} aria-label={`Remove ${name} from assignment`} onClick={() => { setSelected((current) => { const next = { ...current }; delete next[Number(id)]; return next }); searchInput.current?.focus() }}>Remove</button></li>)}</ul></div>}
    {employees.error ? <LoadError error={employees.error} retry={employees.reload} /> : employees.loading ? <p role="status">Loading employees…</p> : employees.items.length === 0 ? <p>No employees match your search.</p> : <fieldset className="employee-picker"><legend>Available employees</legend>{employees.items.map((employee) => {
      const name = `${employee.first_name || ''} ${employee.last_name || ''}`.trim() || employee.username
      return <label key={employee.id}><input type="checkbox" checked={employee.id in selected} disabled={busy} onChange={() => setSelected((current) => { const next = { ...current }; if (employee.id in next) delete next[employee.id]; else next[employee.id] = name; return next })} />{name}</label>
    })}</fieldset>}
    <Pagination {...employees} loading={employees.loading || busy} onPage={employees.setPage} /><div className="form-field"><label htmlFor={`notes-${item.id}`}>HR notes (optional)</label><textarea disabled={busy} id={`notes-${item.id}`} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} /></div>
    {error && <div className="error-notice" role="alert"><p>{error}</p>{conflict && <p>Close this editor, refresh the request queue, and reopen the assignment to review its latest version.</p>}</div>}<div className="inline-actions"><button className="small-button approve-button" disabled={busy || conflict || (item.requires_employee_assignment && Object.keys(selected).length === 0)} onClick={save}>{busy ? 'Saving…' : 'Save assignment'}</button><button className="ghost-button" disabled={busy} onClick={onCancel}>Close editor</button></div>
  </section>
}

function BatchHistory() {
  const batches = usePaged<ExportBatch>('/export-batches/')
  const [active, setActive] = useState<string | null>(null)
  const [result, setResult] = useState('confirmed')
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const download = async (id: string) => {
    setBusy(true)
    try { const response = await api.get(`/export-batches/${id}/download/`, { responseType: 'blob' }); downloadCsv(response.data, `overtime-approval-${id}.csv`) }
    catch (error) { toast.error(errorMessage(error)) }
    finally { setBusy(false) }
  }
  const record = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true)
    try { await api.post(`/export-batches/${active}/record_result/`, { status: result, sap_reference: reference, result_note: note }); toast.success('Import result recorded.'); setActive(null); batches.reload() }
    catch (error) { toast.error(errorMessage(error)) }
    finally { setBusy(false) }
  }
  return <section className="history-panel"><h2>Saved export batches</h2><p className="muted">Download the original file again without creating another export. Record an import result only after checking it in SAP.</p>
    {batches.error ? <LoadError error={batches.error} retry={batches.reload} /> : batches.loading ? <p role="status">Loading export history…</p> : batches.items.length === 0 ? <p className="empty-state">No export batches have been created.</p> : batches.items.map((batch) => <article className="request-row" key={batch.id}><h3>{new Date(batch.created_at).toLocaleString()} · {batch.row_count} requests</h3><p>{batch.status === 'generated' ? 'File generated; import unconfirmed' : batch.status === 'confirmed' ? 'Import confirmed' : 'Import failed'} · {batch.created_by_name}</p><p className="muted">Batch {batch.id}</p>{batch.sap_reference && <p>SAP reference: {batch.sap_reference}</p>}{batch.result_note && <p>{batch.result_note}</p>}<div className="inline-actions"><button className="ghost-button" disabled={busy} onClick={() => download(batch.id)}>Download saved file</button>{batch.status !== 'confirmed' && <button className="ghost-button" disabled={busy} onClick={() => { setActive(batch.id); setReference(''); setNote(''); setResult('confirmed') }}>Record SAP import result</button>}</div>
    {active === batch.id && <form className="inline-form" onSubmit={record}><label htmlFor={`result-${batch.id}`}>Import result</label><select id={`result-${batch.id}`} value={result} onChange={(event) => setResult(event.target.value)}><option value="confirmed">Import confirmed in SAP</option><option value="failed">Import failed</option></select><label htmlFor={`reference-${batch.id}`}>SAP import reference{result === 'confirmed' ? ' (required)' : ''}</label><input id={`reference-${batch.id}`} maxLength={100} required={result === 'confirmed'} value={reference} onChange={(event) => setReference(event.target.value)} /><label htmlFor={`note-${batch.id}`}>Result notes{result === 'failed' ? ' (required)' : ''}</label><textarea id={`note-${batch.id}`} required={result === 'failed'} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /><div className="inline-actions"><button className="small-button approve-button" disabled={busy}>Save result</button><button type="button" className="ghost-button" disabled={busy} onClick={() => setActive(null)}>Cancel</button></div></form>}
    </article>)}<Pagination {...batches} onPage={batches.setPage} />
  </section>
}

export default function HRManagerDashboard() {
  const [filters, setFilters] = useState(initialRequestFilters)
  const queue = usePaged<OvertimeRequest>('/requests/', { ...filters, status: 'approved' })
  const [selected, setSelected] = useState<Record<number, OvertimeRequest>>({})
  const [editing, setEditing] = useState<number | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [exportError, setExportError] = useState('')
  const [focusAssignment, setFocusAssignment] = useState<number | null>(null)
  useEffect(() => {
    if (focusAssignment === null || queue.loading || editing !== null) return
    document.getElementById(`assignment-trigger-${focusAssignment}`)?.focus()
    setFocusAssignment(null)
  }, [focusAssignment, queue.loading, editing])
  const resetExport = () => {
    setSelected({}); setPreview(null); setExportError(''); queue.reload()
    setHistoryRevision((value) => value + 1)
  }
  const selection = { request_ids: Object.keys(selected).map(Number), versions: Object.fromEntries(Object.values(selected).map((item) => [String(item.id), item.version])) }
  const previewExport = async () => {
    setBusy(true); setPreview(null); setExportError('')
    try { const response = await api.post('/sap-exports/preview/', selection); setPreview(response.data.csv_data) }
    catch (error) { setExportError(errorMessage(error)) }
    finally { setBusy(false) }
  }
  const exportFile = async () => {
    setBusy(true); setExportError('')
    try {
      const response = await api.post('/sap-exports/export_to_csv/', selection)
      downloadCsv(response.data.csv_data, `overtime-approval-${response.data.batch.id}.csv`)
      toast.success(response.data.message); setSelected({}); setPreview(null); queue.reload(); setHistoryRevision((value) => value + 1)
    } catch (error) { setExportError(errorMessage(error)); setPreview(null) }
    finally { setBusy(false) }
  }
  return <main className="dashboard-shell dashboard-hr"><Header title="Prepare approved overtime" description="Assign employees and prepare approved hours for the advance authorization export." />
    <p className="export-notice">The current file is an approval review CSV. Your SAP team must validate its mapping before it is used for an import.</p>
    <section className="history-panel"><div className="section-heading"><h2>Approved requests</h2><span>{queue.count} approved</span></div>
      <RequestFilters filters={filters} onChange={setFilters} refresh={queue.reload} loading={queue.loading} disabled={busy || editing !== null} />
      {exportError && <div className="error-notice" role="alert"><p>{exportError}</p><p>Refresh and reselect requests to review their latest state. If a download failed, check saved batches before creating another export.</p><button className="ghost-button" disabled={busy || editing !== null} onClick={resetExport}>Refresh queue and clear selection</button></div>}
      <div className="toolbar"><p>{Object.keys(selected).length} {Object.keys(selected).length === 1 ? 'request' : 'requests'} selected across pages (maximum 200).</p><div className="inline-actions"><button className="ghost-button" disabled={busy || !Object.keys(selected).length} onClick={() => { setSelected({}); setPreview(null) }}>Clear selection</button><button className="primary-button" disabled={busy || !Object.keys(selected).length || editing !== null} onClick={previewExport}>{busy ? 'Working…' : 'Preview selected export'}</button></div></div>
      {Object.keys(selected).length > 0 && <details className="selected-requests" open><summary>Selected for export · {Object.values(selected).reduce((sum, item) => sum + Number(item.total_hours), 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} employee-hours</summary><p className="muted">Selection is kept when you change pages or filters. Review every request before creating the batch.</p><ul>{Object.values(selected).map((item) => <li key={item.id}><div><strong>{item.title}</strong><span className="muted">{item.request_id} · {item.total_hours} employee-hours</span></div><button className="ghost-button" disabled={busy || editing !== null} aria-label={`Remove ${item.title} from export`} onClick={() => { setSelected((current) => { const next = { ...current }; delete next[item.id]; return next }); setPreview(null) }}>Remove</button></li>)}</ul></details>}
      {preview !== null && <section className="export-preview"><h3>Review the selected export</h3><p>Creating this batch saves the file and locks these assignments. Import confirmation is recorded separately.</p><pre tabIndex={0} aria-label="CSV export preview">{preview}</pre><div className="inline-actions"><button className="primary-button" disabled={busy} onClick={exportFile}>Create batch and download</button><button className="ghost-button" disabled={busy} onClick={() => setPreview(null)}>Close preview</button></div></section>}
      {queue.error ? <LoadError error={queue.error} retry={queue.reload} /> : queue.loading ? <p role="status">Loading approved requests…</p> : queue.items.length === 0 ? <p className="empty-state">No approved requests match your filters. Clear the filters or check again after a request is approved.</p> : queue.items.map((item) => {
        const ready = !item.export_batch && (!item.requires_employee_assignment || Boolean(item.assignment?.employees.length))
        return <article className="request-row" key={item.id}><div className="request-row-heading"><label className="checkbox-control"><input type="checkbox" aria-label={`Select ${item.title} for export`} disabled={busy || !ready || (Object.keys(selected).length >= 200 && !(item.id in selected)) || editing !== null} checked={item.id in selected} onChange={() => { setSelected((current) => { const next = { ...current }; if (item.id in next) delete next[item.id]; else next[item.id] = item; return next }); setPreview(null) }} /><strong>{item.title}</strong></label><span className="status-label">{item.export_batch ? 'Exported' : ready ? 'Ready for export' : 'Needs employees'}</span></div><p className="muted">{item.request_id} · {item.department}</p><p><strong>{item.total_hours} approved employee-hours</strong> · {item.start_date} to {item.end_date}</p><RequestDetails item={item} />
        {!item.export_batch && editing !== item.id && <button id={`assignment-trigger-${item.id}`} className="ghost-button" disabled={busy || editing !== null} onClick={() => { setEditing(item.id); setPreview(null); setExportError(''); setSelected((current) => { const next = { ...current }; delete next[item.id]; return next }) }}>{item.assignment ? 'Edit employee assignment' : item.requires_employee_assignment ? 'Assign employees' : 'Add employees (optional)'}</button>}
        {editing === item.id && <AssignmentEditor item={item} onCancel={() => { setEditing(null); setFocusAssignment(item.id) }} onSaved={() => { setEditing(null); setFocusAssignment(item.id); queue.reload() }} />}
        </article>
      })}<Pagination {...queue} loading={queue.loading || busy || editing !== null} onPage={queue.setPage} />
    </section><BatchHistory key={historyRevision} /></main>
}
