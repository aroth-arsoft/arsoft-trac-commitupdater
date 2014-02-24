#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;

from setuptools import setup

setup(name='arsoft-trac-commitupdater',
        version='0.8',
        description='A plugin to update tickets within Trac when certain keywords are using in commit messages.',
        author='Andreas Roth',
        author_email='aroth@arsoft-online.com',
        url='http://www.arsoft-online.com/',
        packages=['arsoft.trac.plugins.commitupdater'],
        keywords = 'trac commit update ticket issue bug',
        license = 'BSD',
        install_requires = ['Trac >= 1.0'],
        entry_points = {
            'trac.plugins': [
                'arsoft.trac.plugins.commitupdater = arsoft.trac.plugins.commitupdater',
                ]
            }
        )
