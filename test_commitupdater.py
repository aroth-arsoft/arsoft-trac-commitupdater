#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;

from __future__ import print_function
import sys
import os.path

from arsoft.trac.plugins.commitupdater import *
import trac.env
import time, unittest
from trac.util.datefmt import time_now, utc
from trac.core import ComponentManager
from trac.versioncontrol.api import Repository, Changeset, NoSuchChangeset
from tracopt.versioncontrol.git.git_fs import GitRepository
from trac.perm import PermissionSystem
from trac.test import EnvironmentStub, Mock, MockRequest

class MockRepository(Repository):

    has_linear_changesets = True

    def get_youngest_rev(self):
        return 100

    def normalize_path(self, path):
        return path.strip('/') if path else ''

    def normalize_rev(self, rev):
        if rev is None or rev == '':
            return self.youngest_rev
        try:
            nrev = int(rev)
        except:
            raise NoSuchChangeset(rev)
        else:
            if not (1 <= nrev <= self.youngest_rev):
                raise NoSuchChangeset(rev)
            return nrev

    def get_node(self, path, rev):
        assert rev % 3 == 1  # allow only 3n + 1
        assert path in ('file', 'file-old')
        return MockNode(self, path, rev, Node.FILE)

    def get_changeset(self, rev):
        assert rev % 3 == 1  # allow only 3n + 1
        return MockChangeset(self, rev, 'message-%d' % rev, 'author-%d' % rev,
                             datetime(2001, 1, 1, tzinfo=utc) +
                             timedelta(seconds=rev))

    def previous_rev(self, rev, path=''):
        return rev - 1 if rev > 0 else None

    def rev_older_than(self, rev1, rev2):
        return self.normalize_rev(rev1) < self.normalize_rev(rev2)

    def close(self):
        pass

    def _not_implemented(self, *args, **kwargs):
        raise NotImplementedError

    get_changes = _not_implemented
    get_oldest_rev = _not_implemented
    next_rev = _not_implemented

class test_commitupdater(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

        self.perm_sys = PermissionSystem(self.env)
        self.env.insert_users([('user1', 'User C', 'user1@example.org'),
                               ('user2', 'User A', 'user2@example.org'),
                               ('user3', 'User D', 'user3@example.org'),
                               ('user4', 'User B', 'user4@example.org')])
        self.perm_sys.grant_permission('user1', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user2', 'TICKET_VIEW')
        self.perm_sys.grant_permission('user3', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user4', 'TICKET_MODIFY')

        self._committicketupdater = CommitTicketUpdater(self.env)


        #self.repo = Mock(Repository, 'testrepo',
        #            {'name': 'testrepo', 'id': 4321}, None)
        self.repo = Mock(MockRepository, 'testrepo',
                    {'name': 'testrepo', 'id': 4321}, None)

        # Set all component objects to defaults
        config = self.env.config
        config.set("ticket","commit_ticket_update_commands.close","close closed closes fix fixed fixes")
        config.set("ticket","commit_ticket_update_commands.implements","implement implements implemented impl")
        config.set("ticket","commit_ticket_update_commands.invalidate","invalid invalidate invalidated invalidates")
        config.set("ticket","commit_ticket_update_commands.refs","addresses re references refs see")
        config.set("ticket","commit_ticket_update_commands.rejects","reject rejects rejected")
        config.set("ticket","commit_ticket_update_commands.worksforme","worksforme")
        config.set("ticket","commit_ticket_update_commands.alreadyimplemented","alreadyimplemented already_implemented")
        config.set("ticket","commit_ticket_update_commands.reopen","reopen reopens reopened")
        config.set("ticket","commit_ticket_update_commands.testready","testready test_ready ready_for_test rft")
        config.set("ticket","commit_ticket_update_allowed_domains","mydomain")

    def tearDown(self):
        self.env.reset_db()

    def _add_component(self, name='test', owner='owner1'):
        component = Component(self.env)
        component.name = name
        component.owner = owner
        component.insert()

    def build_comment(self,changeset):
        revstring = str(changeset.rev)
        drev = str(self.repo.display_rev(changeset.rev))
        if self.repo.name:
            revstring += '/' + self.repo.name
            drev += '/' + self.repo.name

        return """In [changeset:"%s" %s]:
{{{
#!CommitTicketReference repository="%s" revision="%s"
%s
}}}""" % (revstring, drev, self.repo.name, changeset.rev, changeset.message)

    def check_ticket_comment(self,changeset):
        for obj in [self.env]:
            #print('comment=%s' % self.build_comment(changeset), file=sys.stderr)
            self.assertEqual(self._committicketupdater.make_ticket_comment(self.repo,changeset), self.build_comment(changeset))

    def test_check_implements(self):
        message = "Fixed some stuff. implements #1"
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)

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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user@example.com', None)
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

        test_changeset_declined = Mock(Changeset, self.repo, 42, message,
                         "test_person <me@gohome.now>", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_declined.author),False)

        test_changeset_allowed = Mock(Changeset, self.repo, 42, message,
                         "test_person <me@mydomain>", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_allowed.author),True)

        test_changeset_no_domain = Mock(Changeset, self.repo, 42, message,
                         "test_person", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_no_domain.author),False)

if __name__ == '__main__':
    unittest.main()
