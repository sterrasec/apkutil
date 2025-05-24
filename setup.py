#!/usr/bin/env python3
# coding: UTF-8

from setuptools import setup

setup(
    name="apkutil",
    version="0.1.8",
    description="decode, patch, build, etc",
    author="Taichi Kotake",
    packages=['apkutil'],
    entry_points={
        'console_scripts': [
            'apkutil = apkutil.cli:main',
        ],
    },
    install_requires=[
        'inquirer',
        'colorama',
        'defusedxml'
    ],
    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
