#!/usr/bin/python
# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; mixedindent off; indent-mode python;
#
# Copyright (C) 2009-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

# This plugin was based on the contrib/trac-post-commit-hook script, which
# had the following copyright notice:
# ----------------------------------------------------------------------------
# Copyright (c) 2004 Stephen Hansen
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
# ----------------------------------------------------------------------------

from __future__ import with_statement

import re
import textwrap

from trac.config import BoolOption, Option
from trac.core import Component, implements
from trac.notification.api import NotificationSystem
from trac.perm import PermissionCache
from trac.resource import Resource, ResourceNotFound
from trac.ticket import Ticket
from trac.ticket.notification import TicketChangeEvent
from trac.util.datefmt import datetime_now, utc
from trac.util.html import tag
from trac.util.text import exception_to_unicode
from trac.util.translation import _, cleandoc_
from trac.versioncontrol import IRepositoryChangeListener, RepositoryManager
from trac.versioncontrol.web_ui.changeset import ChangesetModule
from trac.wiki.formatter import format_to_html
from trac.wiki.macros import WikiMacroBase


class CommitTicketUpdater(Component):
    """Update tickets based on commit messages.

    This component hooks into changeset notifications and searches commit
    messages for text in the form of:
    {{{
    command #1
    command #1, #2
    command #1 & #2
    command #1 and #2
    }}}

    Instead of the short-hand syntax "#1", "ticket:1" can be used as well,
    e.g.:
    {{{
    command ticket:1
    command ticket:1, ticket:2
    command ticket:1 & ticket:2
    command ticket:1 and ticket:2
    }}}

    Using the long-form syntax allows a comment to be included in the
    reference, e.g.:
    {{{
    command ticket:1#comment:1
    command ticket:1#comment:description
    }}}

    In addition, the ':' character can be omitted and issue or bug can be used
    instead of ticket.

    You can have more than one command in a message. The following commands
    are supported. There is more than one spelling for each command, to make
    this as user-friendly as possible.

      close, closed, closes, fix, fixed, fixes::
        The specified tickets are closed, and the commit message is added to
        them as a comment.

      references, refs, addresses, re, see::
        The specified tickets are left in their current status, and the commit
        message is added to them as a comment.

      reopen, reopens, reopened::
        The specified tickets are reopened, and the commit message is added to
        them as a comment.

      implement, implements, implemented, impl::
        The specified tickets are set to implemented and the commit message is
        added to them as a comment.

      reject, rejects, rejected::
        The specified tickets are set to rejected and the commit message is
        added to them as a comment.

      invalid, invalidate, invalidated, invalidates::
        The specified tickets are closed with reason set to invalid and the
        commit message is added to added to them as a comment.

      worksforme::
        The specified tickets are closed with reason set to worksforme and the
        commit message is added to added to them as a comment.

    A fairly complicated example of what you can do is with a commit message
    of:

        Changed blah and foo to do this or that. Fixes #10 and #12,
        and refs #12.

    This will close #10 and #12, and add a note to #12.
    """

    implements(IRepositoryChangeListener)

    envelope = Option('ticket', 'commit_ticket_update_envelope', '',
        """Require commands to be enclosed in an envelope.

        Must be empty or contain two characters. For example, if set to `[]`,
        then commands must be in the form of `[closes #4]`.""")

    allowed_domains = Option('ticket', 'commit_ticket_update_allowed_domains',
        '',
        """List of allowed domains in the authors mail address, as a space-separated list.""")

    commands_close = Option('ticket', 'commit_ticket_update_commands.close',
        'close closed closes fix fixed fixes',
        """Commands that close tickets, as a space-separated list.""")

    commands_refs = Option('ticket', 'commit_ticket_update_commands.refs',
        'addresses re references refs see',
        """Commands that add a reference, as a space-separated list.

        If set to the special value `<ALL>`, all tickets referenced by the
        message will get a reference to the changeset.""")

    commands_reopens = Option('ticket', 'commit_ticket_update_commands.reopen',
        'reopen reopens reopened',
        """Commands that close tickets, as a space-separated list.""")

    commands_implements = Option('ticket', 'commit_ticket_update_commands.implements',
        'implement implements implemented impl',
        """Commands that implements a tickets, as a space-separated list.""")

    commands_rejects = Option('ticket', 'commit_ticket_update_commands.rejects',
        'reject rejects rejected',
        """Commands that rejects a tickets, as a space-separated list.""")

    commands_invalidate = Option('ticket', 'commit_ticket_update_commands.invalidate',
        'invalid invalidate invalidated invalidates',
        """Commands that close tickets with status invalid, as a space-separated list.""")

    commands_worksforme = Option('ticket', 'commit_ticket_update_commands.worksforme',
        'worksforme',
        """Commands that close tickets with status worksforme, as a space-separated list.""")

    commands_alreadyimplemented = Option('ticket', 'commit_ticket_update_commands.alreadyimplemented',
        'alreadyimplemented already_implemented',
        """Commands that close tickets with status already_implemented, as a space-separated list.""")

    commands_testready = Option('ticket', 'commit_ticket_update_commands.testready',
        'testready test_ready ready_for_test rft',
        """Commands that change tickets to test_ready status, as a space-separated list.""")

    check_perms = BoolOption('ticket', 'commit_ticket_update_check_perms',
        'true',
        """Check that the committer has permission to perform the requested
        operations on the referenced tickets.

        This requires that the user names be the same for Trac and repository
        operations.""")

    notify = BoolOption('ticket', 'commit_ticket_update_notify', 'true',
        """Send ticket change notification when updating a ticket.""")

    ticket_prefix = '(?:#|(?:ticket|issue|bug)[: ]?)'
    ticket_reference = ticket_prefix + \
                       '[0-9]+(?:#comment:([0-9]+|description))?'
    ticket_command = (r'(?P<action>[A-Za-z\_]*)\s*.?\s*'
                      r'(?P<ticket>%s(?:(?:[, &]*|[ ]?and[ ]?)%s)*)' %
                      (ticket_reference, ticket_reference))

    @property
    def command_re(self):
        (begin, end) = (re.escape(self.envelope[0:1]),
                        re.escape(self.envelope[1:2]))
        return re.compile(begin + self.ticket_command + end)

    ticket_re = re.compile(ticket_prefix + '([0-9]+)')

    _last_cset_id = None


    def changeset_added_impl(self, repos, changeset):
        tickets = self._parse_message(changeset.message)
        comment = self.make_ticket_comment(repos, changeset)
        return self._update_tickets(tickets, changeset, comment,
                             datetime_now(utc))


    # IRepositoryChangeListener methods

    def changeset_added(self, repos, changeset):
        self.log.debug("changeset_added on %s for changesets %s", repos.name, changeset.rev)
        if self._is_duplicate(changeset):
            return
        self.changeset_added_impl(repos, changeset)

    def changeset_modified(self, repos, changeset, old_changeset):
        self.log.debug("changeset_modified on %s for changesets %s", repos.name, changeset.rev)
        if self._is_duplicate(changeset):
            return
        tickets = self._parse_message(changeset.message)
        old_tickets = {}
        if old_changeset is not None:
            old_tickets = self._parse_message(old_changeset.message)
        tickets = dict(each for each in tickets.iteritems()
                       if each[0] not in old_tickets)
        comment = self.make_ticket_comment(repos, changeset)
        self._update_tickets(tickets, changeset, comment,
                             datetime_now(utc))

    @staticmethod
    def _get_changeset_author(changeset_author):
        author_name = None
        author_email = None
        author_email_domain = None
        at_idx = changeset_author.find('@')
        if at_idx > 0:
            start_idx = changeset_author.rfind('<', 0, at_idx)
            if start_idx < 0:
                start_idx = 0
            else:
                author_name = changeset_author[0:start_idx].strip()
                start_idx = start_idx + 1
            end_idx = changeset_author.find('>', at_idx)
            if end_idx < 0:
                end_idx = len(changeset_author)
            author_email = changeset_author[start_idx:end_idx]
            author_email_domain = changeset_author[at_idx+1:end_idx].lower()

        return author_name, author_email, author_email_domain

    def _is_author_allowed(self, changeset_author):
        #self.log.info('_is_author_allowed got %s, cfg %s' % (changeset_author, self.allowed_domains))
        if not self.allowed_domains:
            ret = True
        else:
            # Default to deny author when we are unable to get a valid email from the
            # changeset author
            ret = False
            author_name, author_email, author_email_domain = CommitTicketUpdater._get_changeset_author(changeset_author)
            if author_email_domain is not None:
                allowed_domains_list = self.allowed_domains.split(' ')
                ret = True if author_email_domain in allowed_domains_list else False
        return ret

    def _get_username_for_email(self, changeset_email):
        changeset_email_lower = changeset_email.lower()
        for username, name, email in self.env.get_known_users():
            #print('%s, %s, %s <> %s' % (username, name, email, changeset_email_lower))
            if (email is not None and email.lower() == changeset_email_lower) or (username is not None and username.lower() == changeset_email_lower):
                return username
        return None

    def _get_username_for_changeset_author(self, changeset_author):
        author_name, author_email, author_email_domain = CommitTicketUpdater._get_changeset_author(changeset_author)
        #print(author_name, author_email, author_email_domain )
        if author_email is not None:
            return self._get_username_for_email(author_email)
        else:
            return self._get_username_for_email(changeset_author)

    def _is_duplicate(self, changeset):
        # Avoid duplicate changes with multiple scoped repositories
        cset_id = (changeset.rev, changeset.message, changeset.author,
                   changeset.date)
        if cset_id != self._last_cset_id:
            self._last_cset_id = cset_id
            return False
        return True

    def _parse_message(self, message):
        """Parse the commit message and return the ticket references."""
        cmd_groups = self.command_re.finditer(message)
        functions = self._get_functions()
        tickets = {}
        for m in cmd_groups:
            cmd, tkts = m.group('action', 'ticket')
            func = functions.get(cmd.lower())
            if not func and self.commands_refs.strip() == '<ALL>':
                func = self.cmd_refs
            if func:
                for tkt_id in self.ticket_re.findall(tkts):
                    tickets.setdefault(int(tkt_id), []).append(func)
        return tickets

    def make_ticket_comment(self, repos, changeset):
        """Create the ticket comment from the changeset data."""
        rev = changeset.rev
        revstring = str(rev)
        drev = str(repos.display_rev(rev))
        if repos.reponame:
            revstring += '/' + repos.reponame
            drev += '/' + repos.reponame
        return textwrap.dedent("""\
In [changeset:"%s" %s]:
{{{
#!CommitTicketReference repository="%s" revision="%s"
%s
}}}""") % (revstring, drev, repos.reponame, rev,
                       changeset.message.strip())

    def _update_tickets(self, tickets, changeset, comment, date):
        """Update the tickets with the given comment."""

        authname = self._get_username_for_changeset_author(changeset.author)
        if not authname:
            authname = self._authname(changeset)
        perm = PermissionCache(self.env, authname)
        ret = {}
        for tkt_id, cmds in tickets.iteritems():
            self.log.debug("Updating ticket #%d", tkt_id)
            save = False
            with self.env.db_transaction:
                try:
                    ticket = Ticket(self.env, tkt_id)
                except ResourceNotFound:
                    self.log.warning("Ticket %i does not exist", tkt_id)
                    ticket = None
                if ticket is not None:
                    ticket_perm = perm(ticket.resource)
                    if self.check_perms and not 'TICKET_MODIFY' in ticket_perm:
                        #sys.stderr.write("%s doesn't have TICKET_MODIFY permission for #%d\n" % (authname, ticket.id))
                        self.log.info("%s doesn't have TICKET_MODIFY permission for #%d",
                                    authname, ticket.id)
                    else:
                        if self._is_author_allowed(changeset.author):
                            for cmd in cmds:
                                if cmd(ticket, changeset, ticket_perm):
                                    save = True
                        else:
                            #sys.stderr.write("%s is not allowed to modify to #%d\n" % (changeset.author, ticket.id))
                            self.log.info("%s is not allowed to modify to #%d",
                                        changeset.author, ticket.id)
                    if save:
                        ticket.save_changes(authname, comment, date)
            if save:
                self._notify(ticket, date)
            ret[tkt_id] = (cmds, ticket)
        return ret

    def _notify(self, ticket, date, author, comment):
        """Send a ticket update notification."""
        if not self.notify:
            return
        event = TicketChangeEvent('changed', ticket, date, author, comment)
        try:
            NotificationSystem(self.env).notify(event)
        except Exception as e:
            self.log.error("Failure sending notification on change to "
                           "ticket #%s: %s", ticket.id,
                           exception_to_unicode(e))

    def _get_functions(self):
        """Create a mapping from commands to command functions."""
        functions = {}
        for each in dir(self):
            if not each.startswith('cmd_'):
                continue
            func = getattr(self, each)
            for cmd in getattr(self, 'commands_' + each[4:], '').split():
                functions[cmd] = func
        return functions

    def _authname(self, changeset):
        """Returns the author of the changeset, normalizing the casing if
        [trac] ignore_author_case is true."""
        return changeset.author.lower() \
               if self.env.config.getbool('trac', 'ignore_auth_case') \
               else changeset.author

    # Command-specific behavior
    # The ticket isn't updated if all extracted commands return False.

    def cmd_close(self, ticket, changeset, perm):
        if ticket['status'] != 'closed':
            ticket['status'] = 'closed'
            ticket['resolution'] = 'fixed'
            author_username = self._get_username_for_changeset_author(changeset.author)
            if author_username:
                ticket['owner'] = author_username
        return True

    def cmd_invalidate(self, ticket, changeset, perm):
        if ticket['status'] != 'closed':
            ticket['status'] = 'closed'
            ticket['resolution'] = 'invalid'
            if not ticket['owner']:
                author_username = self._get_username_for_changeset_author(changeset.author)
                if author_username:
                    ticket['owner'] = author_username
        return True

    def cmd_worksforme(self, ticket, changeset, perm):
        if ticket['status'] != 'closed':
            ticket['status'] = 'closed'
            ticket['resolution'] = 'worksforme'
            if not ticket['owner']:
                author_username = self._get_username_for_changeset_author(changeset.author)
                if author_username:
                    ticket['owner'] = author_username
        return True

    def cmd_alreadyimplemented(self, ticket, changeset, perm):
        if ticket['status'] != 'closed':
            ticket['status'] = 'closed'
            ticket['resolution'] = 'already_implemented'
            if not ticket['owner']:
                author_username = self._get_username_for_changeset_author(changeset.author)
                if author_username:
                    ticket['owner'] = author_username
        return True

    def cmd_reopens(self, ticket, changeset, perm):
        if ticket['status'] == 'closed':
            ticket['status'] = 'reopened'
            ticket['resolution'] = ''
            author_username = self._get_username_for_changeset_author(changeset.author)
            if author_username:
                ticket['owner'] = author_username
        return True

    def cmd_refs(self, ticket, changeset, perm):
        return True

    def cmd_implements(self, ticket, changeset, perm):
        if ticket['status'] != 'implemented' and ticket['status'] != 'closed':
            ticket['status'] = 'implemented'
            author_username = self._get_username_for_changeset_author(changeset.author)
            if author_username:
                ticket['owner'] = author_username
        return True

    def cmd_rejects(self, ticket, changeset, perm):
        if ticket['status'] != 'rejected' and ticket['status'] != 'closed':
            ticket['status'] = 'rejected'
            if ticket['reporter']:
                ticket['owner'] = ticket['reporter']
            if not ticket['owner']:
                author_username = self._get_username_for_changeset_author(changeset.author)
                if author_username:
                    ticket['owner'] = author_username
        return True

    def cmd_testready(self, ticket, changeset, perm):
        if ticket['status'] != 'closed':
            ticket['status'] = 'test_ready'
            ticket['resolution'] = ''
            if ticket['reporter']:
                ticket['owner'] = ticket['reporter']
            if not ticket['owner']:
                author_username = self._get_username_for_changeset_author(changeset.author)
                if author_username:
                    ticket['owner'] = author_username
        return True

class CommitTicketReferenceMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Insert a changeset message into the output.

    This macro must be called using wiki processor syntax as follows:
    {{{
    {{{
    #!CommitTicketReference repository="reponame" revision="rev"
    }}}
    }}}
    where the arguments are the following:
     - `repository`: the repository containing the changeset
     - `revision`: the revision of the desired changeset
    """)

    def expand_macro(self, formatter, name, content, args=None):
        args = args or {}
        reponame = args.get('repository') or ''
        rev = args.get('revision')
        repos = RepositoryManager(self.env).get_repository(reponame)
        try:
            changeset = repos.get_changeset(rev)
            message = changeset.message
            rev = changeset.rev
            resource = repos.resource
        except Exception:
            message = content
            resource = Resource('repository', reponame)
        if formatter.context.resource.realm == 'ticket':
            ticket_re = CommitTicketUpdater.ticket_re
            if not any(int(tkt_id) == int(formatter.context.resource.id)
                       for tkt_id in ticket_re.findall(message)):
                return tag.p(_("(The changeset message doesn't reference "
                               "this ticket)"), class_='hint')
        if ChangesetModule(self.env).wiki_format_messages:
            return tag.div(format_to_html(self.env,
                formatter.context.child('changeset', rev, parent=resource),
                message, escape_newlines=True), class_='message')
        else:
            return tag.pre(message, class_='message')

if __name__ == '__main__':
    for a in ["test_person <me@gohome.now>",
                         "test_person <me@mydomain>",
                         "test_person",
                         "test_person@gohome.now"
                         ]:
        print(CommitTicketUpdater._get_changeset_author(a))
