from django.conf import settings
from django.core import mail
from django.test import TestCase

from mock import patch

from myjobs.tests.factories import UserFactory
from mysearches.tests.factories import (SavedSearchFactory,
                                        SavedSearchDigestFactory)
from mysearches.tests.test_helpers import return_file
from tasks import send_search_digests


class SavedSearchModelsTests(TestCase):
    def setUp(self):
        self.user = UserFactory()

        self.patcher = patch('urllib2.urlopen', return_file)
        self.mock_urlopen = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_send_search_email(self):
        SavedSearchDigestFactory(user=self.user,
                                 is_active=False)
        search = SavedSearchFactory(user=self.user, is_active=True,
                                    frequency='D',
                                    url='www.my.jobs/search?q=new+search')
        send_search_digests()
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox.pop()
        self.assertEqual(email.from_email, settings.SAVED_SEARCH_EMAIL)
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, search.label)
        self.assertTrue("table" in email.body)
        self.assertTrue(email.to[0] in email.body)
        self.assertNotEqual(email.body.find(search.url), -1,
                            "Search url was not found in email body")

    def test_send_search_digest_email(self):
        SavedSearchDigestFactory(user=self.user)
        send_search_digests()
        self.assertEqual(len(mail.outbox), 0)

        SavedSearchFactory(user=self.user)
        send_search_digests()
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox.pop()
        self.assertEqual(email.from_email, settings.SAVED_SEARCH_EMAIL)
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual(email.subject, "Your Daily Saved Search Digest")
        self.assertTrue("table" in email.body)
        self.assertTrue(email.to[0] in email.body)

    def test_send_search_digest_send_if_none(self):
        SavedSearchDigestFactory(user=self.user, send_if_none=True)
        send_search_digests()
        self.assertEqual(len(mail.outbox), 0)

        SavedSearchFactory(user=self.user)
        send_search_digests()
        self.assertEqual(len(mail.outbox), 1)
    
    def test_send_initial_email(self):
        search = SavedSearchFactory(user=self.user, is_active=False,
                                    url='www.my.jobs/search?q=new+search')
        search.send_initial_email()
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox.pop()
        self.assertEqual(email.from_email, settings.SAVED_SEARCH_EMAIL)
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual("My.jobs New Saved Search" in email.subject, True)
        self.assertTrue("table" in email.body)
        self.assertTrue(email.to[0] in email.body)
    
    def test_send_update_email(self):
        search = SavedSearchFactory(user=self.user, is_active=False,
                                    url='www.my.jobs/search?q=new+search')
        search.send_update_email('Your search is updated')
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox.pop()
        self.assertEqual(email.from_email, settings.SAVED_SEARCH_EMAIL)
        self.assertEqual(email.to, [self.user.email])
        self.assertEqual("My.jobs Saved Search Updated" in email.subject, True)
        self.assertTrue("table" in email.body)
        self.assertTrue("Your search is updated" in email.body)
        self.assertTrue(email.to[0] in email.body)