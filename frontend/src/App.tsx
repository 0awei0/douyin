import PipelinePage from './pages/PipelinePage'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <h1 className="text-xl font-bold text-gray-900">爆款结构迁移引擎</h1>
          <p className="text-sm text-gray-500 mt-1">上传样例视频 → 拆解结构 → 迁移到新内容 → 生成新视频</p>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <PipelinePage />
      </main>
    </div>
  )
}
