"""Cross-platform SDK discovery and execution regressions (issues #19/#26)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from apkutil import util


class ToolDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apkutil sdk ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patch = mock.patch.object(util, 'ANDROID_HOME', str(self.root))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(util.shutil, 'which', return_value=None)
        self.which = patch.start()
        self.addCleanup(patch.stop)

    def tool(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return str(path)

    def test_windows_sdk_extensions(self):
        with mock.patch.object(util, '_IS_WINDOWS', True):
            for name, relative in (
                ('adb', 'platform-tools/adb.exe'),
                ('zipalign', 'build-tools/36.0.0/zipalign.exe'),
                ('aapt2', 'build-tools/36.0.0/aapt2.exe'),
                ('apksigner', 'build-tools/36.0.0/apksigner.bat'),
            ):
                with self.subTest(name=name):
                    expected = self.tool(relative)
                    self.assertEqual(util._find_tool(name), expected)

    def test_numeric_version_order_and_stable_preference(self):
        with mock.patch.object(util, '_IS_WINDOWS', False):
            for version in ('9.0.0', '35.0.0', '36.0.0-rc1', '36.0.0', 'unversioned'):
                self.tool('build-tools/' + version + '/aapt2')
            self.assertEqual(util._find_tool('aapt2'),
                             str(self.root / 'build-tools/36.0.0/aapt2'))

    def test_skips_newer_version_missing_requested_tool(self):
        expected = self.tool('build-tools/35.0.0/apksigner')
        self.tool('build-tools/36.0.0/aapt2')
        with mock.patch.object(util, '_IS_WINDOWS', False):
            self.assertEqual(util._find_tool('apksigner'), expected)

    def test_sdk_precedes_path(self):
        self.which.return_value = '/path/adb'
        expected = self.tool('platform-tools/adb.exe')
        with mock.patch.object(util, '_IS_WINDOWS', True):
            self.assertEqual(util._find_tool('adb'), expected)
        self.which.assert_not_called()

    def test_path_fallback_including_apktool(self):
        for name in ('adb', 'aapt2', 'zipalign', 'apksigner', 'apktool'):
            self.which.return_value = '/tools/' + name + '.cmd'
            self.assertEqual(util._find_tool(name), self.which.return_value)
            self.which.assert_called_with(name)

    def test_missing_tool_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            util._find_tool('adb')


class SdkHomeTest(unittest.TestCase):
    def test_environment_precedence(self):
        with mock.patch.dict(os.environ, {'ANDROID_HOME': '/home-sdk',
                                         'ANDROID_SDK_ROOT': '/root-sdk'}, clear=True):
            self.assertEqual(util._get_android_home(), '/home-sdk')
            os.environ['ANDROID_HOME'] = ''
            self.assertEqual(util._get_android_home(), '/root-sdk')

    def test_defaults(self):
        for platform, windows, relative in (
            ('darwin', False, '~/Library/Android/sdk'),
            ('linux', False, '~/Android/Sdk'),
            ('win32', True, '~/AppData/Local/Android/Sdk'),
        ):
            with self.subTest(platform=platform), \
                    mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(util, '_IS_WINDOWS', windows), \
                    mock.patch.object(sys, 'platform', platform):
                # expanduser needs USERPROFILE on Windows to resolve a home.
                with mock.patch.object(util.os.path, 'expanduser', side_effect=lambda p: p):
                    self.assertEqual(os.path.normpath(util._get_android_home()),
                                     os.path.normpath(relative))

    def test_windows_local_appdata(self):
        with mock.patch.dict(os.environ, {'LOCALAPPDATA': 'local data'}, clear=True), \
                mock.patch.object(util, '_IS_WINDOWS', True):
            self.assertEqual(util._get_android_home(), os.path.join('local data', 'Android', 'Sdk'))


class ExecutionTest(unittest.TestCase):
    def test_batch_wrapper_quotes_paths_and_preserves_exit_code(self):
        proc = mock.Mock(returncode=7)
        proc.communicate.return_value = (b'output', b'warning')
        for suffix in ('.bat', '.CMD'):
            with self.subTest(suffix=suffix), \
                    mock.patch.object(util, '_IS_WINDOWS', True), \
                    mock.patch.object(util, '_find_tool', return_value='tool dir/apktool' + suffix), \
                    mock.patch.object(util.subprocess, 'Popen', return_value=proc) as popen:
                self.assertEqual(util._run_subprocess(['apktool', 'd', 'app & %PATH%! (test).apk']),
                                 ('output', 'warning', 7))
                command = popen.call_args.args[0]
                self.assertIn('/d /v:off /s /c ""%APKUTIL_ARG_0%"', command)
                self.assertEqual(popen.call_args.kwargs['env']['APKUTIL_ARG_2'],
                                 'app & %PATH%! (test).apk')

    def test_native_executable_uses_argument_list(self):
        proc = mock.Mock(returncode=0)
        proc.communicate.return_value = (b'', b'')
        with mock.patch.object(util, '_IS_WINDOWS', True), \
                mock.patch.object(util.subprocess, 'Popen', return_value=proc) as popen:
            command = ['sdk dir/adb.exe', 'pull', 'app name.apk']
            util._run_subprocess(command)
            self.assertEqual(popen.call_args.args[0], command)
            self.assertNotIn('env', popen.call_args.kwargs)

    def test_batch_wrapper_escapes_trailing_backslashes(self):
        proc = mock.Mock(returncode=0)
        proc.communicate.return_value = (b'', b'')
        with mock.patch.object(util, '_IS_WINDOWS', True), \
                mock.patch.object(util.subprocess, 'Popen', return_value=proc) as popen:
            util._run_subprocess(['apktool.bat', 'b', '.\\app\\', '-o', 'out.apk'])
            env = popen.call_args.kwargs['env']
            self.assertEqual(env['APKUTIL_ARG_2'], '.\\app\\\\')
            self.assertEqual(env['APKUTIL_ARG_3'], '-o')
            self.assertEqual(env['APKUTIL_ARG_4'], 'out.apk')

    @unittest.skipUnless(os.name == 'nt', 'Requires cmd.exe')
    def test_real_windows_batch_arguments(self):
        with tempfile.TemporaryDirectory(prefix='apkutil batch ') as directory:
            root = Path(directory)
            (root / 'capture_args.py').write_text(
                'import json, sys\n'
                'print(json.dumps(sys.argv[1:]))\n'
                'sys.exit(7)\n')
            args = ['app & (sample).apk', '%PATH%!literal!', '',
                    '.\\app\\', '-o', 'out.apk', 'C:\\',
                    '.\\app with spaces\\\\', 'following argument', 'last\\']
            for suffix in ('.bat', '.cmd'):
                with self.subTest(suffix=suffix):
                    script = root / ('forward args' + suffix)
                    # Forward the original quoted parameters to a native argv
                    # parser, as apktool/apksigner do when launching Java.
                    script.write_text(
                        '@echo off\n'
                        '"%APKUTIL_TEST_PYTHON%" "%~dp0capture_args.py" %*\n'
                        'exit /b %errorlevel%\n')
                    with mock.patch.dict(os.environ, {'APKUTIL_TEST_PYTHON': sys.executable}):
                        out, err, code = util._run_subprocess([str(script)] + args)
                    self.assertEqual(code, 7, out + err)
                    self.assertEqual(json.loads(out), args)

    def test_alignment_uses_unique_temp_file_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'test.apk'
            apk.write_bytes(b'original')
            outputs = []

            def align(cmd):
                outputs.append(cmd[-1])
                Path(cmd[-1]).write_bytes(b'aligned')
                return '', '', 0

            with mock.patch.object(util, '_find_tool', return_value='zipalign'), \
                    mock.patch.object(util, '_run_subprocess', side_effect=align):
                self.assertTrue(util.align(str(apk)))
                self.assertTrue(util.align(str(apk)))
            self.assertEqual(apk.read_bytes(), b'aligned')
            self.assertNotEqual(outputs[0], outputs[1])
            self.assertTrue(all(not Path(p).parent.exists() for p in outputs))

    def test_sign_uses_home_directory_without_home_environment_variable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / 'test.apk'
            apk.touch()
            (root / 'apkutil.json').write_text(
                '{"keystore_path": "~/key.jks", "ks-key-alias": "a", "ks-pass": "pass:p"}')
            with mock.patch.dict(os.environ, {'USERPROFILE': directory, 'HOME': directory}), \
                    mock.patch.object(util, '_find_tool', return_value='apksigner.bat'), \
                    mock.patch.object(util, '_run_subprocess', return_value=('', '', 0)) as run:
                if os.name == 'nt':
                    del os.environ['HOME']
                self.assertTrue(util.sign(str(apk)))
                self.assertIn(str(root / 'key.jks'), run.call_args.args[0])


class SigningPasswordTest(unittest.TestCase):
    def sign_with_config(self, password):
        config = json.dumps({'keystore_path': 'key.jks', 'ks-key-alias': 'test',
                             'ks-pass': password})
        with mock.patch('builtins.open', mock.mock_open(read_data=config)), \
                mock.patch.object(util.os.path, 'isfile', return_value=True), \
                mock.patch.object(util, '_find_tool', return_value='apksigner.bat'):
            return util.sign('sample.apk')

    def test_inline_password_is_only_in_child_environment(self):
        password = 'abc%USERNAME%xyz!& "quoted"'
        with mock.patch.dict(os.environ, {'APKUTIL_KS_PASS': 'parent-value'}), \
                mock.patch.object(util, '_run_subprocess', return_value=('', '', 0)) as run:
            self.assertTrue(self.sign_with_config('pass:' + password))
            command = run.call_args.args[0]
            self.assertEqual(command[command.index('--ks-pass') + 1], 'env:APKUTIL_KS_PASS')
            self.assertNotIn(password, ' '.join(command))
            self.assertEqual(run.call_args.kwargs['env'], {'APKUTIL_KS_PASS': password})
            self.assertEqual(os.environ['APKUTIL_KS_PASS'], 'parent-value')

    def test_other_password_sources_are_unchanged(self):
        for password in ('env:MY_PASSWORD', 'file:password.txt', 'stdin'):
            with self.subTest(password=password), \
                    mock.patch.object(util, '_run_subprocess', return_value=('', '', 0)) as run:
                self.assertTrue(self.sign_with_config(password))
                command = run.call_args.args[0]
                self.assertEqual(command[command.index('--ks-pass') + 1], password)
                self.assertIsNone(run.call_args.kwargs['env'])

    def test_child_environment_is_scoped_for_native_and_batch_commands(self):
        password = 'abc%USERNAME%xyz'
        for command in (['signer.exe', 'env:APKUTIL_KS_PASS'],
                        ['signer.bat', 'env:APKUTIL_KS_PASS']):
            with self.subTest(command=command), \
                    mock.patch.object(util, '_IS_WINDOWS', True), \
                    mock.patch.dict(os.environ, {'APKUTIL_KS_PASS': 'parent-value'}), \
                    mock.patch.object(util.subprocess, 'Popen', side_effect=FileNotFoundError) as popen:
                overrides = {'APKUTIL_KS_PASS': password}
                with self.assertRaises(FileNotFoundError):
                    util._run_subprocess(command, env=overrides)
                child_env = popen.call_args.kwargs['env']
                self.assertEqual(child_env['APKUTIL_KS_PASS'], password)
                self.assertNotIn(password, str(popen.call_args.args[0]))
                self.assertTrue(all(password not in value for key, value in child_env.items()
                                    if key.startswith('APKUTIL_ARG_')))
                self.assertEqual(os.environ['APKUTIL_KS_PASS'], 'parent-value')
                self.assertEqual(overrides, {'APKUTIL_KS_PASS': password})

    @unittest.skipUnless(os.name == 'nt', 'Requires cmd.exe and CALL expansion')
    def test_sign_password_survives_call_reexpansion(self):
        password = 'abc%USERNAME%xyz!& test'
        with tempfile.TemporaryDirectory(prefix='apkutil signing ') as directory:
            root = Path(directory)
            script = root / 'apksigner.bat'
            script.write_text(
                '@echo off\nsetlocal\nset params=%*\n'
                'call "%APKUTIL_TEST_PYTHON%" "%~dp0check_password.py" %params%\n'
                'exit /b %errorlevel%\n')
            (root / 'check_password.py').write_text(
                'import os, sys\n'
                'source = sys.argv[sys.argv.index("--ks-pass") + 1]\n'
                'password = os.environ[source[4:]] if source.startswith("env:") else source[5:]\n'
                'sys.exit(0 if password == ' + repr(password) + ' else 21)\n')
            config = json.dumps({'keystore_path': 'key.jks', 'ks-key-alias': 'test',
                                 'ks-pass': 'pass:' + password})
            with mock.patch.dict(os.environ, {'USERNAME': 'must-not-expand',
                                              'APKUTIL_TEST_PYTHON': sys.executable}), \
                    mock.patch('builtins.open', mock.mock_open(read_data=config)), \
                    mock.patch.object(util.os.path, 'isfile', return_value=True), \
                    mock.patch.object(util, '_find_tool', return_value=str(script)):
                # Prove the fixture reproduces the original CALL expansion.
                _, _, code = util._run_subprocess(
                    [str(script), 'sign', '--ks-pass', 'pass:' + password])
                self.assertEqual(code, 21)
                self.assertTrue(util.sign('sample.apk'))
