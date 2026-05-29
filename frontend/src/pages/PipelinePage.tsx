import { useState } from 'react'
import { runPipeline, PipelineResponse } from '../api/client'
import UploadStep from '../components/UploadStep'
import ResultView from '../components/ResultView'

type Step = 'upload' | 'processing' | 'result'

export default function PipelinePage() {
  const [step, setStep] = useState<Step>('upload')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [targetFile, setTargetFile] = useState<File | null>(null)
  const [targetDesc, setTargetDesc] = useState('')
  const [result, setResult] = useState<PipelineResponse | null>(null)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState('')

  const handleRun = async () => {
    if (!sourceFile || !targetFile) {
      setError('请上传样例视频和目标视频')
      return
    }
    setStep('processing')
    setError('')
    setProgress('正在上传并分析视频...')

    try {
      setProgress('正在分析样例视频结构...')
      const res = await runPipeline(sourceFile, targetFile, targetDesc || undefined)
      setResult(res)
      setStep('result')
    } catch (e: any) {
      setError(e.message || '执行失败')
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
          onSourceChange={setSourceFile}
          onTargetChange={setTargetFile}
          onDescChange={setTargetDesc}
          onRun={handleRun}
          error={error}
        />
      )}

      {step === 'processing' && (
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent mb-4"></div>
          <p className="text-lg text-gray-700">{progress}</p>
          <p className="text-sm text-gray-400 mt-2">这可能需要 1-2 分钟，请耐心等待</p>
        </div>
      )}

      {step === 'result' && result && (
        <ResultView result={result} onBack={() => { setStep('upload'); setResult(null) }} />
      )}
    </div>
  )
}
