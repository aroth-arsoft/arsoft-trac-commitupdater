#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;
 
import sys 
import os.path

from arsoft.trac.plugins.commitupdater import *
import trac.env
import time, unittest
from trac.core import ComponentManager
from trac.versioncontrol.api import Repository, Changeset

class test_commitupdater(unittest.TestCase):

    def setUp(self):
        self._script_dir = os.path.abspath(os.path.dirname(__file__))
        self._env_dir = os.path.join(self._script_dir, 'tmp', 'env')

        self._env = trac.env.open_environment(self._env_dir)
        self._committicketupdater = CommitTicketUpdater(self._env)

        self._repo = Repository("Test_repo",{'name': "Test_repo", 'id': 4321},"tmp.log")

        # Set all component objects to defaults
        self._env.config.set("ticket","commit_ticket_update_commands.close","close closed closes fix fixed fixes")
        self._env.config.set("ticket","commit_ticket_update_commands.implements","implement implements implemented impl")
        self._env.config.set("ticket","commit_ticket_update_commands.invalidate","invalid invalidate invalidated invalidates")
        self._env.config.set("ticket","commit_ticket_update_commands.refs","addresses re references refs see")
        self._env.config.set("ticket","commit_ticket_update_commands.rejects","reject rejects rejected")

    def build_comment(self,changeset):
        revstring = str(changeset.rev)
        if self._repo.name:
            revstring += '/' + self._repo.name
        
        return """In [changeset:"%s"]:
{{{
#!CommitTicketReference repository="%s" revision="%s"
%s
}}}""" % (revstring, self._repo.name, changeset.rev, changeset.message)

    def check_ticket_comment(self,changeset):
        for obj in [self._env]:
            self.assertEqual(self._committicketupdater.make_ticket_comment(self._repo,changeset), self.build_comment(changeset))

    def test_check_implements(self):
        message = "Fixed some stuff. implements #1"
        test_changeset = Changeset(None,1234,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_implements])
        
    def test_check_invalidate(self):
        message = "Fixed some stuff. invalid #1"
        test_changeset = Changeset(None,1234,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_invalidate])

if __name__ == '__main__':
    unittest.main()
