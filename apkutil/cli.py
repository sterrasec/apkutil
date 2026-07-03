#!/usr/bin/env python3
# coding: UTF-8

import argparse
import colorama
from colorama import Fore, Back, Style

from . import manifestutil
from . import util


def cmd_set_debuggable(args):
    print('Decoding APK by Apktool...')
    try:
        util.decode(args.apk_path)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    dir_path = args.apk_path.replace('.apk', '')
    print('Potentially Sensitive Files:')
    util.check_sensitive_files(dir_path)

    print('Checking AndroidManifest.xml...')
    manifest = manifestutil.ManifestUtil(dir_path + '/AndroidManifest.xml')
    manifest.check_all()

    print(Fore.CYAN + '\nSet debuggable attribute to true in AndroidManifest!')
    manifest.set_debuggable()

    print('\nBuilding APK by Apktool...')
    dir_name = args.apk_path.replace('.apk', '')
    apk_path = args.output
    if args.output is None:
        apk_path = dir_name + ".patched.apk"

    try:
        util.build(dir_name, apk_path)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Aligning APK by zipalign...')
    try:
        result = util.align(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Signing APK by apksigner...')
    try:
        result = util.sign(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print(Fore.CYAN + 'Output: ' + apk_path)


def cmd_set_network(args):
    print('Decoding APK by Apktool...')
    try:
        util.decode(args.apk_path)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    dir_path = args.apk_path.replace('.apk', '')
    print('Potentially Sensitive Files:')
    util.check_sensitive_files(dir_path)

    print('Checking AndroidManifest.xml...')
    manifest = manifestutil.ManifestUtil(dir_path + '/AndroidManifest.xml')
    manifest.check_all()

    print(Fore.CYAN + '\nSet networkSecurityConfig attribute to true in AndroidManifest!')
    manifest.set_networkSecurityConfig()
    util.make_network_security_config(dir_path)

    print('\nBuilding APK by Apktool...')
    dir_name = args.apk_path.replace('.apk', '')
    apk_path = args.output
    if args.output is None:
        apk_path = dir_name + ".patched.apk"

    try:
        util.build(dir_name, apk_path)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return
    
    print('Aligning APK by zipalign...')
    try:
        result = util.align(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Signing APK by apksigner...')
    try:
        result = util.sign(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print(Fore.CYAN + 'Output: ' + apk_path)


def cmd_all(args):
    print('Decoding APK by Apktool...')
    try:
        result = util.decode(args.apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    dir_path = args.apk_path.replace('.apk', '')
    print('Potentially Sensitive Files:')
    util.check_sensitive_files(dir_path)

    print('Checking AndroidManifest.xml...')
    manifest = manifestutil.ManifestUtil(dir_path + '/AndroidManifest.xml')
    manifest.check_all()

    print(Fore.CYAN + '\nSet debuggable attribute to true in AndroidManifest!')
    manifest.set_debuggable()

    print(Fore.CYAN + '\nSet networkSecurityConfig attribute to true in AndroidManifest!')
    manifest.set_networkSecurityConfig()
    util.make_network_security_config(dir_path)

    print('\nBuilding APK by Apktool...')
    dir_name = args.apk_path.replace('.apk', '')
    apk_path = args.output
    if args.output is None:
        apk_path = dir_name + ".patched.apk"

    try:
        util.build(dir_name, apk_path)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Aligning APK by zipalign...')
    try:
        result = util.align(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Signing APK by apksigner...')
    try:
        result = util.sign(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print(Fore.CYAN + 'Output: ' + apk_path)


def cmd_decode(args):
    print('Decoding APK by Apktool...')
    try:
        result = util.decode(args.apk_path, no_res=args.no_res, no_src=args.no_src)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    if not args.no_res:
        dir_path = args.apk_path.replace('.apk', '')
        print('Potentially Sensitive Files:')
        util.check_sensitive_files(dir_path)

        print('Checking AndroidManifest.xml...')
        manifest = manifestutil.ManifestUtil(dir_path + '/AndroidManifest.xml')
        manifest.check_all()

def cmd_build(args):
    print('Building APK by Apktool...')
    apk_path = args.output
    if args.output is None:
        apk_path = args.dir_name + ".patched.apk"
    try:
        result = util.build(args.dir_name, apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return
    
    print('Aligning APK by zipalign...')
    try:
        result = util.align(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print('Signing APK by apksigner...')
    try:
        result = util.sign(apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print(Fore.CYAN + 'Output: ' + apk_path)

def cmd_align(args):
    print('Aligning APK by zipalign...')
    try:
        result = util.align(args.apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return


def cmd_sign(args):
    print('Signing APK by apksigner...')
    try:
        result = util.sign(args.apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')
        return

    print(Fore.CYAN + 'Output: ' + args.apk_path)


def cmd_info(args):
    print('Getting package name by aapt2...')
    try:
        result = util.get_packagename(args.apk_path)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')


def cmd_screenshot(args):
    print('Getting a screenshot from connected device...')
    try:
        result = file_name = util.get_screenshot()
        if not result:
            raise Exception()
        print(Fore.CYAN + 'Output: ' + file_name)
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')


def cmd_pull_apks(args):
    print('Pulling APKs from device...')
    try:
        result = util.pull_apks(args.keyword)
        if not result:
            raise Exception()
    except Exception as e:
        print(e)
        print(Fore.RED + 'Failed')


def main():
    colorama.init(autoreset=True)
    parser = argparse.ArgumentParser(description='useful utility for android security testing')

    subparsers = parser.add_subparsers()
    parser_todebuggable = subparsers.add_parser('debuggable', aliases=['debug', 'dg'], help='set debuggable, build & sign APK')
    parser_todebuggable.add_argument('apk_path', help='')
    parser_todebuggable.add_argument('--output', '-o')
    parser_todebuggable.set_defaults(handler=cmd_set_debuggable)

    parser_todebuggable = subparsers.add_parser('network', aliases=['net', 'n'], help='set networkSecurityConfig, build & sign APK')
    parser_todebuggable.add_argument('apk_path', help='')
    parser_todebuggable.add_argument('--output', '-o')
    parser_todebuggable.set_defaults(handler=cmd_set_network)

    parser_all = subparsers.add_parser('all', help='set debuggable & networkSecurityConfig, build & sign APK')
    parser_all.add_argument('apk_path', help='')
    parser_all.add_argument('--output', '-o')
    parser_all.set_defaults(handler=cmd_all)

    parser_decode = subparsers.add_parser('decode', aliases=['d'], help='decode APK')
    parser_decode.add_argument('-r', '--no-res', action='store_true',
        dest='no_res', help='do not decode resources.')
    parser_decode.add_argument('-s', '--no-src', action='store_true',
        dest='no_src', help='do not decode sources.')
    parser_decode.add_argument('apk_path', help='')
    parser_decode.set_defaults(handler=cmd_decode)

    parser_build = subparsers.add_parser('build', aliases=['b'], help='build APK')
    parser_build.add_argument('dir_name', help='')
    parser_build.add_argument('--output', '-o')
    parser_build.set_defaults(handler=cmd_build)

    parser_sign = subparsers.add_parser('sign', aliases=['s'], help='sign APK')
    parser_sign.add_argument('apk_path', help='')
    parser_sign.set_defaults(handler=cmd_sign)

    parser_sign = subparsers.add_parser('align', aliases=['a'], help='align APK')
    parser_sign.add_argument('apk_path', help='')
    parser_sign.set_defaults(handler=cmd_align)

    parser_info = subparsers.add_parser('info', aliases=['i'], help='identify the package name')
    parser_info.add_argument('apk_path', help='')
    parser_info.set_defaults(handler=cmd_info)

    parser_screenshot = subparsers.add_parser('screenshot', aliases=['ss'], help='get screenshot from connected device')
    parser_screenshot.set_defaults(handler=cmd_screenshot)

    parser_pull_apks = subparsers.add_parser('pull', aliases=['p'], help='pull APKs from device')
    parser_pull_apks.add_argument('keyword', help='keyword to search for package name')
    parser_pull_apks.set_defaults(handler=cmd_pull_apks)

    args = parser.parse_args()
    if hasattr(args, 'handler'):
        args.handler(args)
    else:
        parser.print_help()
