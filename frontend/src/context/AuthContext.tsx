import { createContext, useContext, useEffect, useState } from 'react'
import api, { errorMessage } from '../services/api'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  error: string
  retry: () => void
  login: (username: string, password: string) => Promise<User>
  logout: () => Promise<void>
}
const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const loadUser = async () => {
    setLoading(true); setError('')
    try {
      if (!localStorage.getItem('accessToken')) { setUser(null); return null }
      const response = await api.get<User>('/users/me/')
      setUser(response.data)
      return response.data
    } catch (err) {
      setUser(null)
      if (localStorage.getItem('accessToken')) setError(errorMessage(err))
      return null
    } finally { setLoading(false) }
  }
  useEffect(() => {
    void loadUser()
    const expired = () => { setUser(null); setError('') }
    window.addEventListener('auth-expired', expired)
    return () => window.removeEventListener('auth-expired', expired)
  }, [])
  const login = async (username: string, password: string) => {
    const response = await api.post('/auth/login/', { username, password })
    localStorage.setItem('accessToken', response.data.token)
    const current = await loadUser()
    if (!current) throw new Error('Signed in, but unable to load your profile. Please retry.')
    return current
  }
  const logout = async () => {
    if (localStorage.getItem('accessToken')) await api.post('/auth/logout/')
    localStorage.removeItem('accessToken'); setUser(null); setError('')
  }
  return <AuthContext.Provider value={{ user, loading, error, retry: () => { void loadUser() }, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
