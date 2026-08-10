import type {
  ApiErrorBody,
  Batch,
  BulkUploadResponse,
  JobRoleDetail,
  JobRoleSummary,
  Page,
  ResumeUploadResponse,
} from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init)

  if (!response.ok) {
    let code = 'http_error'
    let message = `Request failed with status ${response.status}`
    let details: Record<string, unknown> = {}
    try {
      const body = (await response.json()) as ApiErrorBody
      if (body?.error) {
        code = body.error.code
        message = body.error.message
        details = body.error.details ?? {}
      }
    } catch {
      // Non-JSON error body — keep the generic message.
    }
    throw new ApiError(message, code, response.status, details)
  }

  return (await response.json()) as T
}

export const api = {
  listJobRoles: () => request<Page<JobRoleSummary>>('/job-roles?limit=100'),

  getJobRole: (ref: string) => request<JobRoleDetail>(`/job-roles/${ref}`),

  uploadResume: (jobRoleId: string, file: File) => {
    const form = new FormData()
    form.append('job_role_id', jobRoleId)
    form.append('file', file)
    return request<ResumeUploadResponse>('/resumes', { method: 'POST', body: form })
  },

  createBatch: (input: { job_role_id: string; name: string; recruiter_email?: string }) =>
    request<Batch>('/batches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),

  uploadBatchResumes: (batchId: string, files: File[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return request<BulkUploadResponse>(`/batches/${batchId}/resumes`, {
      method: 'POST',
      body: form,
    })
  },
}
