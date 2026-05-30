import { useState } from 'react'
import { PipelineProgressEvent, PipelineResponse, runPipelineStream } from '../api/client'
import UploadStep from '../components/UploadStep'
import ResultView from '../components/ResultView'

type Step = 'upload' | 'processing' | 'result'

export default function PipelinePage() {
  const [step, setStep] = useState<Step>('upload')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [targetFile, setTargetFile] = useState<File | null>(null)
  const [targetDesc, setTargetDesc] = useState('')
  const [creativeBrief, setCreativeBrief] = useState('')
  const [result, setResult] = useState<PipelineResponse | null>(null)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState('')
  const [progressEvents, setProgressEvents] = useState<PipelineProgressEvent[]>([])

  const handleRun = async () => {
    if (!sourceFile || !targetFile) {
      setError('请上传样例视频和目标视频')
      return
    }
    setStep('processing')
    setError('')
    setProgress('准备上传视频...')
    setProgressEvents([])

    try {
      const res = await runPipelineStream(
        sourceFile,
        targetFile,
        targetDesc || undefined,
        creativeBrief || undefined,
        (event) => {
          setProgress(event.title)
          setProgressEvents((events) => [...events, event])
        },
      )
      setResult(res)
      setStep('result')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '执行失败')
      setStep('upload')
    }
  }

  return (
    <div className="space-y-6">
      {step === 'upload' && (
        <UploadStep
          sourceFile={sourceFile}
          targetFile={targetFile}
          targetDesc={targetDesc}
          creativeBrief={creativeBrief}
          onSourceChange={setSourceFile}
          onTargetChange={setTargetFile}
          onDescChange={setTargetDesc}
          onCreativeBriefChange={setCreativeBrief}
          onRun={handleRun}
          error={error}
        />
      )}

      {step === 'processing' && (
        <ProcessingView events={progressEvents} progress={progress} />
      )}

      {step === 'result' && result && (
        <ResultView result={result} onBack={() => { setStep('upload'); setResult(null) }} />
      )}
    </div>
  )
}

const FLOW_STEPS = [
  { key: 'upload', label: '上传素材' },
  { key: 'brief', label: '创作意图扩写' },
  { key: 'source_analysis', label: '爆款样例分析' },
  { key: 'target_analysis', label: '目标素材分析' },
  { key: 'transfer', label: '结构迁移' },
  { key: 'render', label: '视频生成' },
  { key: 'complete', label: '完成' },
]

function ProcessingView({ events, progress }: { events: PipelineProgressEvent[]; progress: string }) {
  const visibleEvents = events.filter((event) => event.type !== 'result')

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
      <div className="bg-white rounded-lg shadow p-6 self-start">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-full border-4 border-blue-500 border-t-transparent animate-spin" />
          <div>
            <p className="font-semibold text-gray-900">{progress || '正在处理...'}</p>
            <p className="text-sm text-gray-500">分析和迁移结果会实时出现在右侧。</p>
          </div>
        </div>

        <div className="space-y-4">
          {FLOW_STEPS.map((item) => {
            const event = latestEventForStep(events, item.key)
            const status = event?.status ?? 'waiting'
            return (
              <div key={item.key} className="flex gap-3">
                <StepDot status={status} />
                <div className="min-w-0">
                  <p className={`text-sm font-medium ${status === 'waiting' ? 'text-gray-400' : 'text-gray-900'}`}>
                    {item.label}
                  </p>
                  {event && (
                    <p className="text-xs text-gray-500 break-words">{event.message}</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">实时输出</h2>
          <span className="text-xs text-gray-400">{visibleEvents.length} 条更新</span>
        </div>

        <div className="space-y-4">
          {visibleEvents.length === 0 && (
            <div className="border border-dashed rounded-lg p-6 text-sm text-gray-400">
              等待后端返回第一条处理进度...
            </div>
          )}
          {visibleEvents.map((event, index) => (
            <ProgressEventCard key={`${event.step}-${event.status}-${index}`} event={event} />
          ))}
        </div>
      </div>
    </div>
  )
}

function StepDot({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <span className="mt-1 flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-[11px] font-bold text-white">
        ✓
      </span>
    )
  }
  if (status === 'running') {
    return <span className="mt-1 h-5 w-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
  }
  if (status === 'error') {
    return (
      <span className="mt-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[11px] font-bold text-white">
        !
      </span>
    )
  }
  return <span className="mt-1 h-5 w-5 rounded-full border-2 border-gray-200 bg-gray-50" />
}

function ProgressEventCard({ event }: { event: PipelineProgressEvent }) {
  const borderColor = event.status === 'done' ? 'border-green-200' : event.status === 'error' ? 'border-red-200' : 'border-blue-200'
  const bgColor = event.status === 'done' ? 'bg-green-50/40' : event.status === 'error' ? 'bg-red-50/40' : 'bg-blue-50/40'

  return (
    <div className={`border ${borderColor} ${bgColor} rounded-lg p-4`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-gray-900">{event.title}</p>
          <p className="text-sm text-gray-500 mt-1">{event.message}</p>
        </div>
        <span className="shrink-0 rounded-full bg-white px-2 py-1 text-xs text-gray-500 border">
          {event.status === 'running' ? '进行中' : event.status === 'done' ? '完成' : '失败'}
        </span>
      </div>
      <EventDetail event={event} />
    </div>
  )
}

function EventDetail({ event }: { event: PipelineProgressEvent }) {
  const detail = event.detail
  if (!detail || Object.keys(detail).length === 0) return null

  if (event.step === 'upload') {
    return (
      <DetailGrid
        items={[
          ['任务 ID', textValue(detail, 'run_id')],
          ['样例文件', textValue(detail, 'source_file')],
          ['目标文件', textValue(detail, 'target_file')],
          ['样例大小', sizeValue(detail, 'source_size_mb')],
          ['目标大小', sizeValue(detail, 'target_size_mb')],
        ]}
      />
    )
  }

  if (event.step === 'source_analysis' || event.step === 'target_analysis') {
    const keyShots = arrayValue(detail, 'key_shots')
    return (
      <div className="mt-4 space-y-4">
        <DetailGrid
          items={[
            ['时长', secondsValue(detail, 'duration')],
            ['分辨率', textValue(detail, 'resolution')],
            ['脚本段数', textValue(detail, 'script_count')],
            ['镜头数', textValue(detail, 'shot_count')],
          ]}
        />
        <SummaryText label="Hook" value={textValue(detail, 'hook_strategy')} />
        <SummaryText label="节奏" value={textValue(detail, 'pacing_pattern')} />
        <SummaryText label="空间轨迹" value={textValue(detail, 'spatial_pattern') || textValue(detail, 'subject_trajectory')} />
        {keyShots.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">关键镜头</p>
            <div className="space-y-2">
              {keyShots.map((shot, index) => (
                <div key={index} className="rounded border bg-white/70 p-3 text-xs text-gray-600">
                  <p className="font-medium text-gray-800">
                    {textValue(shot, 'time')} · {textValue(shot, 'type')}
                  </p>
                  <p className="mt-1">{textValue(shot, 'content')}</p>
                  {(textValue(shot, 'distance') || textValue(shot, 'motion')) && (
                    <p className="mt-1 text-gray-400">
                      {textValue(shot, 'distance')} {textValue(shot, 'motion')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (event.step === 'brief') {
    const brief = objectValue(detail, 'creative_brief')
    return (
      <div className="mt-4 space-y-3">
        <SummaryText label="意图摘要" value={textValue(brief, 'summary')} />
        <SummaryText label="迁移优先级" value={listValue(brief, 'transfer_priority').join(' / ')} />
        <SummaryText label="避免误判" value={listValue(brief, 'avoid_focus').join(' / ')} />
      </div>
    )
  }

  if (event.step === 'transfer') {
    return (
      <div className="mt-4 space-y-3">
        <DetailGrid
          items={[
            ['分镜数', textValue(detail, 'storyboard_count')],
            ['脚本段数', textValue(detail, 'script_count')],
            ['成片时长', secondsValue(detail, 'total_duration')],
            ['素材覆盖', percentValue(detail, 'coverage_ratio')],
          ]}
        />
        <SummaryText label="空间角色链" value={listValue(detail, 'spatial_roles').join(' → ')} />
        <SummaryText label="补全策略" value={textValue(detail, 'filling_summary')} />
        <SummaryText label="时间线" value={textValue(detail, 'transfer_path')} />
      </div>
    )
  }

  if (event.step === 'render') {
    return (
      <DetailGrid
        items={[
          ['视频路径', textValue(detail, 'video_path')],
          ['文件大小', sizeValue(detail, 'size_mb')],
        ]}
      />
    )
  }

  return null
}

function DetailGrid({ items }: { items: Array<[string, string]> }) {
  const visibleItems = items.filter(([, value]) => value)
  if (visibleItems.length === 0) return null
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
      {visibleItems.map(([label, value]) => (
        <div key={label} className="rounded border bg-white/70 p-3">
          <p className="text-xs text-gray-400 mb-1">{label}</p>
          <p className="text-sm text-gray-800 break-words">{value}</p>
        </div>
      ))}
    </div>
  )
}

function SummaryText({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
      <p className="text-sm text-gray-700 leading-relaxed">{value}</p>
    </div>
  )
}

function latestEventForStep(events: PipelineProgressEvent[], step: string) {
  return events.slice().reverse().find((event) => event.step === step)
}

function textValue(detail: Record<string, unknown>, key: string) {
  const value = detail[key]
  if (value === null || value === undefined) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return ''
}

function arrayValue(detail: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = detail[key]
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : []
}

function objectValue(detail: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = detail[key]
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function listValue(detail: Record<string, unknown>, key: string): string[] {
  const value = detail[key]
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function secondsValue(detail: Record<string, unknown>, key: string) {
  const value = textValue(detail, key)
  return value ? `${value}s` : ''
}

function sizeValue(detail: Record<string, unknown>, key: string) {
  const value = textValue(detail, key)
  return value ? `${value} MB` : ''
}

function percentValue(detail: Record<string, unknown>, key: string) {
  const value = detail[key]
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : ''
}
