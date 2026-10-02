export type UserRole = 'dept_manager' | 'head_manager' | 'hr_manager' | 'admin'

export interface UserProfile {
  id: number
  user: number
  role: UserRole
  department?: string
  phone?: string
  created_at?: string
  updated_at?: string
}

export interface User {
  id: number
  username: string
  email: string
  first_name?: string
  last_name?: string
  is_staff?: boolean
  is_superuser?: boolean
  profile?: UserProfile
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthResponse {
  token?: string
  user?: User
}

export interface OvertimeRequest {
  id: number
  request_id: string
  requester_name: string
  department: string
  status: 'pending' | 'approved' | 'rejected' | 'withdrawn'
  version: number
  title: string
  description: string
  reason: string
  start_date: string
  end_date: string
  total_hours: string
  hourly_rate: string | null
  estimated_cost: string | null
  rejection_reason: string
  approved_by_name: string | null
  approval_date: string | null
  requires_employee_assignment: boolean
  assignment: { id: number; notes: string; status: string; employees: { id: number; name: string }[] } | null
  export_batch: string | null
}

export interface ExportBatch {
  id: string
  created_at: string
  created_by_name: string
  row_count: number
  checksum: string
  status: 'generated' | 'confirmed' | 'failed'
  sap_reference: string
  result_note: string
}
