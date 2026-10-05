import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-toastify'
import api, { errorMessage } from '../services/api'

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const firstField = useRef<HTMLInputElement>(null)
  useEffect(() => {
    firstField.current?.focus()
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (next !== confirm) {
      setError('The new password and its confirmation do not match.')
      return
    }
    setBusy(true); setError('')
    try {
      const response = await api.post<{ token?: string }>('/auth/change-password/', { current_password: current, new_password: next })
      if (response.data?.token) localStorage.setItem('accessToken', response.data.token)
      toast.success('Password changed. Other sessions were signed out.')
      onClose()
    } catch (err) {
      setError(errorMessage(err, 'Unable to change the password.'))
    } finally {
      setBusy(false)
    }
  }
  return <div className="password-overlay">
    <section className="password-dialog" role="dialog" aria-modal="true" aria-label="Change password">
      <h2>Change password</h2>
      <p className="muted">Your other sessions will be signed out.</p>
      <form onSubmit={submit} aria-busy={busy}>
        <div className="field"><label htmlFor="current-password">Current password</label><input ref={firstField} id="current-password" type="password" autoComplete="current-password" required disabled={busy} value={current} onChange={(event) => setCurrent(event.target.value)} /></div>
        <div className="field"><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" required disabled={busy} value={next} onChange={(event) => setNext(event.target.value)} /></div>
        <div className="field"><label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type="password" autoComplete="new-password" required disabled={busy} value={confirm} onChange={(event) => setConfirm(event.target.value)} /></div>
        {error && <p className="error-notice" role="alert">{error}</p>}
        <div className="dialog-actions"><button className="small-button approve-button" disabled={busy}>{busy ? 'Updating…' : 'Update password'}</button><button type="button" className="ghost-button" disabled={busy} onClick={onClose}>Cancel</button></div>
      </form>
    </section>
  </div>
}
