"""LLM helpers for user creative intent and transfer-plan revisions."""

from __future__ import annotations

import json
from typing import Any

from .doubao_client import get_ark_client
from ..core.config import get_settings


async def expand_creative_brief(
    creative_brief: str | None,
    target_description: str | None = None,
) -> dict[str, Any]:
    """Expand casual user notes into structured creative constraints."""
    text = (creative_brief or "").strip()
    target = (target_description or "").strip()
    if not text and not target:
        return {}

    settings = get_settings()
    client = get_ark_client()
    prompt = f"""用户上传短视频后补充了创作意图。请把它扩写成结构化约束，供后续视频分析、爆款结构提取和结构迁移使用。

用户输入:
{text or "（无）"}

目标描述:
{target or "（无）"}

请严格返回 JSON:
{{
  "summary": "一句话总结用户想要什么",
  "user_highlights": ["用户认为重要的视频亮点"],
  "transfer_priority": ["迁移时必须优先保留的结构/画面/情绪"],
  "avoid_focus": ["不要过度强调的动作或误判方向"],
  "style_keywords": ["风格关键词"],
  "cta_keywords": ["可用于搜索 CTA 的关键词"],
  "analysis_hints": ["给视频分析模型的观察提示"],
  "revision_options": ["给用户确认方案时可展示的快捷调整选项"]
}}"""

    response = client.chat.completions.create(
        model=settings.ARK_MODEL,
        messages=[
            {"role": "system", "content": "你是短视频创作意图整理助手，把用户自然语言变成可执行的结构化创作约束。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content
    parsed = _parse_json(raw)
    if parsed:
        parsed["raw_user_brief"] = text
        return parsed
    return {
        "summary": text or target,
        "raw_user_brief": text,
        "user_highlights": [text] if text else [],
        "transfer_priority": [],
        "avoid_focus": [],
        "style_keywords": [],
        "cta_keywords": [],
        "analysis_hints": [],
        "revision_options": [],
    }


async def revise_transfer_with_instruction(
    transfer: dict[str, Any],
    instruction: str,
    creative_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Revise an existing transfer plan from natural-language feedback."""
    settings = get_settings()
    client = get_ark_client()
    prompt = f"""你正在修改一个短视频结构迁移方案。用户会用自然语言提出调整要求，请只修改必要字段，保持 JSON 结构可执行。

用户调整要求:
{instruction}

创作约束:
{json.dumps(creative_brief or {{}}, ensure_ascii=False, indent=2)}

当前方案:
{json.dumps(transfer, ensure_ascii=False, indent=2)}

修改规则:
- 保留 storyboard/script/material_needs/timeline_metrics/material_coverage 等顶层结构。
- 如果用户要求换片段，优先修改 storyboard 中对应 shot 的 source/content/subtitle/edit。
- 只修改用户明确提到的镜头或字段；用户没有提到的 shot 必须保持原来的 source、duration、edit.spatial_role 和顺序。
- 如果用户只要求调整 near/mid，far、empty、cta 的 source 必须保持不变。
- 如果用户说“保持远景/环境释放”，不得改动 far/empty 镜头的 source。
- 不要输出解释文字，只返回完整 JSON。
- 确保 storyboard 每个 shot 有 source、duration、content、subtitle、edit.spatial_role。
"""

    response = client.chat.completions.create(
        model=settings.ARK_MODEL,
        messages=[
            {"role": "system", "content": "你是短视频剪辑方案修订助手，擅长把自然语言反馈转成可执行 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content
    return _parse_json(raw) or transfer


def creative_context_text(brief: dict[str, Any] | None) -> str:
    if not brief:
        return ""
    return json.dumps(brief, ensure_ascii=False, indent=2)


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    first = text.find("{")
    last = text.rfind("}")
    candidates = [text]
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
