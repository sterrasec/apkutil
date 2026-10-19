"""A cached or downloaded CI executable must pass the pinned digest check."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock


spec = importlib.util.spec_from_file_location(
    'ci_setup_tools', Path(__file__).resolve().parents[1] / '.github/ci/setup_tools.py')
setup_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_tools)


class VerifiedDownloadTest(unittest.TestCase):
    def test_valid_download_is_cached_and_cache_hit_needs_no_network(self):
        data = b'verified release artifact'
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'downloads/tool'
            with mock.patch.object(setup_tools.urllib.request, 'urlopen',
                                   return_value=io.BytesIO(data)) as download:
                self.assertEqual(setup_tools.verified_download('https://example.test/tool', digest, cache), data)
                self.assertEqual(setup_tools.verified_download('https://example.test/tool', digest, cache), data)
                download.assert_called_once()
            self.assertEqual(cache.read_bytes(), data)

    def test_modified_download_is_rejected_before_caching(self):
        digest = hashlib.sha256(b'expected').hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'tool'
            with mock.patch.object(setup_tools.urllib.request, 'urlopen',
                                   return_value=io.BytesIO(b'tampered')):
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    setup_tools.verified_download('https://example.test/tool', digest, cache)
            self.assertFalse(cache.exists())

    def test_modified_cache_is_rejected(self):
        digest = hashlib.sha256(b'expected').hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'tool'
            cache.write_bytes(b'tampered')
            with mock.patch.object(setup_tools.urllib.request, 'urlopen') as download:
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    setup_tools.verified_download('https://example.test/tool', digest, cache)
                download.assert_not_called()
