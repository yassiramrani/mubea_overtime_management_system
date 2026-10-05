import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'react-toastify'
import { errorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, user } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  useEffect(() => {
    const role = user?.profile?.role
    if (role) navigate(role === 'admin' ? '/administration' : role === 'dept_manager' ? '/dept-manager' : role === 'hr_manager' ? '/hr-manager' : '/head-manager', { replace: true })
  }, [user, navigate])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')

    try {
      const loggedInUser = await login(username, password)
      const userRole = loggedInUser?.profile?.role

      if (userRole === 'dept_manager') {
        navigate('/dept-manager')
      } else if (userRole === 'head_manager') {
        navigate('/head-manager')
      } else if (userRole === 'hr_manager') {
        navigate('/hr-manager')
      } else if (userRole === 'admin') {
        navigate('/administration')
      } else if (loggedInUser.is_superuser) {
        navigate('/administration')
      } else {
        throw new Error('This account has no assigned manager role. Contact your administrator.')
      }

      toast.success('Login successful')
    } catch (error) {
      setError(errorMessage(error, 'Login failed. Check your username and password.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-shell">
      <section className="login-visual">
        <div className="brand-mark">OT</div>
        <h1>Mubea Overtime Management system.</h1>
        <p className="visual-copy">One calm place to submit, track, and manage overtime across every department.</p>
        <div className="visual-stat"><strong>05</strong><span>connected departments</span></div>
      </section>

      <section className="login-panel">
        <div className="login-heading">
          <h2>Sign in to your workspace</h2>
          <p>Use your company manager credentials. Your account determines your department.</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form" aria-busy={loading}>
          {error && <p className="error-notice login-error" role="alert">{error}</p>}
          <div className="field">
            <label htmlFor="username">Username</label>
          <input
            required
            id="username"
            disabled={loading}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
          <input
            required
            id="password"
            type={showPassword ? 'text' : 'password'}
            disabled={loading}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          </div>
          <label className="checkbox-control password-visibility"><input type="checkbox" checked={showPassword} onChange={(event) => setShowPassword(event.target.checked)} />Show password</label>

          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Continue to dashboard'}
          </button>
        </form>
        <p className="login-footer">Secure access for authorized managers</p>
      </section>
    </main>
  )
}
