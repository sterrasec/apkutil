#!/usr/bin/env python3
# coding: UTF-8

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from colorama import Fore
import inquirer

_IS_WINDOWS = os.name == 'nt'


def _get_android_home():
    sdk_path = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if sdk_path:
        return os.path.expanduser(sdk_path)
    if _IS_WINDOWS:
        local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~/AppData/Local')
        return os.path.join(local_appdata, 'Android', 'Sdk')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Android/sdk')
    return os.path.expanduser('~/Android/Sdk')


ANDROID_HOME = _get_android_home()

# Oldest apktool apkutil is known to work with. Older releases can't decode
# APKs built by recent aapt2 and default to aapt1 when building.
APKTOOL_MIN_VERSION = (2, 9, 0)

# Private methods
def _build_tools_version(path):
    version = os.path.basename(path)
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[- ](.+))?', version)
    if match is None:
        return (-1, -1, -1, False, version)
    major, minor, patch, preview = match.groups()
    return (int(major), int(minor), int(patch), preview is None, preview or '')


def _find_tool(name):
    # Prefer the configured SDK, falling back to tools installed on PATH.
    if name == 'adb':
        directories = [os.path.join(ANDROID_HOME, 'platform-tools')]
    elif name == 'apktool':
        directories = []
    else:
        directories = sorted(glob.glob(os.path.join(ANDROID_HOME, 'build-tools', '*')),
                             key=_build_tools_version, reverse=True)
    suffixes = ('.exe', '.bat', '.cmd', '') if _IS_WINDOWS else ('',)
    for directory in directories:
        for suffix in suffixes:
            candidate = os.path.join(directory, name + suffix)
            if os.path.isfile(candidate):
                return candidate
    path = shutil.which(name)
    if path:
        return path
    raise FileNotFoundError('{0} not found in the Android SDK or PATH'.format(name))


def _is_sdk_apksigner(wrapper):
    # A PATH entry can be an arbitrary forwarding script. Only bypass a
    # launcher in the SDK's build-tools/<version>/ layout with its SDK JAR.
    directory = os.path.dirname(os.path.realpath(wrapper))
    return (os.path.basename(os.path.dirname(directory)).lower() == 'build-tools'
            and _build_tools_version(directory)[0] >= 0
            and os.path.isfile(os.path.join(directory, 'lib', 'apksigner.jar')))


def _apksigner_java_command(wrapper):
    # The SDK's batch launcher uses CALL, which reparses every argument. Launch
    # its JAR directly so paths, aliases and other options reach Java literally.
    directory = os.path.dirname(os.path.realpath(wrapper))
    candidates = [os.path.join(directory, 'apksigner.jar'),
                  os.path.join(directory, 'lib', 'apksigner.jar'),
                  os.path.join(directory, '..', 'framework', 'apksigner.jar')]
    jar = next((path for path in candidates if os.path.isfile(path)), None)
    if jar is None:
        raise RuntimeError('apksigner.jar not found beside {0}'.format(wrapper))
    java_home = os.environ.get('JAVA_HOME', '').strip('"')
    if java_home:
        java = os.path.join(java_home, 'bin', 'java.exe')
        if not os.path.isfile(java):
            raise RuntimeError('java.exe not found in JAVA_HOME')
    else:
        java = shutil.which('java')
        if java is None:
            raise RuntimeError('java not found in PATH; please install Java or set JAVA_HOME')
    # Match the SDK wrapper's default VM settings.
    return [java, '-Xmx1024M', '-Xss1m', '-jar', jar]


def _run_subprocess(cmd, env=None):
    # Resolve apktool via PATH/PATHEXT as CreateProcess does not find .bat/.cmd
    # wrappers from the extensionless name. SDK commands are already resolved.
    child_env = None
    if env is not None:
        child_env = os.environ.copy()
        child_env.update(env)
    cmd = list(cmd)
    if cmd[0] == 'apktool':
        cmd[0] = _find_tool('apktool')
    is_batch = _IS_WINDOWS and os.path.splitext(cmd[0])[1].lower() in ('.bat', '.cmd')
    is_apktool_batch = is_batch and os.path.basename(cmd[0]).lower() in ('apktool.bat', 'apktool.cmd')
    if (is_batch and os.path.basename(cmd[0]).lower() in ('apksigner.bat', 'apksigner.cmd')
            and _is_sdk_apksigner(cmd[0])):
        cmd = _apksigner_java_command(cmd[0]) + cmd[1:]
        is_batch = False
    if is_batch:
        # Pass a command-line string so Popen does not re-escape the quotes for
        # the C runtime. /s strips the outer pair, preserving quoted paths.
        # Environment variables protect the initial cmd expansion only; a
        # wrapper using CALL can expand arguments again. Keep passwords out
        # of arguments. Disable delayed expansion for paths containing '!'.
        if child_env is None:
            child_env = os.environ.copy()
        arguments = []
        for index, argument in enumerate(cmd):
            if any(char in argument for char in ('"', '\r', '\n', '\0')):
                raise ValueError('Unsupported character in Windows batch argument')
            if argument == '':
                # cmd /c leaves an undefined %NAME% literal; empty variables
                # are treated as undefined. Encode the empty argument itself.
                arguments.append('""')
                continue
            key = 'APKUTIL_ARG_{0}'.format(index)
            # Batch wrappers forward %* to Java/native programs. A closing
            # quote after N backslashes must follow 2N backslashes so the
            # native argument parser preserves them and closes the quote.
            trailing_slashes = len(argument) - len(argument.rstrip('\\'))
            child_env[key] = argument + '\\' * trailing_slashes
            arguments.append('"%{0}%"'.format(key))
        shell = os.environ.get('COMSPEC', 'cmd.exe')
        command = '"{0}" /d /v:off /s /c "{1}"'.format(shell, ' '.join(arguments))
        cmd = command
    options = {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE}
    if is_apktool_batch:
        # The official wrapper runs PAUSE under cmd /c. Give it EOF rather
        # than inheriting a terminal or an open input pipe and waiting forever.
        options['stdin'] = subprocess.DEVNULL
    if child_env is not None:
        options['env'] = child_env
    proc = subprocess.Popen(cmd, **options)
    outs, errs = proc.communicate()
    # Tool output is not guaranteed to be ASCII (e.g. apktool's usage text
    # contains "Wiśniewski", and paths/locales may be non-ASCII), so decode
    # leniently instead of raising UnicodeDecodeError and hiding the real error.
    #
    # Success is judged by the exit code, not by whether stderr is empty:
    # adb, apktool and apksigner all write progress or warnings to stderr on
    # successful runs.
    return (outs.decode('utf-8', errors='replace'),
            errs.decode('utf-8', errors='replace'),
            proc.returncode)

def _error_message(cmd, outs, errs, returncode):
    # Prefer stderr, but some tools (e.g. apktool's usage text) report the
    # failure on stdout, and some (e.g. `pm path` for an unknown package)
    # print nothing at all.
    if len(errs.strip()) != 0:
        return errs
    if len(outs.strip()) != 0:
        return outs
    return '{0} exited with code {1}'.format(os.path.basename(cmd[0]), returncode)

def _parse_apktool_version(version_str):
    # `apktool --version` prints a bare "2.4.1" / "2.12.0-dirty" / "3.0.3" on
    # most versions, but 2.12.x rejects the option and prints its banner
    # ("Apktool 2.12.0 - a tool for ...", "with smali 3.0.9 ...") instead.
    # Anchor to the start of a line so the smali version is never picked up.
    match = re.search(r'^\s*(?:Apktool\s+)?v?(\d+)\.(\d+)(?:\.(\d+))?',
                      version_str or '', re.MULTILINE)
    if match is None:
        return None
    return tuple(int(n or 0) for n in match.groups())

def _get_apktool_version():
    outs, _, _ = _run_subprocess(['apktool', '--version'])
    return _parse_apktool_version(outs)

def _apktool_supports_use_aapt2():
    # `--use-aapt2` was removed in apktool 2.12.0 (aapt2 has been the default
    # since 2.9.0). Passing it to 2.12+/3.x fails with "Unrecognized option",
    # so only pass it to versions that still accept it. This keeps aapt2 builds
    # on apktool <= 2.8, where aapt1 is the default.
    version = _get_apktool_version()
    if version is None:
        return False
    return version < (2, 12, 0)

def _get_package_name(keyword):
    adb_path = _find_tool('adb')
    list_packages_cmd = [adb_path, 'shell', 'pm', 'list', 'packages']
    outs, errs, returncode = _run_subprocess(list_packages_cmd)
    if returncode != 0:
        raise Exception(_error_message(list_packages_cmd, outs, errs, returncode))

    package_list = outs.strip().splitlines()
    package_names = [line.split(":")[1] for line in package_list if keyword in line]
    return package_names if package_names else None

def _pull_apk_files(apk_paths):
    adb_path = _find_tool('adb')
    for apk_path in apk_paths:
        print(f"Pulling {apk_path}...")
        pull_cmd = [adb_path, 'pull', apk_path]
        outs, errs, returncode = _run_subprocess(pull_cmd)
        if returncode != 0:
            raise Exception(_error_message(pull_cmd, outs, errs, returncode))
        print(outs)
        # adb always outputs to stderr when command is successful
        # ex. /data/app/SPWhHCAAAELkPgU86YQ/hoge/base.apk: 1 file pulled, 0 skipped. 30.9 MB/s (23004210 bytes in 0.709s)
        print(errs)

def _get_apk_paths(package_name):
    adb_path = _find_tool('adb')
    path_cmd = [adb_path, 'shell', 'pm', 'path', package_name]
    outs, errs, returncode = _run_subprocess(path_cmd)
    if returncode != 0:
        raise Exception(_error_message(path_cmd, outs, errs, returncode))

    apk_paths = outs.strip().splitlines()
    return [line.split(":")[1] for line in apk_paths]

# Public methods
def pull_apks(keyword):
    try:
        package_names = _get_package_name(keyword)
        if not package_names:
            print(f"No package found matching keyword: {keyword}")
            return False

        questions = [
            inquirer.List('package_name',
                message="Select the APK to pull",
                choices=package_names + ['Not Found'],
                default='Not Found',
            ),
        ]
        
        answers = inquirer.prompt(questions)
        package_name = answers['package_name']
        
        if package_name == 'Not Found':
            print("Operation cancelled.")
            return False
        
        apk_paths = _get_apk_paths(package_name)
        if not apk_paths:
            print(f"No APK paths found for package: {package_name}")
            return False

        _pull_apk_files(apk_paths)

        print("APKs have been pulled to the current directory.")
        
        return True

    except (IndexError, FileNotFoundError):
        print(Fore.RED + 'adb not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False
    except Exception as e:
        print(Fore.RED + f"An error occurred: {e}")
        return False
        
def warn_if_apktool_outdated():
    try:
        version = _get_apktool_version()
    except FileNotFoundError:
        # decode()/build() report the missing apktool themselves.
        return

    if version is None:
        print(Fore.YELLOW + 'Could not determine the apktool version.')
        print(Fore.YELLOW + 'apkutil is tested with apktool {0} or later.'.format(
            '.'.join(map(str, APKTOOL_MIN_VERSION))))
    elif version < APKTOOL_MIN_VERSION:
        print(Fore.YELLOW + 'apktool {0} is outdated. Please upgrade to apktool {1} or later.'.format(
            '.'.join(map(str, version)), '.'.join(map(str, APKTOOL_MIN_VERSION))))

def decode(apk_path, no_res=False, no_src=False):
    apktool_cmd = ['apktool']
    apktool_cmd.extend(['d', apk_path])

    if no_res:
        apktool_cmd.extend(['-r'])

    if no_src:
        apktool_cmd.extend(['-s'])

    try:
        outs, errs, returncode = _run_subprocess(apktool_cmd)
        if (outs is not None) and (len(outs) != 0):
            print(outs)
        
        if returncode != 0:
            errs = _error_message(apktool_cmd, outs, errs, returncode)
            # unsupported `apktool d -f`
            errs = errs.replace('Use -f switch if you want to overwrite it.', '')
            raise Exception(errs)

        if (errs is not None) and (len(errs) != 0):
            # warnings on a successful decode
            print(Fore.YELLOW + errs)
        
        return True

    except FileNotFoundError as e:
        print('apktool not found.')
        print('Please install apktool')
        return False


def build(dir_name, apk_path):
    apktool_cmd = ['apktool']
    apktool_cmd.extend(['b', dir_name])
    apktool_cmd.extend(['-o', apk_path])

    try:
        if _apktool_supports_use_aapt2():
            apktool_cmd.extend(['--use-aapt2'])

        outs, errs, returncode = _run_subprocess(apktool_cmd)

        if (outs is not None) and (len(outs) != 0):
            print(outs)
        
        if returncode != 0:
            raise Exception(_error_message(apktool_cmd, outs, errs, returncode))

        if (errs is not None) and (len(errs) != 0):
            # warnings on a successful build
            print(Fore.YELLOW + errs)
        
        return True

    except FileNotFoundError as e:
        print(Fore.RED + 'apktool not found.')
        print(Fore.RED + 'Please install apktool.')
        return False

def align(apk_path):
    try:
        zipalign_path = _find_tool('zipalign')
        zipalign_cmd = [zipalign_path]
        zipalign_cmd.append('-f')
        zipalign_cmd.extend(['-p', '4'])
        zipalign_cmd.append(apk_path)
        with tempfile.TemporaryDirectory(prefix='apkutil-') as temp_dir:
            aligned_path = os.path.join(temp_dir, 'aligned.apk')
            zipalign_cmd.append(aligned_path)
            outs, errs, returncode = _run_subprocess(zipalign_cmd)
            if returncode != 0:
                raise Exception(_error_message(zipalign_cmd, outs, errs, returncode))

            shutil.move(aligned_path, apk_path)
        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'zipalign not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False

def sign(apk_path):
    home_dir = os.path.expanduser('~')
    keystore_path = ''
    ks_key_alias = ''
    ks_pass = ''

    try:
        with open(os.path.join(home_dir, 'apkutil.json')) as f:
            config = json.load(f)
            keystore_path = os.path.expanduser(config['keystore_path'])
            ks_key_alias = config['ks-key-alias']
            ks_pass = config['ks-pass']

    except:
        print('Please place `~/apkutil.json` containing the keystore information')
        return False

    try:
        if not os.path.isfile(apk_path):
            errs = '{0} is not found.'.format(apk_path)
            raise Exception(errs)

        apksigner_path = _find_tool('apksigner')
        apksigner_cmd = [apksigner_path]
        apksigner_cmd.append('sign')
        apksigner_cmd.extend(['-ks', keystore_path])
        apksigner_cmd.extend(['--v2-signing-enabled', 'true'])
        apksigner_cmd.append('-v')
        apksigner_cmd.extend(['--ks-key-alias', ks_key_alias])
        signing_env = None
        if ks_pass.startswith('pass:'):
            # apksigner.bat uses CALL, which reparses %NAME% even inside quoted
            # arguments. Let Java read the literal password from its own env.
            signing_env = {'APKUTIL_KS_PASS': ks_pass[len('pass:'):]}
            ks_pass = 'env:APKUTIL_KS_PASS'
        apksigner_cmd.extend(['--ks-pass', ks_pass])
        apksigner_cmd.append(apk_path)
        outs, errs, returncode = _run_subprocess(apksigner_cmd, env=signing_env)
        if (outs is not None) and (len(outs) != 0):
            print(Fore.CYAN + outs)
        
        if returncode != 0:
            print(Fore.RED + _error_message(apksigner_cmd, outs, errs, returncode))
            return False

        if (errs is not None) and (len(errs) != 0):
            # e.g. JVM warnings on a successful signing
            print(Fore.YELLOW + errs)
        
        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'apksigner not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False


def get_packagename(apk_path):
    try:
        aapt2_path = _find_tool('aapt2')
        aapt2_cmd = [aapt2_path]
        aapt2_cmd.append('dump')
        aapt2_cmd.append('packagename')
        aapt2_cmd.append(apk_path)
        outs, errs, returncode = _run_subprocess(aapt2_cmd)
        if (outs is not None) and (len(outs) != 0):
            print(outs)

        if returncode != 0:
            raise Exception(_error_message(aapt2_cmd, outs, errs, returncode))

        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'aapt2 not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False

def get_screenshot():
    try:
        adb_path = _find_tool('adb')
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
        screenshot_file = 'screenshot-' + timestamp + '.png'
        screenshot_path = '/data/local/tmp/' + screenshot_file

        screencap_cmd = [adb_path]
        screencap_cmd.append('shell')
        screencap_cmd.append('screencap')
        screencap_cmd.extend(['-p', screenshot_path])
        outs, errs, returncode = _run_subprocess(screencap_cmd)
        if returncode != 0:
            raise Exception(_error_message(screencap_cmd, outs, errs, returncode))

        pull_cmd = [adb_path]
        pull_cmd.append('pull')
        pull_cmd.append(screenshot_path)
        outs, errs, returncode = _run_subprocess(pull_cmd)
        if returncode != 0:
            raise Exception(_error_message(pull_cmd, outs, errs, returncode))
        # Logs are output to stderr even if command execution is successful.
        print(errs)

        rm_cmd = [adb_path]
        rm_cmd.append('shell')
        rm_cmd.append('rm')
        rm_cmd.append(screenshot_path)
        outs, errs, returncode = _run_subprocess(rm_cmd)
        if returncode != 0:
            print(Fore.YELLOW + _error_message(rm_cmd, outs, errs, returncode))

        return screenshot_file

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'adb not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False


def check_sensitive_files(target_path):
    types = ('**/*.md', '**/*.cpp', '**/*.c', '**/*.h', '**/*.java', '**/*.kts',
        '**/*.bat', '**/*.sh', '**/*.template', '**/*.gradle', '**/*.json', '**/*.yml', '**/*.txt')
    allow_list = ('apktool.yml', os.sep + os.path.join('assets', 'google-services-desktop.json'),
        os.sep + os.path.join('assets', 'bin', 'Data', 'RuntimeInitializeOnLoads.json'),
        os.sep + os.path.join('assets', 'bin', 'Data', 'ScriptingAssemblies.json'))
    found_files = []
    for file_type in types:
        found_files.extend(glob.glob(os.path.join(target_path, file_type), recursive=True))
    
    sensitive_files = []
    for found_file in found_files:
        allow_flag = False
        for allow_file in allow_list:
            if found_file.endswith(allow_file):
                allow_flag = True
                break
        if not allow_flag:
            sensitive_files.append(found_file)

    if len(sensitive_files) == 0:
        print(Fore.BLUE + 'None')
    else:
        for sensitive_file in sensitive_files:
            print(Fore.RED + sensitive_file)
    print('')
    return sensitive_files

def make_network_security_config(target_path):
    xml_path = os.path.join(target_path, 'res/xml')
    if not os.path.exists(xml_path):
        os.makedirs(xml_path)

    with open(os.path.join(target_path, 'res/xml/network_security_config.xml'),'w') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n' +
            '<network-security-config>\n' +
            '    <base-config>\n' +
            '        <trust-anchors>\n' +
            '            <certificates src="system" />\n' +
            '            <certificates src="user" />\n' +
            '        </trust-anchors>\n' +
            '    </base-config>\n' +
            '</network-security-config>')
