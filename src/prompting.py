"""Tidebound 规范的本地提示词包加载与组装器。
严格基于 master.yaml 加载模块化提示词，不访问远端或执行动态未校验代码。
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant: str
    name: str
    segments: List[Segment] = Field(min_length=1)


class Language(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    variants: List[Variant] = Field(min_length=1)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompts: Dict[str, List[Language]]


@dataclass(frozen=True)
class PromptBundle:
    name: str
    content: str
    files: Tuple[Path, ...]


def load_manifest(root: Path) -> Manifest:
    """加载 master.yaml 清单。"""
    manifest_path = root / "master.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"未找到提示词清单文件: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Manifest.model_validate(data)


def resolve_segment_path(root: Path, content_ref: str) -> Path:
    """解析以 @master 开头的内容文件路径。"""
    if content_ref.startswith("@master/"):
        relative = content_ref[len("@master/") :]
        return root / "master" / relative
    return root / content_ref


def clean_markdown_comment(text: str) -> str:
    """移除类似 {{/* ... */}} 的模板注释。"""
    return re.sub(r"\{\{/\*.*?\*/\}\}", "", text, flags=re.DOTALL).strip()


# 全局提示词内存缓存，避免重复读盘
_COMPILED_BUNDLES: Dict[str, PromptBundle] = {}

def load_prompt_bundles(
    root: Path,
    purposes: Tuple[str, ...],
    language: str = "zh",
) -> PromptBundle:
    """按指定用途顺序加载并合并提示词，使用内存缓存。"""
    bundle_name = "+".join(purposes) + f"_{language}"
    if bundle_name in _COMPILED_BUNDLES:
        return _COMPILED_BUNDLES[bundle_name]

    manifest = load_manifest(root)
    collected_contents: List[str] = []
    collected_files: List[Path] = []

    for purpose in purposes:
        if purpose not in manifest.prompts:
            raise KeyError(f"提示词清单中未定义模块: {purpose}")
        lang_configs = manifest.prompts[purpose]
        matched_lang = next((l for l in lang_configs if l.language == language), None)
        if not matched_lang and lang_configs:
            matched_lang = lang_configs[0]
        if not matched_lang:
            continue

        primary_variant = matched_lang.variants[0]
        for seg in primary_variant.segments:
            file_path = resolve_segment_path(root, seg.content)
            if not file_path.exists():
                raise FileNotFoundError(f"提示词文件不存在: {file_path}")
            raw_text = file_path.read_text(encoding="utf-8")
            cleaned_text = clean_markdown_comment(raw_text)
            if cleaned_text:
                collected_contents.append(cleaned_text)
            collected_files.append(file_path)

    full_content = "\n\n".join(collected_contents)
    bundle = PromptBundle(name=bundle_name, content=full_content, files=tuple(collected_files))
    _COMPILED_BUNDLES[bundle_name] = bundle
    return bundle


def clear_prompt_cache():
    """清空提示词缓存，用于WebUI保存后热重载。"""
    _COMPILED_BUNDLES.clear()


def load_chat_system(
    root: Path,
    session_type: str = "private",
    language: str = "zh",
    enable_simultaneous: bool = False,
) -> str:
    """按角色、世界观、安全约定、特定群聊/私聊场景、交互节奏及同传指令组装系统提示词。"""
    purposes = ["chat.character", "world.worldview", "chat.safety"]
    if session_type == "group":
        purposes.append("chat.group")
    else:
        purposes.append("chat.private")
    purposes.append("companion.rules")
    if enable_simultaneous:
        purposes.append("interpretation.simultaneous")
    bundle = load_prompt_bundles(root, tuple(purposes), language=language)
    return bundle.content


def get_tts_anchor_rules() -> str:
    """获取置于Prompt最末尾的强硬输出约束锚点，防止被长文稀释。"""
    return (
        "【最后警告：输出红线约束】\n"
        "1. 你的回复将直接用于语音合成，因此**绝对禁止**使用任何表情符号（如✨、😊、🐱、🎵等）和特殊排版。\n"
        "2. **绝对禁止**在回复中包含对动作、神态、心理描写的括号或任何形式的解说（如 `（拉开窗帘）`、`[微笑]`、`（递过去）` 等）。\n"
        "3. 你只能输出纯粹的、自然的、角色口语台词。\n"
        "4. 保持纯台词口语流露，日常随口闲聊自然利落（约40-90字）；涉及深情安抚、回忆往事或倾听烦恼时，允许充沛展开，严禁机械死板截断。\n"
        "5. 严禁以第三人称或说书人姿态向哥哥讲述星空列车，哥哥是亲历同乘者，交流必须立足共同生活与同乘经历。\n"
        "6. **绝对禁止**输出任何思考过程、上下文分析、扮演思路或思维链路（如严禁出现‘让我分析’、‘用户发送了’、‘从群聊内容来看’、‘<think>’等），你必须直接以音理的第一人称输出对白台词！\n"
        "请现在直接以上述规范给出音理的纯台词回复。"
    )


def load_decision_prompt(root: Path, language: str = "zh") -> str:
    """加载用于决策模型主动回复的提示词。"""
    bundle = load_prompt_bundles(root, ("decision.active_reply",), language=language)
    return bundle.content
