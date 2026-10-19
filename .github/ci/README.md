# CI dependencies and caches

All workflow Actions are pinned to full commit SHAs. Linux runs
`pinact run --check --verify` using pinact 2.0.4; its release archive and apktool
2.12.0 are verified against digests committed in `setup_tools.py`. Windows uses
the unmodified official apktool.bat from the pinned upstream commit, also
verified by SHA-256. Action updates
are proposed weekly by Dependabot. To update pins locally, run `pinact run`,
review the changes, then `pinact run --check --verify`.

Python dependencies, including transitive and package build dependencies, are
locked with hashes. To refresh the lock from the repository root:

```sh
uv pip compile .github/ci/requirements.in --python-version 3.12 --universal --generate-hashes --only-binary :all: --exclude-newer '1 week' --output-file .github/ci/requirements.txt
```

Keep the runtime entries in `requirements.in` aligned with `setup.py`.
`pip check` rejects missing or incompatible dependencies after the project is
installed with `--no-deps --no-build-isolation`. External dependencies are
installed from wheels with `--require-hashes`; no dependency build scripts run.

The pip download cache is keyed by OS, Python version, and the lock file through
setup-python. Tool downloads are cached separately by OS and the installer file
hash, with no partial-key fallback; every restored tool archive/JAR is rehashed
before use. Extracted executables, virtual environments, and signing keys are
not cached. The SDK is reused from GitHub's runner image; only missing versioned
packages are installed. Caching the entire SDK would duplicate large preinstalled
files and consume cache storage and transfer time.

All three OSes run regression tests. Linux and Windows also run real SDK smoke
tests; macOS avoids redundant Java/SDK setup. Superseded runs are cancelled and
jobs have a 15-minute timeout. The public repository uses standard runners,
whose execution time is currently free. Cache storage remains subject to GitHub's
storage limits; monitor usage separately.

Pinning and digest checks prevent silently replaced references/downloads; they
do not prove that the originally selected release is benign. GitHub runner
images and their SDK/Java tools, PyPI, upstream releases, and reviewed dependency
updates remain trust boundaries. Tests use `pull_request`, read-only repository
permissions, no secrets, and checkout without persisted credentials. CodeQL
retains `security-events: write` to upload its results.

The Windows SDK smoke test leaves an input pipe open while querying apktool,
so an accidental PAUSE blocks and fails the timeout rather than passing because
CI already closed stdin. Signing uses the SDK's apksigner JAR via native Java
arguments to avoid the batch launcher's CALL re-expansion. The smoke test uses
literal `%USERNAME%` in APK/keystore filenames, the key alias, and the password.
