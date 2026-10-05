import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'react-toastify'
import api, { errorMessage } from '../services/api'
import { usePaged } from '../hooks/usePaged'
import { useAuth } from '../context/AuthContext'
import { Header, Pagination, LoadError } from '../components/Workflow'
import { roleLabels, departmentLabels } from '../labels'
import type { AdminAccount, EmailLog, ExportBatch, OvertimeRequest, User } from '../types'

const departments = ['logistics', 'quality', 'production', 'maintenance', 'planning']

interface DepartmentLoad { department: string; total: number; pending: number }
interface OverviewCounts {
  total: number; pending: number; approved: number; closed: number
  accounts: number; batches: number; queued: number; sent: number; failed: number
  departments: DepartmentLoad[]
}

function useOverviewCounts(accountsPath: string) {
  const [data, setData] = useState<OverviewCounts | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let cancelled = false
    const count = (path: string, params: Record<string, string> = {}) => api.get(path, { params }).then((response) => response.data.count as number)
    const load = async () => {
      try {
        const [total, pending, approved, rejected, withdrawn, accounts, batches, queued, sent, failed] = await Promise.all([
          count('/requests/'), count('/requests/', { status: 'pending' }), count('/requests/', { status: 'approved' }),
          count('/requests/', { status: 'rejected' }), count('/requests/', { status: 'withdrawn' }),
          count(accountsPath), count('/export-batches/'),
          count('/email-logs/', { status: 'queued' }), count('/email-logs/', { status: 'sent' }), count('/email-logs/', { status: 'failed' }),
        ])
        const departmentLoad = await Promise.all(departments.map(async (department) => ({
          department,
          total: await count('/requests/', { department }),
          pending: await count('/requests/', { department, status: 'pending' }),
        })))
        if (!cancelled) {
          setData({ total, pending, approved, closed: rejected + withdrawn, accounts, batches, queued, sent, failed, departments: departmentLoad })
          setError('')
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err))
      }
    }
    void load()
    return () => { cancelled = true }
  }, [revision, accountsPath])
  return { data, error, loading: !data && !error, reload: () => setRevision((value) => value + 1) }
}

function useSystemHealth() {
  const [reachable, setReachable] = useState<boolean | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let cancelled = false
    fetch('/health/')
      .then((response) => { if (!cancelled) setReachable(response.ok) })
      .catch(() => { if (!cancelled) setReachable(false) })
    return () => { cancelled = true }
  }, [revision])
  return { reachable, reload: () => setRevision((value) => value + 1) }
}

function StatCard({ label, value, tone, hint }: { label: string; value: number | null; tone?: string; hint?: string }) {
  return <article className={`stat-card${tone ? ` stat-${tone}` : ''}`}><span>{label}</span><strong>{value === null ? '—' : value.toLocaleString()}</strong>{hint && <small>{hint}</small>}</article>
}

function waitingLabel(createdAt: string) {
  const days = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 86400000))
  return days === 0 ? 'today' : `${days} day${days === 1 ? '' : 's'}`
}

const batchStatus: Record<string, { className: string; label: string }> = {
  generated: { className: 'badge badge-queued', label: 'Import unconfirmed' },
  confirmed: { className: 'badge badge-sent', label: 'Import confirmed' },
  failed: { className: 'badge badge-failed', label: 'Import failed' },
}

const accountRoleOptions: [string, string][] = [
  ['employee', 'Employee account'],
  ['dept_manager', 'Department manager'],
  ['head_manager', 'Head manager'],
  ['hr_manager', 'HR manager'],
  ['admin', 'Administrator'],
]

function accountRoleLabel(account: AdminAccount) {
  if (account.profile?.role) return roleLabels[account.profile.role] || account.profile.role
  return account.is_superuser ? 'Administrator' : 'Employee account'
}

function AccountEditor({ account, onSaved, onCancel }: { account: AdminAccount | null; onSaved: () => void; onCancel: () => void }) {
  const isNew = account === null
  const [username, setUsername] = useState('')
  const [firstName, setFirstName] = useState(account?.first_name || '')
  const [lastName, setLastName] = useState(account?.last_name || '')
  const [email, setEmail] = useState(account?.email || '')
  const [role, setRole] = useState(account ? account.profile?.role || (account.is_superuser ? 'admin' : 'employee') : 'employee')
  const [department, setDepartment] = useState(account?.profile?.department || '')
  const [password, setPassword] = useState('')
  const [active, setActive] = useState(account?.is_active ?? true)
  const [djangoAdmin, setDjangoAdmin] = useState(Boolean(account?.is_superuser))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true); setError('')
    const payload: Record<string, unknown> = {
      first_name: firstName, last_name: lastName, email, role,
      department: role === 'dept_manager' ? department || null : null,
      django_admin: djangoAdmin && role === 'admin',
    }
    if (isNew) {
      payload.username = username
      payload.password = password
    } else {
      payload.is_active = active
      if (password) payload.password = password
    }
    try {
      if (isNew) await api.post('/admin/accounts/', payload)
      else await api.patch(`/admin/accounts/${account.id}/`, payload)
      toast.success(isNew ? 'Account created. Share the password privately.' : 'Account updated.')
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return <section className="request-form-panel" aria-label={isNew ? 'Create account' : `Edit ${account.username}`}>
    <h3>{isNew ? 'New account' : `Edit ${account.username}`}</h3>
    <form className="request-form" onSubmit={save} aria-busy={busy}>
      {isNew && <div className="form-field"><label htmlFor="account-username">Username</label><input id="account-username" required maxLength={150} autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} /></div>}
      <div className="form-field"><label htmlFor="account-first-name">First name</label><input id="account-first-name" maxLength={150} value={firstName} onChange={(event) => setFirstName(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="account-last-name">Last name</label><input id="account-last-name" maxLength={150} value={lastName} onChange={(event) => setLastName(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="account-email">Email</label><input id="account-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
      <div className="form-field"><label htmlFor="account-role">Role</label><select id="account-role" value={role} onChange={(event) => { setRole(event.target.value); if (event.target.value !== 'admin') setDjangoAdmin(false) }}>{accountRoleOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      {role === 'dept_manager' && <div className="form-field"><label htmlFor="account-department">Department</label><select id="account-department" required value={department} onChange={(event) => setDepartment(event.target.value)}><option value="">Select a department</option>{departments.map((value) => <option key={value} value={value}>{departmentLabels[value]}</option>)}</select></div>}
      <div className="form-field"><label htmlFor="account-password">{isNew ? 'Initial password' : 'New password (optional)'}</label><input id="account-password" type="password" required={isNew} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
      {!isNew && <div className="form-field"><label className="checkbox-control"><input id="account-active" type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />Active account</label></div>}
      <div className="form-field"><label className="checkbox-control"><input id="account-django-admin" type="checkbox" disabled={role !== 'admin'} checked={djangoAdmin && role === 'admin'} onChange={(event) => setDjangoAdmin(event.target.checked)} />Django administration access</label><small className="muted">Full database administration. Requires the Administrator role.</small></div>
      {error && <div className="error-notice full-width" role="alert"><p>{error}</p></div>}
      <div className="form-actions full-width"><button className="small-button approve-button" disabled={busy}>{busy ? 'Saving…' : isNew ? 'Create account' : 'Save changes'}</button><button type="button" className="ghost-button" disabled={busy} onClick={onCancel}>Cancel</button></div>
    </form>
  </section>
}

export default function AdminDashboard() {
  const { user: currentUser } = useAuth()
  const canManageAccounts = Boolean(currentUser?.is_superuser)
  const accountsPath = canManageAccounts ? '/admin/accounts/' : '/users/'
  const counts = useOverviewCounts(accountsPath)
  const health = useSystemHealth()
  const queue = usePaged<OvertimeRequest>('/requests/', { status: 'pending', ordering: 'created_at' })
  const failedMail = usePaged<EmailLog>('/email-logs/', { status: 'failed' })
  const batches = usePaged<ExportBatch>('/export-batches/')
  const [accountQuery, setAccountQuery] = useState('')
  const [accountSearch, setAccountSearch] = useState('')
  const accounts = usePaged<AdminAccount | User>(accountsPath, { search: accountSearch })
  const [creatingAccount, setCreatingAccount] = useState(false)
  const [editingAccount, setEditingAccount] = useState<AdminAccount | null>(null)
  const refresh = () => {
    counts.reload(); health.reload(); queue.reload(); failedMail.reload(); batches.reload(); accounts.reload()
    toast.success('Overview refreshed.')
  }
  const busiest = Math.max(1, ...(counts.data?.departments.map((load) => load.total) ?? [1]))

  return <main className="dashboard-shell dashboard-admin">
    <Header title="Administration overview" description="System-wide view of requests, notification delivery, exports and accounts." />
    <div className="toolbar">
      <p className={`system-status${health.reachable === true ? ' is-up' : health.reachable === false ? ' is-down' : ''}`} role="status">
        {health.reachable === null ? 'Checking system health…' : health.reachable ? 'API and database reachable' : 'Health check failed — API or database unavailable'}
      </p>
      <button className="ghost-button" onClick={refresh}>Refresh data</button>
    </div>

    {counts.error ? <LoadError error={counts.error} retry={counts.reload} /> : <>
      <section className="stat-grid" aria-label="Key figures">
        <StatCard label="Total requests" value={counts.data?.total ?? null} />
        <StatCard label="Awaiting review" value={counts.data?.pending ?? null} tone="coral" hint="Pending head-manager decisions" />
        <StatCard label="Approved" value={counts.data?.approved ?? null} tone="green" />
        <StatCard label="Closed without approval" value={counts.data?.closed ?? null} tone="slate" hint="Rejected or withdrawn" />
        <StatCard label="Accounts" value={counts.data?.accounts ?? null} hint="Manager and employee logins" />
        <StatCard label="Export batches" value={counts.data?.batches ?? null} hint="Saved review files" />
      </section>

      <div className="admin-grid">
        <section className="history-panel" aria-label="Approval queue">
          <div className="section-heading"><h2>Approval queue</h2><span className="panel-note">Longest waiting first</span></div>
          {queue.error ? <LoadError error={queue.error} retry={queue.reload} /> : queue.loading ? <p role="status">Loading pending requests…</p> : queue.items.length === 0 ? <p className="empty-state">Nothing is waiting for approval.</p> : <div className="table-wrap"><table>
            <thead><tr><th>Request</th><th>Department</th><th>Requester</th><th>Hours</th><th>Waiting</th></tr></thead>
            <tbody>{queue.items.slice(0, 5).map((item) => <tr key={item.id}>
              <td><strong>{item.title}</strong><small>{item.request_id}</small></td>
              <td>{departmentLabels[item.department] || item.department}</td>
              <td>{item.requester_name || '—'}</td>
              <td>{item.total_hours}</td>
              <td>{waitingLabel(item.created_at)}</td>
            </tr>)}</tbody>
          </table></div>}
          <p className="panel-link"><Link to="/head-manager">Review and decide in the approvals workspace →</Link></p>
        </section>

        <section className="history-panel" aria-label="Notification outbox">
          <div className="section-heading"><h2>Notification outbox</h2><span className="panel-note">Email delivery log</span></div>
          <p className="panel-note">Delivery runs through the scheduled <code>send_notifications</code> command; queued messages wait for the next run.</p>
          <div className="outbox-metrics">
            <div><strong>{counts.data ? counts.data.queued.toLocaleString() : '—'}</strong><span>Queued</span></div>
            <div><strong>{counts.data ? counts.data.sent.toLocaleString() : '—'}</strong><span>Delivered</span></div>
            <div className={counts.data && counts.data.failed > 0 ? 'is-alert' : ''}><strong>{counts.data ? counts.data.failed.toLocaleString() : '—'}</strong><span>Failed</span></div>
          </div>
          {failedMail.error ? <LoadError error={failedMail.error} retry={failedMail.reload} /> : failedMail.loading ? <p role="status">Loading failed messages…</p> : failedMail.items.length === 0 ? <p className="panel-note">No failed deliveries recorded.</p> : <ul className="failed-mail">
            {failedMail.items.slice(0, 4).map((log) => <li key={log.id}><strong>{log.recipient}</strong><small>{log.subject}</small><small>{log.attempts} failed {log.attempts === 1 ? 'attempt' : 'attempts'}{log.error_message ? ` · ${log.error_message}` : ''}</small></li>)}
          </ul>}
        </section>
      </div>

      <div className="admin-grid">
        <section className="history-panel" aria-label="Department workload">
          <div className="section-heading"><h2>Department workload</h2><span className="panel-note">All requests by department</span></div>
          {counts.data ? <div className="bar-chart">{counts.data.departments.map((load) => <div className="bar-row" key={load.department}>
            <span>{departmentLabels[load.department] || load.department}</span>
            <div className="bar-track" role="img" aria-label={`${departmentLabels[load.department] || load.department}: ${load.total} requests, ${load.pending} awaiting review`}>
              <div className="bar-seg bar-other" style={{ width: `${((load.total - load.pending) / busiest) * 100}%` }} />
              <div className="bar-seg bar-pending" style={{ width: `${(load.pending / busiest) * 100}%` }} />
            </div>
            <span className="bar-value">{load.total}</span>
          </div>)}</div> : <p role="status">Loading department totals…</p>}
          <p className="bar-legend"><span><span className="legend-chip pending" />Awaiting review</span><span><span className="legend-chip other" />Other statuses</span></p>
        </section>

        <section className="history-panel" aria-label="Recent export batches">
          <div className="section-heading"><h2>Recent export batches</h2><span className="panel-note">Latest saved files</span></div>
          {batches.error ? <LoadError error={batches.error} retry={batches.reload} /> : batches.loading ? <p role="status">Loading export batches…</p> : batches.items.length === 0 ? <p className="empty-state">No export batches yet.</p> : <div className="table-wrap"><table>
            <thead><tr><th>Created</th><th>Rows</th><th>Status</th><th>Recorded by</th></tr></thead>
            <tbody>{batches.items.slice(0, 5).map((batch) => <tr key={batch.id}>
              <td>{new Date(batch.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</td>
              <td>{batch.row_count}</td>
              <td><span className={batchStatus[batch.status]?.className || 'badge'}>{batchStatus[batch.status]?.label || batch.status}</span></td>
              <td>{batch.created_by_name || '—'}</td>
            </tr>)}</tbody>
          </table></div>}
          <p className="panel-link"><Link to="/hr-manager">Download files and record SAP import results →</Link></p>
        </section>
      </div>

      <section className="history-panel" aria-label="Accounts directory">
        <div className="section-heading">
          <h2>Accounts directory</h2>
          {canManageAccounts && <button className="small-button approve-button" onClick={() => { setCreatingAccount(true); setEditingAccount(null) }}>New account</button>}
        </div>
        <p className="panel-note">{canManageAccounts ? 'Create accounts, assign roles or departments, reset passwords and deactivate leavers. Deactivation replaces deletion so history and assignments stay intact.' : 'Manager and employee accounts · administrator accounts excluded'}</p>
        <form className="account-search" role="search" onSubmit={(event) => { event.preventDefault(); setAccountSearch(accountQuery.trim()) }}>
          <label htmlFor="account-search">Search accounts</label>
          <input id="account-search" type="search" value={accountQuery} onChange={(event) => setAccountQuery(event.target.value)} placeholder="Name, username or email" />
          <button className="ghost-button" disabled={accounts.loading}>Search</button>
        </form>
        {(creatingAccount || editingAccount) && <AccountEditor key={editingAccount ? `edit-${editingAccount.id}` : 'new'} account={editingAccount} onSaved={() => { setCreatingAccount(false); setEditingAccount(null); accounts.reload(); counts.reload() }} onCancel={() => { setCreatingAccount(false); setEditingAccount(null) }} />}
        {accounts.error ? <LoadError error={accounts.error} retry={accounts.reload} /> : accounts.loading ? <p role="status">Loading accounts…</p> : accounts.items.length === 0 ? <p className="empty-state">No accounts match this search.</p> : canManageAccounts ? <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Role</th><th>Department</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{(accounts.items as AdminAccount[]).map((account) => <tr key={account.id}>
            <td>{`${account.first_name || ''} ${account.last_name || ''}`.trim() || '—'}</td>
            <td>{account.username}</td>
            <td>{account.email || '—'}</td>
            <td>{accountRoleLabel(account)}</td>
            <td>{account.profile?.department ? departmentLabels[account.profile.department] || account.profile.department : '—'}</td>
            <td><span className={account.is_active ? 'badge badge-sent' : 'badge badge-neutral'}>{account.is_active ? 'Active' : 'Deactivated'}</span>{account.is_superuser && <span className="badge badge-queued">Django admin</span>}</td>
            <td><button className="row-action" aria-label={`Edit ${account.username}`} onClick={() => { setEditingAccount(account); setCreatingAccount(false) }}>Edit</button></td>
          </tr>)}</tbody>
        </table></div> : <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Role</th><th>Department</th></tr></thead>
          <tbody>{(accounts.items as User[]).map((account) => <tr key={account.id}>
            <td>{`${account.first_name || ''} ${account.last_name || ''}`.trim() || '—'}</td>
            <td>{account.username}</td>
            <td>{account.email || '—'}</td>
            <td>{account.profile?.role ? roleLabels[account.profile.role] || account.profile.role : 'Employee account'}</td>
            <td>{account.profile?.department ? departmentLabels[account.profile.department] || account.profile.department : '—'}</td>
          </tr>)}</tbody>
        </table></div>}
        <Pagination {...accounts} onPage={accounts.setPage} />
      </section>

      <p className="admin-footer muted">Role and permission changes stay a superuser task in <a href="/admin/">Django administration</a>. This overview is read-only.</p>
    </>}
  </main>
}
