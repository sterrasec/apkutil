#!/usr/bin/env python3
# coding: UTF-8

import datetime
import glob
import json
import os
import shutil
import subprocess

from colorama import Fore
import inquirer

ANDROID_SDK_DEFAULT_PATH = '/Library/Android/sdk/'
ANDROID_HOME = os.environ.get('ANDROID_HOME', ANDROID_SDK_DEFAULT_PATH)

# Private methods
def _run_subprocess(cmd):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outs, errs = proc.communicate()
    return outs.decode('ascii'), errs.decode('ascii')

def _get_package_name(keyword):
    adb_path = glob.glob(ANDROID_HOME + '/platform-tools/adb')[0]
    list_packages_cmd = [adb_path, 'shell', 'pm', 'list', 'packages']
    outs, errs = _run_subprocess(list_packages_cmd)
    if (errs is not None) and (len(errs) != 0):
        raise Exception(errs)

    package_list = outs.strip().splitlines()
    package_names = [line.split(":")[1] for line in package_list if keyword in line]
    return package_names if package_names else None

def _pull_apk_files(apk_paths):
    adb_path = glob.glob(ANDROID_HOME + '/platform-tools/adb')[0]
    for apk_path in apk_paths:
        print(f"Pulling {apk_path}...")
        pull_cmd = [adb_path, 'pull', apk_path]
        outs, errs = _run_subprocess(pull_cmd)
        print(outs)
        # adb always outputs to stderr when command is successful
        # ex. /data/app/SPWhHCAAAELkPgU86YQ/hoge/base.apk: 1 file pulled, 0 skipped. 30.9 MB/s (23004210 bytes in 0.709s)
        print(errs)

def _get_apk_paths(package_name):
    adb_path = glob.glob(ANDROID_HOME + '/platform-tools/adb')[0]
    path_cmd = [adb_path, 'shell', 'pm', 'path', package_name]
    outs, errs = _run_subprocess(path_cmd)
    if (errs is not None) and (len(errs) != 0):
        raise Exception(errs)

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
        
def decode(apk_path, no_res=False, no_src=False):
    apktool_cmd = ['apktool']
    apktool_cmd.extend(['d', apk_path])

    if no_res:
        apktool_cmd.extend(['-r'])

    if no_src:
        apktool_cmd.extend(['-s'])

    try:
        outs, errs = _run_subprocess(apktool_cmd)
        if (outs is not None) and (len(outs) != 0):
            print(outs)
        
        if (errs is not None) and (len(errs) != 0):
            # unsupported `apktool d -f`
            errs = errs.replace('Use -f switch if you want to overwrite it.', '')
            raise Exception(errs)
        
        return True

    except FileNotFoundError as e:
        print('apktool not found.')
        print('Please install apktool')
        return False


def build(dir_name, apk_path, aapt2=False):
    apktool_cmd = ['apktool']
    apktool_cmd.extend(['b', dir_name])
    apktool_cmd.extend(['-o', apk_path])

    if aapt2:
        apktool_cmd.extend(['--use-aapt2'])
    
    try:
        outs, errs = _run_subprocess(apktool_cmd)

        is_built = False

        if (outs is not None) and (len(outs) != 0):
            if "I: Built apk..." in outs:
                is_built = True

            print(outs)
        
        if (errs is not None) and (len(errs) != 0) and not is_built:
            raise Exception(errs)
        
        return True

    except FileNotFoundError as e:
        print(Fore.RED + 'apktool not found.')
        print(Fore.RED + 'Please install apktool.')
        return False

def align(apk_path):
    try:
        zipalign_path = glob.glob(ANDROID_HOME + '/build-tools/*/zipalign')[0]
        zipalign_cmd = [zipalign_path]
        zipalign_cmd.append('-f')
        zipalign_cmd.extend(['-p', '4'])
        zipalign_cmd.append(apk_path)
        zipalign_cmd.append('/tmp/apkutil_tmp.aligned.apk')
        _, errs = _run_subprocess(zipalign_cmd)
        if len(errs) != 0:
            raise Exception(errs)

        shutil.move('/tmp/apkutil_tmp.aligned.apk', apk_path)
        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'zipalign not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False

def sign(apk_path):
    home_dir = os.environ['HOME']
    keystore_path = ''
    ks_key_alias = ''
    ks_pass = ''

    try:
        with open(home_dir + "/apkutil.json") as f:
            config = json.load(f)
            keystore_path = config['keystore_path'].replace('~', home_dir)
            ks_key_alias = config['ks-key-alias']
            ks_pass = config['ks-pass']

    except:
        print('Please place `~/apkutil.json` containing the keystore information')
        return False

    try:
        if not os.path.isfile(apk_path):
            errs = '{0} is not found.'.format(apk_path)
            raise Exception(errs)

        apksigner_path = glob.glob(ANDROID_HOME + '/build-tools/*/apksigner')[0]
        apksigner_cmd = [apksigner_path]
        apksigner_cmd.append('sign')
        apksigner_cmd.extend(['-ks', keystore_path])
        apksigner_cmd.extend(['--v2-signing-enabled', 'true'])
        apksigner_cmd.append('-v')
        apksigner_cmd.extend(['--ks-key-alias', ks_key_alias])
        apksigner_cmd.extend(['--ks-pass', ks_pass])
        apksigner_cmd.append(apk_path)
        outs, errs = _run_subprocess(apksigner_cmd)
        if (outs is not None) and (len(outs) != 0):
            print(Fore.CYAN + outs)
        
        if (errs is not None) and (len(errs) != 0):
            print(Fore.RED + errs)
            return False
        
        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'apksigner not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False


def get_packagename(apk_path):
    try:
        aapt_path = glob.glob(ANDROID_HOME + '/build-tools/*/aapt')[0]
        aapt_cmd = [aapt_path]
        aapt_cmd.append('l')
        aapt_cmd.append('-a')
        aapt_cmd.append(apk_path)
        aapt_proc = subprocess.Popen(aapt_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        grep_proc = subprocess.Popen(["grep", "A: package"], stdin=aapt_proc.stdout)
        aapt_proc.stdout.close()
        outs, errs = grep_proc.communicate()
        outs, errs = outs, errs
        if (outs is not None) and (len(outs) != 0):
            print(outs.decode('ascii'))

        if (errs is not None) and (len(errs) != 0):
            raise Exception(errs.decode('ascii'))
        
        return True

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'apksigner not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False

def get_screenshot():
    try:
        adb_path = glob.glob(ANDROID_HOME + '/platform-tools/adb')[0]
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d-%H-%M-%S")
        screenshot_file = 'screenshot-' + timestamp + '.png'
        screenshot_path = '/data/local/tmp/' + screenshot_file

        screencap_cmd = [adb_path]
        screencap_cmd.append('shell')
        screencap_cmd.append('screencap')
        screencap_cmd.extend(['-p', screenshot_path])
        _, errs = _run_subprocess(screencap_cmd)
        if (errs is not None) and (len(errs) != 0):
            raise Exception(errs)

        pull_cmd = [adb_path]
        pull_cmd.append('pull')
        pull_cmd.append(screenshot_path)
        _, errs = _run_subprocess(pull_cmd)
        # Logs are output to stderr even if command execution is successful.
        print(errs)

        rm_cmd = [adb_path]
        rm_cmd.append('shell')
        rm_cmd.append('rm')
        rm_cmd.append(screenshot_path)
        _, errs = _run_subprocess(rm_cmd)
        if (errs is not None) and (len(errs) != 0):
            print(errs)

        return screenshot_file

    except (IndexError, FileNotFoundError) as e:
        print(Fore.RED + 'adb not found.')
        print(Fore.RED + 'Please install Android SDK Build Tools.')
        return False


def check_sensitive_files(target_path):
    types = ('**/*.md', '**/*.cpp', '**/*.c', '**/*.h', '**/*.java', '**/*.kts',
        '**/*.bat', '**/*.sh', '**/*.template', '**/*.gradle', '**/*.json', '**/*.yml', '**/*.txt')
    allow_list = ('apktool.yml', '/assets/google-services-desktop.json',
        '/assets/bin/Data/RuntimeInitializeOnLoads.json', '/assets/bin/Data/ScriptingAssemblies.json')
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
