import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import deploy_modelscope as deploy


class SourceSyncTests(unittest.TestCase):
    def archive(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("src/new.js", "new release")
        return SimpleNamespace(stdout=output.getvalue())

    def test_removes_deleted_source_but_preserves_private_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "src").mkdir()
            (root / "src/obsolete.js").write_text("old")
            (root / "deployment-data").mkdir()
            (root / "deployment-data/private.txt").write_text("private")
            (root / "deployment-source.json").write_text(json.dumps({"source_commit": "previous"}))
            with patch.object(deploy.subprocess, "run", return_value=self.archive()), \
                    patch.object(deploy, "git", return_value="src/obsolete.js"):
                deploy.sync_source(root, "current")
            self.assertFalse((root / "src/obsolete.js").exists())
            self.assertEqual((root / "src/new.js").read_text(), "new release")
            self.assertEqual((root / "deployment-data/private.txt").read_text(), "private")

    def test_rejects_deletion_outside_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "checkout"
            root.mkdir()
            outside = Path(folder) / "outside.txt"
            outside.write_text("keep")
            (root / "deployment-source.json").write_text(json.dumps({"source_commit": "previous"}))
            with patch.object(deploy.subprocess, "run", return_value=self.archive()), \
                    patch.object(deploy, "git", return_value="../outside.txt"), \
                    self.assertRaises(RuntimeError):
                deploy.sync_source(root, "current")
            self.assertEqual(outside.read_text(), "keep")
