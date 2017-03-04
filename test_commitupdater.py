#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;

from __future__ import print_function
import sys
import os.path

from arsoft.trac.plugins.commitupdater import *
import trac.env
import time, unittest
from trac import perm
from trac.util.datefmt import time_now, utc
from trac.core import ComponentManager
from trac.ticket.model import Component
from trac.ticket import TicketSystem
from trac.versioncontrol.api import Repository, Changeset, NoSuchChangeset
from trac.web.session import Session
from trac.wiki.web_ui import ReadonlyWikiPolicy
from tracopt.versioncontrol.git.git_fs import GitRepository
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


    def _test_authenticated_session(self, username, fullname, email):
        """
        Verifies that a session cookie does not get used if the user is logged
        in, and that Trac expires the cookie.
        """
        req = MockRequest(self.env, authname=username)
        req.incookie['trac_session'] = '123456'
        session = Session(self.env, req)
        self.assertEqual(username, session.sid)
        session['email'] = email
        session['name'] = fullname
        session.save()

    def setUp(self):
        self.env = \
            EnvironmentStub(enable=['trac.attachment.LegacyAttachmentPolicy',
                                    'trac.perm.*',
                                    'trac.wiki.web_ui.ReadonlyWikiPolicy',
                                    'trac.ticket.*'])
        self.policy = ReadonlyWikiPolicy(self.env)
        store = perm.DefaultPermissionStore(self.env)


        self.perm_sys = perm.PermissionSystem(self.env)
        users = [('user1', 'User C', 'user1@example.org'),
                               ('user2', 'User A', 'user2@example.org'),
                               ('user3', 'User D', 'user3@example.org'),
                               ('user4', 'User B', 'user4@example.org')]
        self.env.insert_users(users)
        store.grant_permission('user1', 'TICKET_MODIFY')
        store.grant_permission('user2', 'TICKET_VIEW')
        store.grant_permission('user3', 'TICKET_MODIFY')
        store.grant_permission('user4', 'TICKET_MODIFY')

        for (username, fullname, email) in users:
            self._test_authenticated_session(username, fullname, email)

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
        config.set("ticket","commit_ticket_update_allowed_domains","example.org mydomain.net")
        #config.set("ticket","commit_ticket_update_check_perms",False)

        self._add_component('component3', 'user3')

        self.ticket = Ticket(self.env)
        self.ticket.populate({
            'reporter': 'user1',
            'summary': 'the summary',
            'component': 'component3',
            'owner': 'user3',
            'status': 'new',
        })
        self.tkt_id = self.ticket.insert()

        self.ticket2 = Ticket(self.env)
        self.ticket2.populate({
            'reporter': 'user2',
            'summary': 'the summary',
            'component': 'component3',
            'owner': 'user2',
            'status': 'new',
        })
        self.tkt2_id = self.ticket2.insert()

        #for username, name, email in self.env.get_known_users():
         #   sys.stderr.write('known user %s, %s, %s\n' % (username, name, email))

        with self.env.db_transaction as db:
            db("INSERT INTO enum VALUES ('resolution', 'already_implemented', 6)")
            #db("INSERT INTO enum VALUES ('resolution', 'worksforme', 5)")

        self._committicketupdater = CommitTicketUpdater(self.env)

    def noop(self):
        pass


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

    def test_check_closes(self):
        message = "Fixed some stuff. closes #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_close])

        ret = ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['owner'], 'user1')
        self.assertEqual(ticket['resolution'], 'fixed')

    def test_check_implements(self):
        message = "Fixed some stuff. implements #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)

        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_implements])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'implemented')
        self.assertEqual(ticket['owner'], 'user1')

    def test_check_invalidate(self):
        message = "Fixed some stuff. invalid #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_invalidate])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['resolution'], 'invalid')

    def test_check_rejects(self):
        message = "Fixed some stuff. reject #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_rejects])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'rejected')

    def test_check_worksforme(self):
        message = "Fixed some stuff. worksforme #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_worksforme])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['resolution'], 'worksforme')

    def test_check_alreadyimplemented(self):
        message = "Fixed some stuff. alreadyimplemented #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_alreadyimplemented])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['resolution'], 'already_implemented')

    def test_check_already_implemented(self):
        message = "Fixed some stuff. already_implemented #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_alreadyimplemented])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['resolution'], 'already_implemented')

    def test_check_reopens(self):
        message = "Fixed some stuff. worksforme #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)

        message = "Fixed some stuff. reopen #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_reopens])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'reopened')

    def test_check_testready(self):
        message = "Fixed some stuff. ready_for_test #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_testready])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'test_ready')

    def test_allowed_domains(self):
        message = "Fixed some stuff. reopen #%i" % self.tkt_id

        test_changeset_declined = Mock(Changeset, self.repo, 42, message,
                         "test_person <me@gohome.now>", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_declined.author),False)

        test_changeset_allowed = Mock(Changeset, self.repo, 42, message,
                         "test_person <me@mydomain.net>", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_allowed.author),True)

        test_changeset_no_domain = Mock(Changeset, self.repo, 42, message,
                         "test_person", None)
        self.assertEqual(self._committicketupdater._is_author_allowed(test_changeset_no_domain.author),False)

        message = "Fixed some stuff. fixed #%i" % self.tkt_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'test_person <me@gohome.now>', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])

        ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'new')

    def test_check_closes_multiple(self):
        message = "Fixed some stuff. closes #%i, #%i" % (self.tkt_id, self.tkt2_id)
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id, self.tkt2_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_close])
        self.assertEqual(tickets.get(self.tkt2_id),[self._committicketupdater.cmd_close])

        ret = ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['owner'], 'user1')
        self.assertEqual(ticket['resolution'], 'fixed')

        (cmds, ticket2) = ret[self.tkt2_id]
        self.assertEqual(ticket2['status'], 'closed')
        self.assertEqual(ticket2['owner'], 'user1')
        self.assertEqual(ticket2['resolution'], 'fixed')

    def test_check_closes_non_existing_ticket(self):
        non_existing_ticket_id = 12345
        message = "Fixed some stuff. closes #%i" % non_existing_ticket_id
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'user1@example.org', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[non_existing_ticket_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(non_existing_ticket_id),[self._committicketupdater.cmd_close])

        ret = ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[non_existing_ticket_id]
        self.assertEqual(ticket, None)

    def test_check_closes_with_full_email_addr(self):
        message = "Fixed some stuff. closes #%i" % (self.tkt_id)
        test_changeset = Mock(Changeset, self.repo, 42, message,
                         'User One <user1@example.org>', None)
        self.check_ticket_comment(test_changeset)
        # For each object in turn:
        # Get tickets and commands
        tickets = self._committicketupdater._parse_message(message)
        # First, check we've got the tickets we were expecting
        self.assertEqual(tickets.keys(),[self.tkt_id])
        # Now check the actions are right
        self.assertEqual(tickets.get(self.tkt_id),[self._committicketupdater.cmd_close])

        ret = ret = self._committicketupdater.changeset_added_impl(self.repo, test_changeset)
        (cmds, ticket) = ret[self.tkt_id]
        self.assertEqual(ticket['status'], 'closed')
        self.assertEqual(ticket['owner'], 'user1')
        self.assertEqual(ticket['resolution'], 'fixed')

if __name__ == '__main__':
    unittest.main()
    #t = test_commitupdater(methodName='noop')
    #t.setUp()
    #t.test_check_implements_cmd()
    #t.tearDown()
