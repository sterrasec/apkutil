"""Install CI tools only after verifying repository-pinned SHA-256 digests.

Cache downloads, not extracted executables, and revalidate every cache hit.
Digests come from the upstream release asset metadata/checksums at review time.
"""
import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.request


TOOLS = {
    'apktool': (
        'https://github.com/iBotPeaches/Apktool/releases/download/v2.12.0/apktool_2.12.0.jar',
        'effb69dab2f93806cafc0d232f6be32c2551b8d51c67650f575e46c016908fdd',
    ),
    'apktool-windows-wrapper': (
        'https://raw.githubusercontent.com/iBotPeaches/Apktool/0228f9800ebf263436e56026a87df43fb9d7ca80/scripts/windows/apktool.bat',
        '3e1c29f9d2c7b3a7c938573f4c2ae61172f6221dc9febfa85080f354357d6336',
    ),
    # pinact is run on the Linux x64 matrix entry only.
    'pinact': (
        'https://github.com/suzuki-shunsuke/pinact/releases/download/v2.0.4/pinact_linux_amd64.tar.gz',
        '791ea4d33f398ec651168292cab71df3cd31a91fd426fd5de9657e284b1d4852',
    ),
}


def verified_download(url, digest, cache):
    if cache.is_file():
        data = cache.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('SHA-256 mismatch: ' + url)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def main(tool):
    url, digest = TOOLS[tool]
    cache = Path('.cache/ci') / url.rsplit('/', 1)[-1]
    data = verified_download(url, digest, cache)
    directory = Path(os.environ['RUNNER_TEMP']) / (tool + ' bin')
    directory.mkdir(exist_ok=True)
    if tool == 'apktool':
        shutil.copyfile(cache, directory / 'apktool.jar')
        if os.name == 'nt':
            wrapper_url, wrapper_digest = TOOLS['apktool-windows-wrapper']
            wrapper = verified_download(wrapper_url, wrapper_digest,
                                        Path('.cache/ci/apktool.bat'))
            (directory / 'apktool.bat').write_bytes(wrapper)
        else:
            script = directory / 'apktool'
            script.write_text('#!/bin/sh\nexec java -jar "$(dirname "$0")/apktool.jar" "$@"\n')
            script.chmod(0o755)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            # Extract only the expected binary; never trust archive paths.
            binary = archive.extractfile('pinact')
            if binary is None:
                raise ValueError('Missing pinact binary')
            script = directory / 'pinact'
            script.write_bytes(binary.read())
            script.chmod(0o755)
    with open(os.environ['GITHUB_PATH'], 'a', encoding='utf-8') as path:
        path.write(str(directory) + '\n')


if __name__ == '__main__':
    main(sys.argv[1])
