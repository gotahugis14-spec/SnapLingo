"""冒烟单元测试（stdlib unittest，无第三方依赖）

运行：python -m unittest discover tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import translator  # noqa: E402


class TestDetectLanguage(unittest.TestCase):
    def test_chinese(self):
        self.assertEqual(translator.detect_language("你好世界"), "zh")

    def test_english(self):
        self.assertEqual(translator.detect_language("Hello world"), "en")

    def test_mixed(self):
        self.assertEqual(translator.detect_language("Mix 中文 test"), "zh")


class TestConfigMigration(unittest.TestCase):
    def test_v01_hotkey_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["APPDATA"] = tmp
            cfg_dir = os.path.join(tmp, "ScreenLingo")
            os.makedirs(cfg_dir, exist_ok=True)
            with open(os.path.join(cfg_dir, "config.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"hotkey_ocr": "ctrl+alt+x"}, f)
            cfg = config.load()
            self.assertEqual(cfg["hotkey_menu"], "ctrl+alt+x")
            self.assertEqual(cfg["hotkey_translate"], "ctrl+alt+t")
            self.assertEqual(cfg["hotkey_copy"], "ctrl+alt+c")


class TestDefaults(unittest.TestCase):
    def test_default_hotkeys(self):
        cfg = config.load()
        self.assertEqual(cfg["hotkey_menu"], "ctrl+alt+o")
        self.assertEqual(cfg["hotkey_translate"], "ctrl+alt+t")
        self.assertEqual(cfg["hotkey_copy"], "ctrl+alt+c")


if __name__ == "__main__":
    unittest.main()
