from pathlib import Path
import os
import unittest
from unittest.mock import patch

from app.config import Settings, get_dashscope_api_key


class ConfigTest(unittest.TestCase):
    def test_get_dashscope_api_key_rejects_missing_key(self) -> None:
        settings = Settings(_env_file=None, dashscope_api_key="")

        with self.assertRaisesRegex(RuntimeError, "DASHSCOPE_API_KEY"):
            get_dashscope_api_key(settings)

    def test_get_dashscope_api_key_reads_environment(self) -> None:
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-dashscope-key"}):
            settings = Settings(_env_file=None)

        self.assertEqual(get_dashscope_api_key(settings), "test-dashscope-key")

    def test_app_code_does_not_contain_leaked_dashscope_key_prefix(self) -> None:
        leaked_prefix = "sk-" + "a292"

        for path in Path("app").rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn(leaked_prefix, content, str(path))


if __name__ == "__main__":
    unittest.main()
