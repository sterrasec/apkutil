# coding: UTF-8
"""Regression tests for the apkutil build/aapt2 behavior.

Background: apkutil historically defaulted to the legacy ``aapt`` binary and only
used ``aapt2`` when ``-2/--aapt2`` was passed. On modern Android SDK build-tools
``aapt`` is gone, so ``aapt2`` is now used unconditionally and the opt-in flag was
removed. These tests lock in that behavior and guard against the earlier crash
where ``debuggable`` / ``network`` handlers read a non-existent ``args.aapt2``.

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


class BuildUsesAapt2Test(unittest.TestCase):
    """util.build must always invoke apktool with --use-aapt2."""

    def test_build_passes_use_aapt2(self):
        captured = {}

        def fake_run(cmd):
            captured['cmd'] = cmd
            return 'I: Built apk...', ''

        with mock.patch.object(util, '_run_subprocess', side_effect=fake_run):
            self.assertTrue(util.build('out_dir', 'out.apk'))
        self.assertIn('--use-aapt2', captured['cmd'])

    def test_build_signature_has_no_aapt2_param(self):
        import inspect
        params = inspect.signature(util.build).parameters
        self.assertNotIn('aapt2', params)


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
