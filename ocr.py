"""OCR 后端：tesseract（本地离线）/ api（OpenAI 兼容视觉模型）"""
import base64
import io
import shutil
import time

import requests

import config

SYSTEM_PROMPT = (
    "你是一个 OCR 工具。请识别图片中的全部文字，"
    "严格按原文输出（保留换行），不要添加任何解释、标点修正或翻译。"
)


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
                {"type": "text", "text": SYSTEM_PROMPT},
                {"type": "image_url", "image_url": {"url": _to_data_url(img)}},
            ],
        }],
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
            resp = requests.post(url, json=payload, headers=headers,
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
