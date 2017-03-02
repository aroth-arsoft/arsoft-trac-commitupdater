#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;

import sys 
import os.path

from arsoft.trac.plugins.commitupdater import *
import trac.env
import time, unittest
from trac.util.datefmt import time_now, utc
from trac.core import ComponentManager
from trac.versioncontrol.api import Repository, Changeset
from tracopt.versioncontrol.git.git_fs import GitRepository
from trac.test import EnvironmentStub, Mock, MockRequest

class test_commitupdater(unittest.TestCase):

    @staticmethod
    def insert_users(env, users):
        """Insert a tuple representing a user session to the
        `session` and `session_attributes` tables.

        The tuple can be length 3 with entries username, name and
        email, in which case an authenticated user is assumed. The
        tuple can also be length 4, with the last entry specifying
        `1` for an authenticated user or `0` for an unauthenticated
        user.
        """
        with env.db_transaction as db:
            for row in users:
                if len(row) == 3:
                    username, name, email = row
                    authenticated = 1
                else:  # len(row) == 4
                    username, name, email, authenticated = row
                db("INSERT INTO session VALUES (%s, %s, %s)",
                   (username, authenticated, int(time_now())))
                db("INSERT INTO session_attribute VALUES (%s,%s,'name',%s)",
                   (username, authenticated, name))
                db("INSERT INTO session_attribute VALUES (%s,%s,'email',%s)",
                   (username, authenticated, email))

    def setUp(self):
        self._script_dir = os.path.abspath(os.path.dirname(__file__))
        self._tmp_dir = os.path.join(self._script_dir, 'tmp')
        if not os.path.isdir(self._tmp_dir):
            os.mkdir(self._tmp_dir)
        self._env_dir = os.path.join(self._tmp_dir, 'env')
        if not os.path.isdir(self._env_dir):
            self._env = trac.env.Environment(path=self._env_dir, create=True)
            test_commitupdater.insert_users(self._env, [('user1', 'User C', 'user1@example.org'),
                                ('user2', 'User A', 'user2@example.org'),
                                ('user3', 'User D', 'user3@example.org'),
                                ('user4', 'User B', 'user4@example.org')])
        else:
            self._env = trac.env.open_environment(self._env_dir)
        self._committicketupdater = CommitTicketUpdater(self._env)


        self._commit_hash = 'd952a7d7d0c24c02feef500ecbe141e49ff84708'

        #self._repo = Repository("Test_repo",{'name': "Test_repo", 'id': 4321},"tmp.log")
        self._repo = GitRepository(self._env, path=self._script_dir, params={'name': "Test_repo", 'id': 4321}, log=self._env.log)

        # Set all component objects to defaults
        self._env.config.set("ticket","commit_ticket_update_commands.close","close closed closes fix fixed fixes")
        self._env.config.set("ticket","commit_ticket_update_commands.implements","implement implements implemented impl")
        self._env.config.set("ticket","commit_ticket_update_commands.invalidate","invalid invalidate invalidated invalidates")
        self._env.config.set("ticket","commit_ticket_update_commands.refs","addresses re references refs see")
        self._env.config.set("ticket","commit_ticket_update_commands.rejects","reject rejects rejected")
        self._env.config.set("ticket","commit_ticket_update_commands.worksforme","worksforme")
        self._env.config.set("ticket","commit_ticket_update_commands.alreadyimplemented","alreadyimplemented already_implemented")
        self._env.config.set("ticket","commit_ticket_update_commands.reopen","reopen reopens reopened")
        self._env.config.set("ticket","commit_ticket_update_commands.testready","testready test_ready ready_for_test rft")
        self._env.config.set("ticket","commit_ticket_update_allowed_domains","mydomain")

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
        test_changeset = Mock(Changeset, self._repo, self._commit_hash, message,
                         'user@example.com', None)

        #test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
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
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_invalidate])

    def test_check_rejects(self):
        message = "Fixed some stuff. reject #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_rejects])

    def test_check_worksforme(self):
        message = "Fixed some stuff. worksforme #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_worksforme])

    def test_check_alreadyimplemented(self):
        message = "Fixed some stuff. alreadyimplemented #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_alreadyimplemented])

    def test_check_already_implemented(self):
        message = "Fixed some stuff. already_implemented #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_alreadyimplemented])

    def test_check_reopens(self):
        message = "Fixed some stuff. reopen #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_reopens])

    def test_check_testready(self):
        message = "Fixed some stuff. ready_for_test #1"
        test_changeset = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[1])
        # Now check the actions are right
        self.assertEqual(tickets.get(1),[self._committicketupdater.cmd_testready])

    def test_allowed_domains(self):
        message = "Fixed some stuff. reopen #1"

        test_changeset_declined = Changeset(None,self._commit_hash,message,"test_person <me@gohome.now>",time.time())
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_declined.author),False)

        test_changeset_allowed = Changeset(None,self._commit_hash,message,"test_person <me@mydomain>",time.time())
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_allowed.author),True)

        test_changeset_no_domain = Changeset(None,self._commit_hash,message,"test_person",time.time())
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_no_domain.author),True)

if __name__ == '__main__':
    unittest.main()
