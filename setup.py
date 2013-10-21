# -*- coding: utf-8 -*-
import sys
import os
import accelerator

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()


setup(
    name='wsgi-accelerator',
    version=accelerator.__version__,
    description='Simple HTTP cache for WSGI apps with fine-grained invalidation',
    long_description=open('README.rst').read(),
    author='Carl Byström',
    author_email='cgbystrom@gmail.com',
    url='https://github.com/cgbystrom/wsgi-accelerator',
    packages=['accelerator', 'accelerator.stores'],
    package_data={'': ['LICENSE', 'README.rst']},
    package_dir={'accelerator': 'accelerator'},
    include_package_data=True,
    install_requires=[],
    license=open('LICENSE').read(),
    zip_safe=False,
    classifiers=(
        'Development Status :: 3 - Alpha    ',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ),
)