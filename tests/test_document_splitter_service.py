import unittest

from app.services.document_splitter_service import document_splitter_service


class DocumentSplitterServiceTest(unittest.TestCase):
    def test_markdown_file_keeps_header_metadata(self) -> None:
        docs = document_splitter_service.split_document(
            "# Title\n\n正文内容",
            "uploads/example.md",
        )

        self.assertEqual(docs[0].metadata["Header 1"], "Title")

    def test_markdown_extension_uses_markdown_splitter(self) -> None:
        docs = document_splitter_service.split_document(
            "# Title\n\n正文内容",
            "uploads/example.markdown",
        )

        self.assertEqual(docs[0].metadata["Header 1"], "Title")

    def test_txt_file_uses_plain_text_splitter(self) -> None:
        docs = document_splitter_service.split_document(
            "# Title\n\n正文内容",
            "uploads/example.txt",
        )

        self.assertNotIn("Header 1", docs[0].metadata)


if __name__ == "__main__":
    unittest.main()
