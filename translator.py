"""翻译：OpenAI 兼容文本模型，自动检测中英文并互译

- 检测到中文 -> 翻译成英文
- 检测到英文 -> 翻译成中文
"""
import requests

import config

LANG_NAMES = {"zh": "中文", "en": "英文"}


def detect_language(text: str) -> str:
    """按中文字符占比判断：有中文字符视为中文，否则视为英文。"""
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cn > 0 else "en"


def translate(text: str, cfg: dict, target: str = None) -> str:
    """把 text 翻译成 target；target 缺省时自动：中文->英文，英文->中文。"""
    if not text.strip():
        return ""
    src = detect_language(text)
    target = target or ("en" if src == "zh" else "zh")
    if src == target:
        return text.strip()

    api_key = config.get_api_key(cfg)
    if not api_key:
        raise RuntimeError("未配置 API key，无法翻译。")
    prompt = (
        f"你是一个翻译工具。把以下{LANG_NAMES[src]}翻译成{LANG_NAMES[target]}。"
        "只输出翻译结果本身，不要解释、不要加引号、不要输出原文。"
    )
    url = cfg["api_base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["translate_model"],
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "max_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
