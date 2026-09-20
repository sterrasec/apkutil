# coding: UTF-8
"""Regression tests for the apkutil build/aapt2 behavior.

Background: apkutil historically defaulted to the legacy ``aapt`` binary and only
used ``aapt2`` when ``-2/--aapt2`` was passed. On modern Android SDK build-tools
``aapt`` is gone, so ``aapt2`` is now used unconditionally and the opt-in flag was
removed. These tests lock in that behavior and guard against the earlier crash
where ``debuggable`` / ``network`` handlers read a non-existent ``args.aapt2``.

apktool itself removed ``--use-aapt2`` in 2.12.0 (aapt2 has been its default
since 2.9.0), so ``util.build`` now passes the flag only to apktool versions
that still accept it. It also has to tolerate non-ASCII tool output and the
newer ``I: Built apk into: <path>`` success message.

They drive the real ``main()`` parser and the handlers with ``apkutil.util``
mocked, so they run anywhere without apktool, the Android SDK, a keystore, or a
sample APK.
"""

import argparse
import sys
import unittest
from unittest import mock

from apkutil import cli
from apkutil import util


def build_parser():
    """Rebuild the parser exactly as cli.main() does, without executing."""
    captured = {}
    real_parse_args = argparse.ArgumentParser.parse_args

    def capture(self, args=None, namespace=None):
        captured['parser'] = self
        return real_parse_args(self, args=args, namespace=namespace)

    with mock.patch.object(sys, 'argv', ['apkutil']), \
            mock.patch.object(argparse.ArgumentParser, 'parse_args', capture), \
            mock.patch.object(cli, 'colorama'):
        try:
            cli.main()
        except SystemExit:
            pass
    return captured['parser']


def fake_apktool(version_out, build_out='I: Built apk...', build_err=''):
    """Return a _run_subprocess stand-in that answers ``apktool --version``
    with ``version_out`` and any other command with the build output. Every
    command is recorded in the returned ``calls`` list."""
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[:2] == ['apktool', '--version']:
            return version_out, ''
        return build_out, build_err
    return run, calls


def build_cmd(calls):
    return [cmd for cmd in calls if cmd[:2] == ['apktool', 'b']][0]


class BuildAapt2FlagTest(unittest.TestCase):
    """util.build passes --use-aapt2 only to apktool versions that accept it.

    The flag exists in apktool <= 2.11 and was removed in 2.12.0. apktool 2.9+
    already builds with aapt2 by default, so omitting the flag there keeps the
    build on aapt2, while 2.8 and older still get the flag so they don't
    silently fall back to aapt1.
    """

    def _build(self, version_out):
        run, calls = fake_apktool(version_out)
        with mock.patch.object(util, '_run_subprocess', side_effect=run):
            result = util.build('out_dir', 'out.apk')
        return result, calls

    def test_old_apktool_gets_use_aapt2(self):
        for version in ('2.4.1', '2.8.1', '2.9.3', '2.11.0', '2.11.1-SNAPSHOT'):
            with self.subTest(version=version):
                result, calls = self._build(version + '\n')
                self.assertTrue(result)
                self.assertIn('--use-aapt2', build_cmd(calls))

    def test_new_apktool_does_not_get_use_aapt2(self):
        for version in ('2.12.0', '2.12.0-dirty', '2.12.1', '3.0.3', '3.1.0-SNAPSHOT'):
            with self.subTest(version=version):
                result, calls = self._build(version + '\n')
                self.assertTrue(result)
                self.assertNotIn('--use-aapt2', build_cmd(calls))

    def test_unparseable_version_does_not_get_use_aapt2(self):
        result, calls = self._build('')
        self.assertTrue(result)
        self.assertNotIn('--use-aapt2', build_cmd(calls))

    def test_build_cmd_shape(self):
        _, calls = self._build('3.0.3\n')
        self.assertEqual(build_cmd(calls), ['apktool', 'b', 'out_dir', '-o', 'out.apk'])

    def test_build_signature_has_no_aapt2_param(self):
        import inspect
        params = inspect.signature(util.build).parameters
        self.assertNotIn('aapt2', params)


class ParseApktoolVersionTest(unittest.TestCase):

    def test_parse(self):
        cases = {
            '2.4.1': (2, 4, 1),
            '2.12.0-dirty': (2, 12, 0),
            '2.11.1-SNAPSHOT': (2, 11, 1),
            '3.0.3': (3, 0, 3),
            '3.0.3\n': (3, 0, 3),
            '2.9': (2, 9, 0),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(util._parse_apktool_version(text), expected)

    def test_unparseable(self):
        self.assertIsNone(util._parse_apktool_version(''))
        self.assertIsNone(util._parse_apktool_version('apktool: command not found'))
        self.assertIsNone(util._parse_apktool_version(None))
        # Only a leading version counts; a version in the middle of a line
        # (e.g. the bundled smali version) must not be mistaken for apktool's.
        self.assertIsNone(util._parse_apktool_version('with smali 3.0.9 and baksmali 3.0.9'))


class BuildSuccessDetectionTest(unittest.TestCase):
    """util.build recognizes both old and new apktool success messages, and
    stderr noise on a successful build must not turn into a failure."""

    NEW_OUT = ('I: Using Apktool 3.0.3\n'
               'I: Building resources...\n'
               'I: Built apk into: /path/x.apk\n')
    OLD_OUT = 'I: Using Apktool 2.4.1\nI: Built apk...\n'

    def _build(self, build_out, build_err=''):
        run, _ = fake_apktool('3.0.3\n', build_out, build_err)
        with mock.patch.object(util, '_run_subprocess', side_effect=run):
            return util.build('out_dir', 'out.apk')

    def test_new_success_message(self):
        self.assertTrue(self._build(self.NEW_OUT))

    def test_old_success_message(self):
        self.assertTrue(self._build(self.OLD_OUT))

    def test_success_with_stderr_warning(self):
        warning = 'W: warning: string \'foo\' has no default translation.\n'
        self.assertTrue(self._build(self.NEW_OUT, warning))
        self.assertTrue(self._build(self.OLD_OUT, warning))

    def test_failure_raises_with_stderr(self):
        usage = 'Apktool 3.0.3 - a tool for reengineering Android apk files\n'
        with self.assertRaises(Exception) as ctx:
            self._build(usage, 'Unrecognized option: --use-aapt2\n')
        self.assertIn('Unrecognized option', str(ctx.exception))


class RunSubprocessDecodingTest(unittest.TestCase):
    """_run_subprocess must not raise on non-ASCII tool output."""

    def _run(self, stdout, stderr):
        proc = mock.MagicMock()
        proc.communicate.return_value = (stdout, stderr)
        with mock.patch.object(util.subprocess, 'Popen', return_value=proc):
            return util._run_subprocess(['apktool'])

    def test_utf8_output(self):
        outs, errs = self._run('Copyright 2010 Ryszard Wiśniewski\n'.encode('utf-8'),
                               'パス/サンプル.apk\n'.encode('utf-8'))
        self.assertEqual(outs, 'Copyright 2010 Ryszard Wiśniewski\n')
        self.assertEqual(errs, 'パス/サンプル.apk\n')

    def test_invalid_bytes_do_not_raise(self):
        outs, errs = self._run(b'I: Built apk into: /path/\xc5\xff.apk\n', b'\xff\xfe')
        self.assertIn('I: Built apk into:', outs)
        self.assertIsInstance(errs, str)


class Aapt2FlagRemovedTest(unittest.TestCase):
    """The opt-in -2/--aapt2 flag is gone; aapt2 is unconditional."""

    def setUp(self):
        self.parser = build_parser()

    def test_flag_rejected_on_build(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['build', 'out_dir', '-2'])

    def test_flag_rejected_on_debuggable(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(['debuggable', 'sample.apk', '--aapt2'])

    def test_plain_invocations_parse(self):
        # No aapt2 attribute is expected on any namespace anymore.
        for argv in (['build', 'out_dir'], ['debuggable', 'sample.apk'],
                     ['network', 'sample.apk'], ['all', 'sample.apk']):
            args = self.parser.parse_args(argv)
            self.assertFalse(hasattr(args, 'aapt2'))


class CompositeHandlersDoNotCrashTest(unittest.TestCase):
    """Drive the composite handlers end-to-end with util mocked.

    Before the flag/attribute cleanup, these crashed with
    ``'Namespace' object has no attribute 'aapt2'`` on the way to util.build.
    Now they must run cleanly and call util.build(dir, apk) positionally.
    """

    def setUp(self):
        self.parser = build_parser()

    def _run(self, argv):
        args = self.parser.parse_args(argv)
        manifest = mock.MagicMock()
        with mock.patch.object(cli.util, 'decode', return_value=True), \
                mock.patch.object(cli.util, 'check_sensitive_files'), \
                mock.patch.object(cli.util, 'make_network_security_config'), \
                mock.patch.object(cli.util, 'build', return_value=True) as build, \
                mock.patch.object(cli.util, 'align', return_value=True), \
                mock.patch.object(cli.util, 'sign', return_value=True), \
                mock.patch.object(cli.manifestutil, 'ManifestUtil', return_value=manifest):
            args.handler(args)
        return build

    def test_debuggable_builds_without_aapt2_kwarg(self):
        build = self._run(['debuggable', 'sample.apk'])
        build.assert_called_once()
        self.assertNotIn('aapt2', build.call_args.kwargs)

    def test_network_builds(self):
        self._run(['network', 'sample.apk']).assert_called_once()

    def test_all_builds(self):
        self._run(['all', 'sample.apk']).assert_called_once()


if __name__ == '__main__':
    unittest.main()
