interface Props {
  sourceFile: File | null
  targetFile: File | null
  targetDesc: string
  creativeBrief: string
  onSourceChange: (f: File | null) => void
  onTargetChange: (f: File | null) => void
  onDescChange: (d: string) => void
  onCreativeBriefChange: (d: string) => void
  onRun: () => void
  error: string
}

export default function UploadStep({
  sourceFile, targetFile, targetDesc, creativeBrief,
  onSourceChange, onTargetChange, onDescChange, onCreativeBriefChange, onRun, error,
}: Props) {
  const briefExamples = [
    '突出开头近景手势舞，后面强调主体从近到远变小，不要把跑步当重点。',
    '保留笑场和互动感，节奏轻快，结尾做抖音搜索挑战 CTA。',
    '想要更像校园挑战，先手势动作，再远景环境释放。',
  ]

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 样例视频 */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">📹 样例视频（爆款模板）</h2>
          <FileInput
            file={sourceFile}
            onChange={onSourceChange}
            placeholder="拖拽或点击上传样例视频"
          />
          {sourceFile && (
            <p className="text-sm text-gray-500 mt-2">
              {sourceFile.name} ({(sourceFile.size / 1024 / 1024).toFixed(1)} MB)
            </p>
          )}
        </div>

        {/* 目标视频 */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">🎯 目标视频（要迁移的内容）</h2>
          <FileInput
            file={targetFile}
            onChange={onTargetChange}
            placeholder="拖拽或点击上传目标视频"
          />
          {targetFile && (
            <p className="text-sm text-gray-500 mt-2">
              {targetFile.name} ({(targetFile.size / 1024 / 1024).toFixed(1)} MB)
            </p>
          )}
        </div>
      </div>

      {/* 目标描述（可选） */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">📝 目标内容描述（可选）</h2>
        <textarea
          className="w-full border rounded-lg p-3 text-sm h-24 resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="补充目标视频的主题、风格等信息，留空则自动从视频提取..."
          value={targetDesc}
          onChange={(e) => onDescChange(e.target.value)}
        />
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex flex-col gap-2 mb-4">
          <h2 className="text-lg font-semibold">创作亮点与迁移要求</h2>
          <p className="text-sm text-gray-500">
            写给 AI 的创作提示。可以很口语，系统会先扩写成结构化约束，再参与分析和迁移。
          </p>
        </div>
        <textarea
          className="w-full border rounded-lg p-3 text-sm min-h-28 resize-y focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          placeholder="例如：开头有近景手势舞，后面主体越来越远；不要突出跑步，要突出近到远的操场空间感..."
          value={creativeBrief}
          onChange={(e) => onCreativeBriefChange(e.target.value)}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {briefExamples.map((example) => (
            <button
              key={example}
              type="button"
              className="rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 hover:bg-blue-100 transition-colors"
              onClick={() => onCreativeBriefChange(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm">{error}</div>
      )}

      <button
        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        onClick={onRun}
        disabled={!sourceFile || !targetFile}
      >
        🚀 开始结构迁移
      </button>
    </div>
  )
}

function FileInput({ file, onChange, placeholder }: {
  file: File | null
  onChange: (f: File | null) => void
  placeholder: string
}) {
  const isVideoFile = (candidate: File) => {
    const videoExt = /\.(mp4|mov|m4v|webm|avi|mkv)$/i
    return candidate.type.startsWith('video/') || videoExt.test(candidate.name)
  }

  const handleFile = (candidate: File | undefined) => {
    onChange(candidate && isVideoFile(candidate) ? candidate : null)
  }

  return (
    <label
      className={`block border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${file ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-blue-400'}`}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        handleFile(e.dataTransfer.files?.[0])
      }}
    >
      <input
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      <div className="text-4xl mb-2">{file ? '✅' : '🎬'}</div>
      <p className="text-sm text-gray-500">{file ? file.name : placeholder}</p>
    </label>
  )
}
