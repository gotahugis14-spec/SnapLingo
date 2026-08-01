"""翻译：OpenAI 兼容文本模型，任意语言内容 → 目标语言（默认中英互译）

支持主流语种切换：中文/英文/日文/韩文/法文/德文/西班牙文/俄文。
提示词不假设源语言（由模型自行识别）。
"""
import time

import requests

import config

# 支持的主流语种
LANG_NAMES = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "fr": "法文",
    "de": "德文",
    "es": "西班牙文",
    "ru": "俄文",
}

# keep-alive：复用连接，减少 TLS/HTTP 握手开销（提速）
_session = requests.Session()


def detect_language(text: str) -> str:
    """按中文字符占比判断：有中文字符视为中文，否则视为英文。"""
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cn > 0 else "en"


def target_name(target: str) -> str:
    return LANG_NAMES.get(target, target)


def translate(text: str, cfg: dict, target: str = None) -> str:
    """把 text 翻译成 target（zh/en/ja/ko/fr/de/es/ru）。
    target 缺省或 "auto" 时自动：中文->英文，其他->中文。"""
    if not text.strip():
        return ""
    src = detect_language(text)
    if not target or target == "auto":
        target = "en" if src == "zh" else "zh"
    if src == target:
        return text.strip()

    api_key = config.get_api_key(cfg)
    if not api_key:
        raise RuntimeError("未配置 API key，无法翻译。")
    prompt = (
        f"你是一个翻译工具。把用户提供的内容翻译成{LANG_NAMES.get(target, target)}。"
        "内容可能是任何语言，请先自行识别。只输出翻译结果本身，"
        "不要解释、不要加引号、不要输出原文。"
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
    return _post_with_retry(url, payload, headers)


def _post_with_retry(url: str, payload: dict, headers: dict,
                     attempts: int = 3, timeout: int = 120) -> str:
    """带重试的 POST：对 429/5xx 和网络异常自动重试（递增等待）。"""
    last: Exception | None = None
    for i in range(attempts):
        try:
            resp = _session.post(url, json=payload, headers=headers,
                                 timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(
                    f"服务繁忙（HTTP {resp.status_code}），请稍后重试。")
                time.sleep(1.5 * (i + 1))
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.RequestException as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last if isinstance(last, Exception) else RuntimeError("请求失败")
