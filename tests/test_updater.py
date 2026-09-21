import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from updater import REPO, check_and_stage, safe_url


class Response:
    def __init__(self, url, data):
        self.url = url
        self.data = data
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, count):
        chunk = self.data[self.offset:self.offset + count]
        self.offset += len(chunk)
        return chunk


class UpdaterTests(unittest.TestCase):
    def test_latest_manifest_and_verified_executable(self):
        latest = f'https://github.com/{REPO}/releases/latest/download/update.json'
        binary = b'MZ-test-executable'
        exe = f'https://github.com/{REPO}/releases/download/v1.1.1/ERP_Senembi.exe'
        manifest = json.dumps({'schema': 1, 'version': '1.1.1', 'url': exe,
            'sha256': hashlib.sha256(binary).hexdigest(), 'size_bytes': len(binary)}).encode()

        def opener(url, timeout):
            if url == latest:
                return Response(f'https://github.com/{REPO}/releases/download/v1.1.1/update.json', manifest)
            if url == exe:
                return Response('https://release-assets.githubusercontent.com/download/test', binary)
            raise AssertionError(f'URL inesperada: {url}')

        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(check_and_stage({'version': '1.1.0'}, folder, opener), '1.1.1')
            self.assertEqual((Path(folder) / 'updates' / 'ERP_Senembi-1.1.1.exe').read_bytes(), binary)

    def test_rejects_other_repositories_and_insecure_urls(self):
        self.assertEqual(safe_url(f'https://github.com/{REPO}/releases/latest/download/update.json'),
                         f'https://github.com/{REPO}/releases/latest/download/update.json')
        for url in ('http://github.com/'+REPO+'/releases/latest/download/update.json',
                    'https://github.com/other/repo/releases/latest/download/update.json',
                    'https://github.com/'+REPO+'/releases/download/v1.1.1/unexpected.exe'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                safe_url(url)


if __name__ == '__main__':
    unittest.main()
