import { PipelineResponse } from '../api/client'

interface Props {
  result: PipelineResponse
  onBack: () => void
}

export default function ResultView({ result, onBack }: Props) {
  const { transfer, video, source_meta, target_meta } = result
  const videoUrl = video.url || videoUrlFromPath(video.path)
  const videoFilename = video.filename || filenameFromPath(video.path) || 'transfer-video.mp4'
  const script = transfer.script ?? []
  const storyboard = transfer.storyboard ?? []
  const packaging = transfer.packaging ?? { subtitle_style: '未返回', transitions: '未返回', cover: '未返回' }
  const materialNeeds = transfer.material_needs ?? { 必需素材列表: [], 可选素材列表: [] }
  const requiredMaterials = materialNeeds.必需素材列表 ?? []
  const optionalMaterials = materialNeeds.可选素材列表 ?? []
  const materialCoverage = transfer.material_coverage
  const timelineMetrics = transfer.timeline_metrics
  const coveragePercent = materialCoverage
    ? Math.min(100, Math.max(0, Math.round(materialCoverage.coverage_ratio * 100)))
    : 0

  return (
    <div className="space-y-6">
      {/* 成功提示 */}
      <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
        <span className="text-2xl">✅</span>
        <div className="min-w-0">
          <p className="font-semibold text-green-800">迁移完成！</p>
          <p className="text-sm text-green-600 break-words">
            视频已生成: {video.path} ({video.size_mb} MB)
          </p>
        </div>
      </div>

      {videoUrl && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
            <div>
              <h3 className="text-lg font-semibold">视频预览</h3>
              <p className="text-sm text-gray-500 mt-1">{videoFilename} · {video.size_mb} MB</p>
            </div>
            <a
              className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
              href={videoUrl}
              download={videoFilename}
            >
              下载视频
            </a>
          </div>
          <div className="mx-auto w-full max-w-[360px] overflow-hidden rounded-lg bg-black shadow">
            <video
              className="block w-full aspect-[9/16] bg-black"
              src={videoUrl}
              controls
              playsInline
              preload="metadata"
            />
          </div>
          <p className="text-xs text-gray-400 mt-3 break-words">预览地址: {videoUrl}</p>
        </div>
      )}

      {/* 元信息 */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-sm font-medium text-gray-500 mb-2">样例视频</h3>
          <p className="text-sm">时长: {source_meta.duration.toFixed(1)}s</p>
          <p className="text-sm">分辨率: {source_meta.resolution}</p>
          <p className="text-sm">脚本段数: {source_meta.script_count}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-sm font-medium text-gray-500 mb-2">目标视频</h3>
          <p className="text-sm">时长: {target_meta.duration.toFixed(1)}s</p>
          <p className="text-sm">分辨率: {target_meta.resolution}</p>
        </div>
      </div>

      {/* 新脚本 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">📋 新脚本</h3>
        <div className="space-y-3">
          {script.map((seg, i) => (
            <div key={i} className="border-l-4 border-blue-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded">{seg.type}</span>
                <span className="text-xs text-gray-400">{seg.duration}s</span>
              </div>
              <p className="text-sm font-medium">{seg.text}</p>
              <p className="text-xs text-gray-500 mt-1">{seg.purpose}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-4">
          总时长: {script.reduce((s, g) => s + g.duration, 0)}s
        </p>
      </div>

      {/* 分镜 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">🎞️ 分镜脚本</h3>
        <div className="space-y-4">
          {storyboard.map((shot, i) => (
            <div key={i} className="border rounded-lg p-4">
              <div className="flex items-center gap-3 mb-2">
                <span className="bg-gray-100 text-gray-700 text-xs px-2 py-1 rounded font-mono">
                  #{shot.shot_number}
                </span>
                <span className="bg-purple-100 text-purple-800 text-xs px-2 py-0.5 rounded">{shot.type}</span>
                <span className="text-xs text-gray-400">{shot.duration}s</span>
                <span className="text-xs text-gray-400">{shot.camera_move}</span>
                {shot.edit?.spatial_role && (
                  <span className="bg-amber-100 text-amber-800 text-xs px-2 py-0.5 rounded">
                    {shot.edit.spatial_role}
                  </span>
                )}
              </div>
              <p className="text-sm mb-1">{shot.content}</p>
              {shot.subtitle && (
                <p className="text-sm text-blue-600">字幕: {shot.subtitle}</p>
              )}
              <p className="text-xs text-gray-400 mt-1">素材: {shot.source}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 包装 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">🎨 包装方案</h3>
        <div className="space-y-2 text-sm">
          <p><span className="font-medium">字幕风格:</span> {packaging.subtitle_style}</p>
          <p><span className="font-medium">转场方案:</span> {packaging.transitions}</p>
          <p><span className="font-medium">封面方案:</span> {packaging.cover}</p>
        </div>
      </div>

      {/* 迁移可视化 */}
      {(materialCoverage || timelineMetrics) && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">🧭 迁移过程可视化</h3>
          {timelineMetrics && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <Metric label="成片时长" value={`${timelineMetrics.total_duration}s`} />
              <Metric label="目标素材段" value={timelineMetrics.source_range_count} />
              <Metric label="CTA补全" value={timelineMetrics.cta_added ? '已生成' : '未新增'} />
              <Metric label="空间角色" value={timelineMetrics.spatial_roles.join(' → ') || '未标注'} />
            </div>
          )}
          {materialCoverage && (
            <div className="space-y-4">
              <div className="border rounded-lg p-4 bg-gray-50">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-600">素材覆盖率</span>
                  <span className="text-sm font-semibold text-gray-900">{coveragePercent}%</span>
                </div>
                <div className="h-2 rounded-full bg-gray-200 overflow-hidden">
                  <div className="h-full bg-blue-600" style={{ width: `${coveragePercent}%` }} />
                </div>
                <p className="text-xs text-gray-500 mt-2">{materialCoverage.filling_summary}</p>
              </div>
              {materialCoverage.gaps.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-500 mb-2">缺口与补全</h4>
                  {materialCoverage.gaps.map((gap, i) => (
                    <div key={i} className="text-sm border-l-2 border-amber-300 pl-3 py-1 mb-2">
                      <span className="font-medium">#{gap.shot_number} {gap.gap_type}</span>
                      <span className="text-xs text-gray-400 ml-2">{gap.severity}</span>
                      <p className="text-xs text-gray-500">{gap.filling_strategy}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 素材需求 */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">📦 素材需求</h3>
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-medium text-gray-500 mb-2">必需素材</h4>
            {requiredMaterials.map((m, i) => (
              <div key={i} className="text-sm border-l-2 border-red-300 pl-3 py-1 mb-2">
                <span className="text-red-600 font-medium">{m.type}</span>: {m.description}
                <p className="text-xs text-gray-400">{m.purpose}</p>
              </div>
            ))}
            {requiredMaterials.length === 0 && (
              <p className="text-sm text-gray-400">无额外必需素材。</p>
            )}
          </div>
          <div>
            <h4 className="text-sm font-medium text-gray-500 mb-2">可选素材</h4>
            {optionalMaterials.map((m, i) => (
              <div key={i} className="text-sm border-l-2 border-gray-300 pl-3 py-1 mb-2">
                <span className="text-gray-600 font-medium">{m.type}</span>: {m.description}
                <p className="text-xs text-gray-400">{m.purpose}</p>
              </div>
            ))}
            {optionalMaterials.length === 0 && (
              <p className="text-sm text-gray-400">无额外可选素材。</p>
            )}
          </div>
        </div>
      </div>

      {/* 返回按钮 */}
      <button
        className="w-full bg-gray-200 hover:bg-gray-300 text-gray-700 font-medium py-3 rounded-lg transition-colors"
        onClick={onBack}
      >
        ← 返回重新上传
      </button>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-white p-3">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-sm font-semibold text-gray-800 break-words">{value}</p>
    </div>
  )
}

function videoUrlFromPath(path: string) {
  const filename = filenameFromPath(path)
  return filename ? `/api/pipeline/videos/${encodeURIComponent(filename)}` : ''
}

function filenameFromPath(path: string) {
  return path.split(/[\\/]/).filter(Boolean).pop() || ''
}
