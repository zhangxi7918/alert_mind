import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from docx import Document as DocxDocument
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import file as file_api
from app.services.vector_index_service import VectorIndexResult


def _build_pdf_bytes(text: str) -> bytes:
    """构造一个含文本层的最小合法 PDF，用于验证 PDF 抽取链路。"""
    stream = b"BT /F1 18 Tf 20 100 Td (" + text.encode("latin-1") + b") Tj ET"
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for index, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj" + body + b"endobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode()
    out += b"trailer<</Size " + str(len(objs) + 1).encode() + b"/Root 1 0 R>>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return out


def _build_docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    document = DocxDocument()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


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
            files={"file": ("bad.exe", b"plain text", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "只支持上传 TXT、Markdown、PDF 或 Word(.docx) 文件",
        )

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

    def test_ingests_pdf_file(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={
                "file": ("doc.pdf", _build_pdf_bytes("CPU usage runbook"), "application/pdf"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filename"], "doc.pdf")
        # 抽取出的文本应被切分并送入索引
        self.assertGreaterEqual(len(self.index_service.docs), 1)
        self.assertIn("CPU usage runbook", self.index_service.docs[0].page_content)

    def test_ingests_docx_file(self) -> None:
        ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        response = self.client.post(
            "/files/upload",
            files={"file": ("doc.docx", _build_docx_bytes("数据库连接池耗尽处理手册"), ctype)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filename"], "doc.docx")
        self.assertGreaterEqual(len(self.index_service.docs), 1)
        self.assertIn("数据库连接池耗尽处理手册", self.index_service.docs[0].page_content)

    def test_rejects_corrupt_pdf(self) -> None:
        response = self.client.post(
            "/files/upload",
            files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["detail"].startswith("文件解析失败"))


if __name__ == "__main__":
    unittest.main()
