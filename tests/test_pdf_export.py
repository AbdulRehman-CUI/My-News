"""Regression coverage for PDF downloads on a read-only serverless filesystem."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pdf_export import cached_pdf_path, export_pdf


class PdfCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "app"
        self.edition = {"id": "cache-test", "local_date": "2026-11-02",
                        "generated_at": "2026-11-02T10:00:00Z"}
        self.items = [{"title": "A saved story", "brief": "The edition remains downloadable."}]
        # Exercise the deployed renderer without installing or launching a browser.
        self.no_browser = patch.dict("sys.modules", {"playwright.sync_api": None})
        self.no_browser.start()
        self.addCleanup(self.no_browser.stop)

    def test_vercel_uses_temporary_storage_and_reuses_pdf(self):
        with patch.dict(os.environ, {"VERCEL": "1"}), patch("pdf_export.tempfile.gettempdir", return_value=self.temp.name):
            first, cached = export_pdf(self.root, self.edition, self.items)
            second, reused = export_pdf(self.root, self.edition, self.items)
            self.assertTrue(first.startswith(b"%PDF-"))
            self.assertEqual(first, second)
            self.assertFalse(cached)
            self.assertTrue(reused)
            self.assertFalse(self.root.exists())
            self.assertEqual(cached_pdf_path(self.root, self.edition).parent, Path(self.temp.name) / "mynews-pdfs")

    def test_unavailable_cache_directory_still_returns_pdf(self):
        with patch("pdf_export.cached_pdf_path", side_effect=OSError(errno.EROFS, "Read-only file system")):
            payload, cached = export_pdf(self.root, self.edition, self.items)
        self.assertTrue(payload.startswith(b"%PDF-"))
        self.assertFalse(cached)

    def test_cache_read_and_write_failures_do_not_break_download(self):
        path = Path(self.temp.name) / "edition.pdf"
        path.write_bytes(b"old-cache")
        with patch("pdf_export.cached_pdf_path", return_value=path), patch.object(Path, "read_bytes", side_effect=PermissionError()):
            payload, cached = export_pdf(self.root, self.edition, self.items)
            self.assertTrue(payload.startswith(b"%PDF-"))
            self.assertFalse(cached)
        path.unlink()
        with patch("pdf_export.cached_pdf_path", return_value=path), patch("pdf_export.tempfile.NamedTemporaryFile", side_effect=OSError(errno.ENOSPC, "No space")):
            payload, cached = export_pdf(self.root, self.edition, self.items)
            self.assertTrue(payload.startswith(b"%PDF-"))
            self.assertFalse(cached)
