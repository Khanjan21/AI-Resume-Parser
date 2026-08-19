export type ExperienceLevel = 'entry' | 'junior' | 'mid' | 'senior' | 'lead'
export type ParseStatus = 'pending' | 'processing' | 'parsed' | 'failed'
export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type UploadSource = 'candidate' | 'recruiter'
export type ShortlistCategory = 'strong_match' | 'consider' | 'weak_match'
export type BatchStatus =
  | 'created'
  | 'uploading'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'

export interface JobRoleSummary {
  id: string
  slug: string
  title: string
  category: string
  summary: string
  default_level: ExperienceLevel
  min_experience_years: number
  max_experience_years: number | null
  required_skills: string[]
  is_active: boolean
}

export interface JobRoleDetail extends JobRoleSummary {
  description: string
  preferred_skills: string[]
  nice_to_have_skills: string[]
  responsibilities: string[]
  education: string[]
  ats_keywords: string[]
  scoring_weights: Record<string, number>
  is_system: boolean
  created_at: string
  updated_at: string
}

export interface PageMeta {
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface Page<T> {
  items: T[]
  meta: PageMeta
}

export interface Resume {
  id: string
  job_role_id: string | null
  batch_id: string | null
  candidate_id: string | null
  job_description_id: string | null
  upload_source: UploadSource
  original_filename: string
  file_extension: string
  content_type: string
  file_size_bytes: number
  content_hash: string
  parse_status: ParseStatus
  parse_error: string | null
  analysis_status: AnalysisStatus
  analysis_error: string | null
  word_count: number | null
  page_count: number | null
  created_at: string
  updated_at: string
}

export interface ResumeScore {
  id: string
  resume_id: string
  job_role_id: string | null
  job_description_id: string | null
  ats_score: number
  matched_ats_keywords: string[]
  required_skill_match: number
  matched_skills: string[]
  missing_skills: string[]
  experience_match: number
  candidate_experience_years: number | null
  suggestions: string[]
  semantic_score: number | null
  final_score: number | null
  category: ShortlistCategory | null
  scored_at: string
}

export interface ResumeDetail extends Resume {
  raw_text: string | null
  parsed_data: Record<string, unknown>
  score: ResumeScore | null
}

export interface ResumeUploadResponse {
  resume: Resume
  duplicate: boolean
  message: string
}

export interface BulkUploadItem {
  filename: string
  status: 'uploaded' | 'duplicate' | 'rejected'
  resume_id: string | null
  error_code: string | null
  error: string | null
}

export interface BulkUploadResponse {
  batch_id: string
  received: number
  uploaded: number
  duplicates: number
  rejected: number
  items: BulkUploadItem[]
}

export interface Batch {
  id: string
  job_role_id: string
  job_description_id: string | null
  name: string
  recruiter_email: string | null
  notes: string | null
  status: BatchStatus
  total_resumes: number
  parsed_resumes: number
  failed_resumes: number
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface BatchCategoryCounts {
  strong_match: number
  consider: number
  weak_match: number
  unscored: number
}

export interface BatchDetail extends Batch {
  job_role: JobRoleSummary | null
  resumes: ResumeDetail[]
  category_counts: BatchCategoryCounts
}

export interface JobDescription {
  id: string
  job_role_id: string | null
  title: string
  company: string | null
  location: string | null
  source_filename: string | null
  parse_status: ParseStatus
  parse_error: string | null
  parsed_at: string | null
  created_at: string
  updated_at: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}
