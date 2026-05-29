# VideoMaker Competition MVP Design

Date: 2026-05-29

## Goal

Build a TypeScript full-stack MVP for the competition task. The system analyzes a reference video, extracts reusable video structure, accepts new content/material inputs, and produces a structured generation brief that can guide later video generation.

The MVP is not a full video editor and does not need to render the final generated video in the first phase. Its first deliverable is a transparent, reviewable pipeline that outputs:

- `VideoStructure`: reference video structure analysis.
- `GenerationBrief`: structured guidance for making a new video from the learned structure.
- `ValidationReport`: evidence that the output covers competition scoring dimensions.

## Competition Alignment

The design is adjusted around the competition requirements shown by the user:

- Basic capability: reference video input and analysis.
- Structure decomposition: complete at least two of three structure categories.
- New content/material input.
- Structured generation guidance.
- Material processing when source material is insufficient.
- Process and result visualization.
- Optional advanced generation features later.

For MVP scoring, the priority is:

1. Structure decomposition.
2. Generation guidance.
3. Process visualization and validation.
4. Material planning and shortage detection.

The MVP should cover all three structure categories, while ensuring at least rhythm structure and packaging structure are stable enough for demo use.

## Product Shape

Use方案 2: Core + CLI + Web Workbench.

```txt
packages/
  core/     # schemas, agents, prompts, adapters, pipeline
  cli/      # command line entry for repeatable parsing jobs

apps/
  web/      # local workbench for review, calibration, visualization, export
```

The workflow:

```txt
Reference video + context + new content/materials
  -> CLI parse command
  -> core agent pipeline
  -> job directory with intermediate artifacts
  -> Web workbench review and calibration
  -> exported VideoStructure + GenerationBrief + ValidationReport
```

The CLI is an engineering and demo entry point. It lets us run reproducible jobs before building a full upload/task system in the Web app.

## Non-Goals For MVP

- No full timeline editor.
- No advanced drag-and-drop video editing.
- No local model training.
- No hard dependency on final video rendering.
- No requirement to support every video genre.

The selected first genre focus is entertainment remix / meme-style videos, but the protocol is structured around the competition's three decomposition categories.

## Core Protocols

### VideoStructure

`VideoStructure` describes what the reference video is doing.

```ts
type VideoStructure = {
  schemaVersion: "1.0";
  structureId: string;
  sourceVideo: SourceVideo;
  userContext?: UserContext;

  scriptStructure: ScriptStructure;
  rhythmStructure: RhythmStructure;
  packagingStructure: PackagingStructure;

  segments: Segment[];
  shots: Shot[];
  beatPoints: BeatPoint[];
  packagingElements: PackagingElement[];

  reviewStatus: ReviewStatus;
  metadata?: Record<string, unknown>;
  experimental?: Record<string, unknown>;
};
```

Structure categories:

- `scriptStructure`: hook, setup, development, punchline/reversal/climax, CTA/end.
- `rhythmStructure`: shot-switch frequency, slow/fast sections, beat sync, climax location, repetition pattern.
- `packagingStructure`: subtitle density, title bars, stickers, memes, transitions, cover style.

Every important inferred field should carry provenance:

```ts
type FieldEvidence<T> = {
  value: T;
  source: "ai" | "user" | "derived";
  confidence: number;
  needsReview: boolean;
  evidenceRefs?: string[];
};
```

### GenerationBrief

`GenerationBrief` describes how to create a new video using the learned structure.

```ts
type GenerationBrief = {
  schemaVersion: "1.0";
  briefId: string;
  basedOnStructureId: string;
  targetContent: TargetContentInput;

  scriptPlan: ScriptPlan;
  storyboard: StoryboardShot[];
  editingPlan: EditingPlan;
  packagingPlan: PackagingPlan;
  materialPlan: MaterialPlan;

  validationNotes: ValidationNote[];
  metadata?: Record<string, unknown>;
  experimental?: Record<string, unknown>;
};
```

The brief should map new content to the reference structure:

- Which reference segment each new segment follows.
- Which rhythm pattern should be reused.
- Which packaging elements should be reused or adapted.
- Which assets are available, missing, or need generation.

### ValidationReport

`ValidationReport` is demo evidence and a development guardrail.

```ts
type ValidationReport = {
  jobId: string;
  generatedAt: string;
  structureCoverage: {
    scriptStructure: CoverageResult;
    rhythmStructure: CoverageResult;
    packagingStructure: CoverageResult;
  };
  materialCoverage: CoverageResult;
  generationBriefCoverage: CoverageResult;
  visualizationReadiness: CoverageResult;
  missingItems: string[];
  needsReview: string[];
};
```

It should directly explain which competition scoring dimensions are covered and where the system still needs manual review.

## Agent Pipeline

Agents are TypeScript modules with typed inputs and outputs:

```ts
type Agent<I, O> = {
  name: string;
  run(input: I, context: AgentContext): Promise<O>;
};
```

`AgentContext` contains job paths, logger, prompt registry, schema validators, and pluggable adapters.

```ts
type AgentContext = {
  jobId: string;
  workDir: string;
  logger: Logger;
  adapters: {
    asr: ASRAdapter;
    ocr: OCRAdapter;
    vision: VisionAdapter;
    llm: LLMAdapter;
  };
};
```

Pipeline v1:

1. `MediaPreprocessAgent`
   - Probe metadata with FFmpeg.
   - Extract audio.
   - Extract keyframes.
   - Produce shot boundary candidates.

2. `TranscriptionOcrAgent`
   - Run ASR on extracted audio.
   - Run OCR on keyframes.
   - Save transcript and OCR evidence.

3. `StructureAnalysisAgent`
   - Build `scriptStructure`, `rhythmStructure`, and `packagingStructure`.
   - Produce `segments`, `shots`, `beatPoints`, and `packagingElements`.
   - Mark confidence and review needs.

4. `MaterialPlanningAgent`
   - Analyze provided new materials.
   - Detect usable and missing assets.
   - Produce material matching and shortage notes.

5. `GenerationBriefAgent`
   - Convert target content plus `VideoStructure` into a `GenerationBrief`.
   - Generate script, storyboard, editing, packaging, and material plans.

6. `ValidationAgent`
   - Validate schemas with Zod.
   - Generate `ValidationReport`.
   - Mark missing items and review risks.

## Prompt Management

Prompts should not be embedded inline inside agent logic. Store prompt builders under `packages/core/src/prompts/`.

Example structure:

```txt
packages/core/src/prompts/
  structureAnalysis.prompt.ts
  rhythmAnalysis.prompt.ts
  packagingAnalysis.prompt.ts
  generationBrief.prompt.ts
  validation.prompt.ts
```

Prompt builders accept structured data and return model messages. Agent code only assembles inputs, calls adapters, validates outputs, and writes artifacts.

Each prompt should have:

- Stable prompt ID.
- Version.
- Input contract.
- Output schema name.
- Short description of expected behavior.

LLM outputs must be JSON only and must pass Zod validation before being accepted.

## Model Strategy

Default to cloud models for MVP speed and quality:

- Local FFmpeg preprocessing.
- Cloud ASR/OCR/vision/LLM by default.
- Local cache of model inputs and outputs.

Keep all model calls behind adapters:

```txt
ASRAdapter
OCRAdapter
VisionAdapter
LLMAdapter
```

This keeps the implementation replaceable with local Whisper, local OCR, ComfyUI, or other services later.

## CLI And Job Directory

CLI command shape:

```bash
videomaker parse \
  --video ./samples/demo.mp4 \
  --context ./samples/context.md \
  --materials ./samples/materials \
  --target ./samples/target.md \
  --out ./runs/demo-001
```

Job directory:

```txt
runs/demo-001/
  input.json

  media/
    audio.wav
    frames/
      0001.jpg
      0002.jpg

  intermediate/
    media-probe.json
    transcript.json
    ocr.json
    shot-candidates.json
    structure-analysis.json
    material-analysis.json

  video-structure.draft.json
  generation-brief.draft.json
  validation-report.json
```

This supports replay, debugging, demo evidence, and Web workbench loading without rerunning models.

## Web Workbench

The Web workbench is for calibration, visualization, and export.

Main areas:

1. Video and input panel
   - Reference video preview.
   - Target content input.
   - Material list.
   - Job status.

2. Process panel
   - Transcript.
   - OCR.
   - Keyframes.
   - Shot candidates.
   - Agent output summaries.

3. Structure decomposition tabs
   - Script/segment structure.
   - Rhythm structure.
   - Packaging structure.

4. Generation guidance tab
   - Script plan.
   - Storyboard.
   - Editing plan.
   - Packaging plan.
   - Material plan.

5. Validation and export tab
   - Competition coverage summary.
   - Missing items.
   - Needs-review list.
   - Export JSON files.

MVP interaction uses tables and structured panels. Timecodes are editable. Fields can be marked reviewed. Full timeline editing is deferred.

## Testing And Acceptance

### Schema Tests

- `VideoStructure` accepts valid outputs.
- `GenerationBrief` accepts valid outputs.
- Missing core fields fail validation.
- `metadata` and `experimental` remain forward-compatible.

### Pipeline Tests

Use fixed sample inputs and mock adapter outputs to verify:

- CLI creates a job directory.
- Intermediate artifacts are written.
- Draft JSON files are produced.
- Validation report is produced.

### Demo Acceptance

A demo run is acceptable when it can show:

- Reference video input.
- At least two stable structure categories.
- New content/material input.
- Generated `GenerationBrief`.
- Process visualization evidence.
- Validation report mapped to competition scoring dimensions.

## Implementation Order

1. Create TypeScript monorepo skeleton.
2. Define Zod schemas for `VideoStructure`, `GenerationBrief`, and `ValidationReport`.
3. Implement job directory and artifact writer.
4. Implement adapter interfaces and mock adapters.
5. Implement pipeline agents with mock outputs.
6. Implement CLI `parse`.
7. Add Web workbench that loads an existing job directory.
8. Replace mock adapters with cloud-backed adapters.
9. Add sample demo data and validation report view.

## Open Decisions

- Which cloud model provider to use first.
- Exact sample video set for demo.
- Whether the Web app opens local job directories directly or imports a zipped run folder.
- How much video preview synchronization is required for MVP.
