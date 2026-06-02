from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import file as file_api
from app.services.vector_index_service import VectorIndexResult


class FakeVectorIndexService:
    def __init__(self) -> None:
        self.docs = []

    def index_documents(self, docs):
        self.docs = docs

        return VectorIndexResult(
            chunks_count=len(docs),
            inserted_count=1,
            skipped_count=max(0, len(docs) - 1),
        )


class FileUploadApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.original_upload_dir = file_api.UPLOAD_DIR
        self.original_index_service = file_api.vector_index_service
        self.original_max_upload_bytes = file_api.MAX_UPLOAD_BYTES
        self.addCleanup(self._restore_file_api_globals)

        self.index_service = FakeVectorIndexService()
        file_api.UPLOAD_DIR = Path(self.temp_dir.name)
        file_api.vector_index_service = self.index_service

        app = FastAPI()
        app.include_router(file_api.router)
        self.client = TestClient(app)

    def _restore_file_api_globals(self) -> None:
        file_api.UPLOAD_DIR = self.original_upload_dir
        file_api.vector_index_service = self.original_index_service
        file_api.MAX_UPLOAD_BYTES = self.original_max_upload_bytes

    def test_rejects_unsupported_file_extension(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={"file": ("bad.pdf", b"plain text", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "只支持上传 TXT 或 Markdown 文件")

    def test_rejects_blank_file_content(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={"file": ("blank.txt", b"   \n\t", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "文件内容不能为空")

    def test_rejects_oversized_file(self) -> None:
        file_api.MAX_UPLOAD_BYTES = 3

        response = self.client.post(
            "/files/upload",
            files={"file": ("large.txt", b"1234", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "文件大小不能超过50MB")

    def test_rejects_non_utf8_file(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={"file": ("bad.txt", b"\xff\xfe", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "文件必须使用 UTF-8 编码")

    def test_success_response_includes_index_counts(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={"file": ("ok.txt", "hello world".encode("utf-8"), "text/plain")},
        )

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["filename"], "ok.txt")
        self.assertEqual(data["chunks_count"], 1)
        self.assertEqual(data["inserted_count"], 1)
        self.assertEqual(data["skipped_count"], 0)
        self.assertEqual(data["status"], "success")


if __name__ == "__main__":
    unittest.main()
