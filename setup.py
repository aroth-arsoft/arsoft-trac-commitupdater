#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;
import os

from setuptools import setup

setup(name='arsoft-trac-commitupdater',
        version='0.16',
        description='A plugin to update tickets within Trac when certain keywords are using in commit messages.',
        long_description = open(os.path.join(os.path.dirname(__file__), 'README.md')).read(),
        author='Andreas Roth',
        author_email='aroth@arsoft-online.com',
        url='http://www.arsoft-online.com/',
        packages=['arsoft.trac.plugins.commitupdater'],
        keywords = 'trac commit update ticket issue bug',
        license = 'BSD',
        classifiers = [
            'Framework :: Trac',
            #'Development Status :: 1 - Planning',
            #'Development Status :: 2 - Pre-Alpha',
            # 'Development Status :: 3 - Alpha',
            #'Development Status :: 4 - Beta',
            'Development Status :: 5 - Production/Stable',
            # 'Development Status :: 6 - Mature',
            # 'Development Status :: 7 - Inactive',
            'Environment :: Web Environment',
            'License :: OSI Approved :: BSD License',
            'Natural Language :: English',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
        ],

        install_requires = ['Trac >= 1.0'],
        entry_points = {
            'trac.plugins': [
                'arsoft.trac.plugins.commitupdater = arsoft.trac.plugins.commitupdater',
                ]
            }
        )
