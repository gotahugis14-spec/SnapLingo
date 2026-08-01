"""ScreenLingo 配置管理：config.json 存于 %APPDATA%/ScreenLingo/"""
import json
import os

APP_NAME = "ScreenLingo"

DEFAULTS = {
    "ocr_backend": "auto",   # auto / tesseract / api
    "api_base_url": "https://api.siliconflow.cn/v1",
    "vision_model": "Qwen/Qwen3-VL-8B-Instruct",
    "translate_model": "deepseek-ai/DeepSeek-V3.2",
    "api_key": "",           # 也可用环境变量 SILICONFLOW_API_KEY
    "tesseract_lang": "chi_sim+eng",
    "hotkey_menu": "ctrl+alt+o",  # 全局热键：弹操作菜单
}


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def load() -> dict:
    cfg = dict(DEFAULTS)
    raw = {}
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[ScreenLingo] 读取配置失败，使用默认配置: {e}")
    cfg.update(raw)
    # 迁移：v0.1 的两个热键合并为 v0.2 的单个 hotkey_menu
    if "hotkey_menu" not in raw and raw.get("hotkey_ocr"):
        cfg["hotkey_menu"] = raw["hotkey_ocr"]
    return cfg


def save(cfg: dict) -> None:
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_api_key(cfg: dict) -> str:
    """优先环境变量，其次 config.json"""
    return os.environ.get("SILICONFLOW_API_KEY", "") or cfg.get("api_key", "")
