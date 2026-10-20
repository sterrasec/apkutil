"""Opt-in smoke test with real SDK tools, apktool, Java and a generated APK."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from apkutil import util


@unittest.skipUnless(os.environ.get('APKUTIL_SDK_TESTS') == '1',
                     'Set APKUTIL_SDK_TESTS=1 with an SDK, apktool and Java installed')
class SdkIntegrationTest(unittest.TestCase):
    def test_info_and_debuggable(self):
        with tempfile.TemporaryDirectory(prefix='apkutil smoke ') as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            manifest = source / 'AndroidManifest.xml'
            manifest.write_text(
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                'package="com.example.apkutilsmoke" android:versionCode="1" '
                'android:versionName="1.0">'
                '<uses-sdk android:minSdkVersion="23" android:targetSdkVersion="28" />'
                '<application android:hasCode="false" android:label="Smoke" />'
                '</manifest>', encoding='utf-8')
            apk = root / 'sample %USERNAME% app.apk'
            output = root / 'patched %USERNAME% app.apk'
            aapt2 = util._find_tool('aapt2')
            sdk_jar = Path(util.ANDROID_HOME) / 'platforms/android-35/android.jar'
            self.assertTrue(sdk_jar.is_file(), str(sdk_jar))

            password = 'abc%USERNAME%xyz!& test'

            def run(command):
                outs, errs, code = util._run_subprocess(
                    command, env={'APKUTIL_TEST_KS_PASS': password})
                self.assertEqual(code, 0, outs + errs)
                return outs

            run([aapt2, 'link', '-I', str(sdk_jar), '--manifest', str(manifest), '-o', str(apk)])
            keytool = shutil.which('keytool')
            self.assertIsNotNone(keytool)
            keystore = root / 'key%USERNAME%store.jks'
            alias = 'alias%USERNAME%'
            run([keytool, '-genkeypair', '-keystore', str(keystore),
                 '-storepass:env', 'APKUTIL_TEST_KS_PASS',
                 '-keypass:env', 'APKUTIL_TEST_KS_PASS', '-alias', alias,
                 '-keyalg', 'RSA', '-validity', '1', '-dname', 'CN=apkutil test', '-noprompt'])
            (root / 'apkutil.json').write_text(json.dumps({
                'keystore_path': '~/' + keystore.name, 'ks-key-alias': alias, 'ks-pass': 'env:APKUTIL_TEST_KS_PASS',
            }))
            with mock.patch.dict(os.environ, {'HOME': directory, 'USERPROFILE': directory,
                                             'USERNAME': 'must-not-expand'}):
                if os.name == 'nt':
                    del os.environ['HOME']
                # Exercise the installed entry point via the same main() used by apkutil.
                entry = [sys.executable, '-c',
                         'from apkutil.cli import main; import os; os.chdir({0!r}); main()'.format(directory)]
                if os.name == 'nt':
                    # Keep stdin's writer open while waiting: inheriting it
                    # would leave the official apktool.bat stuck at PAUSE.
                    probe = subprocess.Popen(
                        [sys.executable, '-c',
                         'from apkutil import util; assert util._get_apktool_version() is not None'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        probe.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        probe.stdin.close()
                        probe.stdin = None
                        probe.communicate(timeout=10)
                        self.fail('Official apktool.bat waited for input')
                    stdout, stderr = probe.communicate(timeout=10)
                    self.assertEqual(probe.returncode, 0, (stdout + stderr).decode(errors='replace'))
                info = run(entry + ['info', apk.name])
                self.assertIn('com.example.apkutilsmoke', info)
                log = run(entry + ['debuggable', apk.name, '-o', output.name])
                self.assertTrue(output.is_file(), log)
                run([util._find_tool('apksigner'), 'verify', str(output)])
                run([util._find_tool('zipalign'), '-c', '4', str(output)])
                xml = run([aapt2, 'dump', 'xmltree', str(output), '--file', 'AndroidManifest.xml'])
                self.assertRegex(xml, r'android:debuggable[^\r\n]*true')

                # Rebuild the decoded directory with a trailing separator.
                # On Windows this exercises .\\sample app\\ through apktool.bat
                # and Java, including the boundary before the -o option.
                rebuilt = root / 'rebuilt %USERNAME% app.apk'
                decoded_dir = '.' + os.sep + apk.stem + os.sep
                log = run(entry + ['build', decoded_dir, '-o', rebuilt.name])
                self.assertTrue(rebuilt.is_file(), log)
                run([util._find_tool('apksigner'), 'verify', str(rebuilt)])
                run([util._find_tool('zipalign'), '-c', '4', str(rebuilt)])
