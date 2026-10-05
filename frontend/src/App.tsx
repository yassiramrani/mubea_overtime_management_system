import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ToastContainer } from 'react-toastify'
import 'react-toastify/dist/ReactToastify.css'
import LoginPage from './pages/LoginPage'
import DepartmentManagerDashboard from './pages/DepartmentManagerDashboard'
import HeadManagerDashboard from './pages/HeadManagerDashboard'
import HRManagerDashboard from './pages/HRManagerDashboard'
import AdminDashboard from './pages/AdminDashboard'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LoadError } from './components/Workflow'

function Protected({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const { user, loading, error, retry } = useAuth()
  if (loading) return <main className="dashboard-shell" role="status">Loading your workspace…</main>
  if (error) return <main className="dashboard-shell"><LoadError error={error} retry={retry} /></main>
  if (!user) return <Navigate to="/login" replace />
  const role = user.profile?.role || ''
  if (!roles.includes(role)) return <main className="dashboard-shell"><p>You do not have access to this workspace.</p><a href="/login">Return to sign in</a></main>
  return <>{children}</>
}

export default function App() {
  return <AuthProvider><BrowserRouter><Routes>
    <Route path="/" element={<Navigate to="/login" replace />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dept-manager" element={<Protected roles={['dept_manager']}><DepartmentManagerDashboard /></Protected>} />
    <Route path="/head-manager" element={<Protected roles={['head_manager', 'admin']}><HeadManagerDashboard /></Protected>} />
    <Route path="/hr-manager" element={<Protected roles={['hr_manager', 'admin']}><HRManagerDashboard /></Protected>} />
    <Route path="/administration" element={<Protected roles={['admin']}><AdminDashboard /></Protected>} />
    <Route path="/dashboard/approvals" element={<Navigate to="/head-manager" replace />} />
    <Route path="/dashboard/assignments" element={<Navigate to="/hr-manager" replace />} />
    <Route path="/dashboard/requests" element={<Navigate to="/dept-manager" replace />} />
    <Route path="*" element={<main className="dashboard-shell"><h1>Page not found</h1><a href="/">Return to sign in</a></main>} />
  </Routes><ToastContainer position="bottom-right" limit={1} autoClose={3000} /></BrowserRouter></AuthProvider>
}
