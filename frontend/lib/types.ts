export type ProjectStatus =
  | "DRAFT"
  | "PLANNING"
  | "AWAITING_APPROVAL"
  | "QUEUED"
  | "GENERATING"
  | "PROCESSING"
  | "VALIDATING"
  | "COMPLETED"
  | "FAILED"
  | "PAUSED"
  | "CANCELLED";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  role: string;
  storage_used_bytes: number;
  created_at: string;
}

export interface AuthResponse {
  user: User;
  csrf_token: string;
}

export interface Scene {
  id: string;
  project_id: string;
  scene_number: number;
  title: string;
  narrative_purpose: string | null;
  duration: number;
  environment: string | null;
  character_presence: string[] | null;
  actions: string | null;
  camera: string | null;
  lighting: string | null;
  visual_style: string | null;
  prompt: string;
  negative_prompt: string | null;
  continuity: string | null;
  narration: string | null;
  dialogue: string | null;
  status: "PENDING" | "SUBMITTING" | "GENERATING" | "DOWNLOADING" | "SUCCEEDED" | "FAILED";
  generation_id: string | null;
  provider_status: string | null;
  attempt_count: number;
  download_status: string;
  error: string | null;
  duration_actual: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Project {
  id: string;
  title: string;
  script: string;
  genre: string | null;
  logline: string | null;
  style: string;
  orientation: string;
  aspect_ratio: string;
  target_duration_seconds: number;
  target_scene_count: number;
  scene_seconds: number;
  tier: string;
  resolution: string;
  quality: string;
  provider: string;
  execution_mode: "cloud" | "local";
  executor: string | null;
  status: ProjectStatus;
  progress: number;
  error: string | null;
  auto_start: boolean;
  plan_revision: number;
  final_video_id: string | null;
  report: Record<string, unknown> | null;
  voiceover_instructions: string | null;
  music_instructions: string | null;
  reference_notes: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  scenes: Scene[];
  characters: Character[];
  active_job: Job | null;
}

export interface Character {
  id: string;
  name: string;
  age_range: string | null;
  description: string;
  appearance: Record<string, unknown> | null;
  voice_description: string | null;
  reference_notes: string | null;
  position: number;
}

export interface Job {
  id: string;
  project_id: string | null;
  kind: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  available_at: string;
  created_at: string;
  updated_at: string;
}

export interface Video {
  id: string;
  project_id: string | null;
  scene_id: string | null;
  kind: "final" | "scene";
  filename: string;
  size_bytes: number;
  mime_type: string;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean;
  checksum_sha256: string | null;
  created_at: string;
  stream_url: string | null;
  download_url: string | null;
  thumbnail_url: string | null;
}

export interface Provider {
  provider: string;
  display_name: string;
  description: string;
  status: string;
  connectable: boolean;
  requires_consent: boolean;
  connected: boolean;
  account_ref: string | null;
  usage: Record<string, unknown> | null;
  last_verified_at: string | null;
  notes: string | null;
}

export interface PublicConfig {
  app_name: string;
  environment: string;
  execution_mode: "cloud" | "local";
  simulated_provider_enabled: boolean;
  taaft_enabled: boolean;
  max_scenes_per_project: number;
  max_scene_seconds: number;
  max_reference_upload_mb: number;
  push_configured: boolean;
}

export interface Usage {
  projects_total: number;
  projects_active: number;
  videos_total: number;
  scenes_generated: number;
  storage_used_bytes: number;
  storage_quota_bytes: number;
  generations_this_month: number;
}

export interface Notification {
  id: string;
  project_id: string | null;
  kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
}

export interface LocalToken {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface LocalTokenCreated extends LocalToken {
  token: string;
}

export interface ExecutionStatus {
  execution_mode: "cloud" | "local";
  cloud_workers_enabled: boolean;
  local_workers_enabled: boolean;
  active_tokens: number;
  instructions: string;
}

export interface ProjectList {
  items: Project[];
  total: number;
}

export interface VideoList {
  items: Video[];
  total: number;
}
