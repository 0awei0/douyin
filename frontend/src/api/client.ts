const BASE_URL = '/api'

async function readError(res: Response, fallback: string): Promise<Error> {
  let detail = ''
  try {
    const data = await res.json()
    detail = typeof data?.detail === 'string' ? data.detail : JSON.stringify(data)
  } catch {
    detail = await res.text().catch(() => '')
  }
  return new Error(`${fallback}: ${detail || res.statusText || res.status}`)
}

export interface UploadResponse {
  file_id: string
  filename: string
  path: string
  size: number
}

export interface AnalyzeResponse {
  status: string
  structure: VideoStructure
}

export interface TransferResponse {
  status: string
  transfer_id: string
  result_path: string
  result: TransferResult
  source_meta: VideoMeta
  target_meta: VideoMeta
}

export interface GenerateResponse {
  status: string
  video_id: string
  video_path: string
  size_mb: number
}

export interface PipelineResponse {
  status: string
  run_id: string
  source_meta: VideoMeta
  target_meta: VideoMeta
  transfer: TransferResult
  video: {
    path: string
    url?: string
    filename?: string
    size_mb: number
  }
}

export interface PipelineProgressEvent {
  type: 'progress' | 'result' | 'error'
  step: string
  status: 'running' | 'done' | 'error'
  title: string
  message: string
  detail?: Record<string, unknown>
  result?: PipelineResponse
}

export interface VideoMeta {
  duration: number
  resolution: string
  script_count?: number
  shot_count?: number
}

export interface VideoStructure {
  meta: {
    duration: number
    resolution: string
    fps: number
    file_size: number
  }
  script_structure: ScriptSection[]
  shots: Shot[]
  audio_structure: {
    bgm: { name: string; mood: string }
    voiceover: { has: boolean; style: string }
    rhythm_sync: string
  }
  packaging_structure: {
    subtitle_style: { font_size: string; color: string }
    transitions: Array<{ type: string; time: number }>
    overall_visual_tone: string
  }
  transferable_features: {
    hook_strategy: string
    narrative_pattern: string
    pacing_pattern: string
    engagement_techniques: string[]
  }
}

export interface ScriptSection {
  type: string
  start_time: number
  end_time: number
  text: string
  purpose: string
}

export interface Shot {
  type: string
  start_time: number
  end_time: number
  content: string
  camera_move: string
  has_subtitle: boolean
}

export interface TransferResult {
  script: Array<{
    type: string
    text: string
    purpose: string
    duration: number
  }>
  storyboard: Array<{
    shot_number: number
    type: string
    content: string
    duration: number
    camera_move: string
    subtitle: string
    source: string
    edit?: {
      crop?: string
      speed?: number
      pace?: string
      spatial_role?: string
    }
  }>
  packaging: {
    subtitle_style: string
    transitions: string
    cover: string
  }
  material_needs: {
    必需素材列表: Array<{ type: string; description: string; purpose: string }>
    可选素材列表: Array<{ type: string; description: string; purpose: string }>
  }
  timeline_metrics?: {
    total_duration: number
    source_range_count: number
    source_ranges: number[][]
    target_duration: number | null
    cta_added: boolean
    spatial_roles: string[]
  }
  material_coverage?: {
    source_material_slots: number
    matched_source_slots: number
    generated_or_packaging_slots: number
    coverage_ratio: number
    filling_summary: string
    matches: Array<{
      shot_number: number
      source: string
      time_range: number[]
      spatial_role: string
      match_quality: string
      note: string
    }>
    gaps: Array<{
      shot_number: number
      gap_type: string
      severity: string
      spatial_role: string
      filling_strategy: string
      note: string
    }>
  }
}

export async function uploadVideo(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${BASE_URL}/analyze/upload`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw await readError(res, '上传失败')
  return res.json()
}

export async function analyzeStructure(videoPath: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/analyze/structure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_path: videoPath }),
  })
  if (!res.ok) throw await readError(res, '分析失败')
  return res.json()
}

export async function runTransfer(
  sourceVideoPath: string,
  targetVideoPath: string,
  targetDescription?: string,
): Promise<TransferResponse> {
  const params = new URLSearchParams({
    source_video_path: sourceVideoPath,
    target_video_path: targetVideoPath,
  })
  if (targetDescription) params.set('target_description', targetDescription)
  const res = await fetch(`${BASE_URL}/transfer/?${params}`, { method: 'POST' })
  if (!res.ok) throw await readError(res, '迁移失败')
  return res.json()
}

export async function generateVideo(
  transferId: string,
  targetVideoPath: string,
  useAiImage = true,
): Promise<GenerateResponse> {
  const params = new URLSearchParams({
    transfer_id: transferId,
    target_video_path: targetVideoPath,
    use_ai_image: String(useAiImage),
  })
  const res = await fetch(`${BASE_URL}/generate/?${params}`, { method: 'POST' })
  if (!res.ok) throw await readError(res, '生成失败')
  return res.json()
}

export async function runPipeline(
  sourceVideo: File,
  targetVideo: File,
  targetDescription?: string,
): Promise<PipelineResponse> {
  const formData = new FormData()
  formData.append('source_video', sourceVideo)
  formData.append('target_video', targetVideo)
  if (targetDescription) formData.append('target_description', targetDescription)
  const res = await fetch(`${BASE_URL}/pipeline/run`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw await readError(res, '流水线失败')
  return res.json()
}

export async function runPipelineStream(
  sourceVideo: File,
  targetVideo: File,
  targetDescription: string | undefined,
  onEvent: (event: PipelineProgressEvent) => void,
): Promise<PipelineResponse> {
  const formData = new FormData()
  formData.append('source_video', sourceVideo)
  formData.append('target_video', targetVideo)
  if (targetDescription) formData.append('target_description', targetDescription)
  formData.append('use_frame_audit', 'false')

  const res = await fetch(`${BASE_URL}/pipeline/run/stream`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw await readError(res, '流水线失败')
  if (!res.body) throw new Error('当前浏览器不支持流式响应')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: PipelineResponse | null = null

  const handleLine = (line: string) => {
    const trimmed = line.trim()
    if (!trimmed) return
    const event = JSON.parse(trimmed) as PipelineProgressEvent
    onEvent(event)
    if (event.type === 'error') {
      throw new Error(event.message || '流水线执行失败')
    }
    if (event.type === 'result' && event.result) {
      finalResult = event.result
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      handleLine(line)
    }
  }

  buffer += decoder.decode()
  handleLine(buffer)

  if (!finalResult) throw new Error('流水线没有返回最终结果')
  return finalResult
}
