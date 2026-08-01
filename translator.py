"""翻译：OpenAI 兼容文本模型，把识别出的文字翻译成英文"""
import requests

import config

PROMPT = (
    "你是一个翻译工具。把用户提供的内容翻译成英文。"
    "只输出翻译结果本身，不要解释、不要加引号、不要输出原文。"
)


def translate_to_english(text: str, cfg: dict) -> str:
    if not text.strip():
        return ""
    api_key = config.get_api_key(cfg)
    if not api_key:
        raise RuntimeError("未配置 API key，无法翻译。")
    url = cfg["api_base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["translate_model"],
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": text},
        ],
        "max_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
