interface Props {
  sourceFile: File | null
  targetFile: File | null
  targetDesc: string
  onSourceChange: (f: File | null) => void
  onTargetChange: (f: File | null) => void
  onDescChange: (d: string) => void
  onRun: () => void
  error: string
}

export default function UploadStep({
  sourceFile, targetFile, targetDesc,
  onSourceChange, onTargetChange, onDescChange, onRun, error,
}: Props) {
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
  return (
    <label className={`block border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${file ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-blue-400'}`}>
      <input
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] || null)}
      />
      <div className="text-4xl mb-2">{file ? '✅' : '🎬'}</div>
      <p className="text-sm text-gray-500">{file ? file.name : placeholder}</p>
    </label>
  )
}
