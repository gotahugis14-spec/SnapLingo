"""OCR 后端：tesseract（本地离线）/ api（OpenAI 兼容视觉模型）

api 后端支持两种调用：
- ocr_image：纯识别
- ocr_and_translate：单次请求同时完成识别+翻译（翻译类模式提速，两次请求→一次）
"""
import base64
import io
import json
import re
import shutil
import time

import requests

import config
import translator

SYSTEM_PROMPT = (
    "你是一个 OCR 工具。请识别图片中的全部文字，"
    "严格按原文输出（保留换行），不要添加任何解释、标点修正或翻译。"
)

# keep-alive：复用连接，减少 TLS/HTTP 握手开销（提速）
_session = requests.Session()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_image(img, cfg: dict, backend: str = None) -> str:
    backend = backend or cfg.get("ocr_backend", "auto")
    if backend == "auto":
        backend = "tesseract" if tesseract_available() else "api"
    if backend == "tesseract":
        return _ocr_tesseract(img, cfg)
    if backend == "api":
        return _ocr_api(img, cfg)
    raise ValueError(f"未知 OCR 后端: {backend}")


def _ocr_tesseract(img, cfg: dict) -> str:
    if not tesseract_available():
        raise RuntimeError("未检测到 Tesseract。请安装后重试，或改用 api 后端。")
    import pytesseract
    lang = cfg.get("tesseract_lang", "chi_sim+eng")
    return pytesseract.image_to_string(img, lang=lang).strip()


def _to_data_url(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _ocr_api(img, cfg: dict) -> str:
    url, payload, headers = _api_request(img, cfg, SYSTEM_PROMPT)
    return _post_with_retry(url, payload, headers)


def ocr_and_translate(img, cfg: dict, target: str) -> tuple[str, str]:
    """单次视觉模型请求同时完成识别+翻译（翻译类模式提速：两次请求→一次）。
    返回 (原文, 译文)；解析失败抛 ValueError（调用方回退两次请求）。"""
    target_cn = translator.target_name(target)
    prompt = (
        "你是一个截图文字工具。请先识别图片中的全部文字，"
        f"然后把识别出的文字翻译成{target_cn}。\n"
        "严格按以下格式输出，不要输出任何其他内容：\n"
        "【原文】\n<识别的原文，保留换行>\n"
        "【译文】\n<翻译结果>"
    )
    url, payload, headers = _api_request(img, cfg, prompt)
    content = _post_with_retry(url, payload, headers)
    parsed = _parse_orig_trans(content)
    if parsed is None:
        raise ValueError("识别+翻译结果解析失败，回退两次请求")
    return parsed


def _parse_orig_trans(content: str) -> tuple[str, str] | None:
    """解析【原文】...【译文】... 格式；失败再试 JSON。"""
    m = re.search(r"【原文】\s*(.*?)\s*【译文】\s*(.*)", content, re.S)
    if m:
        orig, trans = m.group(1).strip(), m.group(2).strip()
        if orig and trans:
            return orig, trans
    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("original") and data.get("translation"):
            return data["original"].strip(), data["translation"].strip()
    except Exception:
        pass
    return None


def _api_request(img, cfg: dict, prompt: str):
    api_key = config.get_api_key(cfg)
    if not api_key:
        raise RuntimeError(
            "未配置 API key：请设置环境变量 SILICONFLOW_API_KEY，"
            "或在 config.json 中填写 api_key。")
    url = cfg["api_base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["vision_model"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _to_data_url(img)}},
            ],
        }],
        "max_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    return url, payload, headers


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
