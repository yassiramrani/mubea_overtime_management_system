import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 20000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Remove legacy bearer storage once; browser credentials now stay in HttpOnly cookies.
localStorage.removeItem('accessToken')
api.interceptors.request.use(async (config) => {
  if (!['get', 'head', 'options'].includes(config.method?.toLowerCase() || 'get')) {
    const response = await api.get<{ csrfToken: string }>('/auth/session/csrf/')
    config.headers['X-CSRFToken'] = response.data.csrfToken
  }
  return config
})

api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401 && error.config?.url !== '/auth/session/login/') {
    window.dispatchEvent(new Event('auth-expired'))
  }
  return Promise.reject(error)
})

export function errorMessage(error: unknown, fallback = 'Unable to complete this action. Try again.'): string {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback
  if (error.code === 'ECONNABORTED') return 'The server took too long to respond. Refresh to check whether your action completed.'
  if (!error.response) return 'Cannot reach the server. Check your connection and try again.'
  const data = error.response.data
  if (typeof data === 'object' && data) {
    return Object.entries(data).map(([key, value]) => `${['detail', 'error', 'non_field_errors'].includes(key) ? '' : `${key}: `}${Array.isArray(value) ? value.join(' ') : String(value)}`).join(' ')
  }
  return fallback
}

export function downloadCsv(content: string | Blob, filename: string) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = filename
  document.body.appendChild(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default api
