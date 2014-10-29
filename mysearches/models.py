from datetime import datetime
from pynliner import Pynliner
from urlparse import urlparse

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.utils.translation import ugettext_lazy as _
from django.template.loader import render_to_string

from myjobs.models import User
from mypartners.models import Contact, ContactRecord, Partner, EMAIL
from mysearches.helpers import (parse_feed, update_url_if_protected,
                                url_sort_options, validate_dotjobs_url)
import mypartners.helpers


FREQUENCY_CHOICES = (
    ('D', _('Daily')),
    ('W', _('Weekly')),
    ('M', _('Monthly')))

DOM_CHOICES = [(i, i) for i in range(1, 31)]
DOW_CHOICES = (('1', _('Monday')),
               ('2', _('Tuesday')),
               ('3', _('Wednesday')),
               ('4', _('Thursday')),
               ('5', _('Friday')),
               ('6', _('Saturday')),
               ('7', _('Sunday')))


class SavedSearch(models.Model):

    SORT_CHOICES = (('Relevance', _('Relevance')),
                    ('Date', _('Date')))

    user = models.ForeignKey('myjobs.User', editable=False)
    
    created_on = models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=60, verbose_name=_("Search Name"))
    url = models.URLField(max_length=300,
                          verbose_name=_("URL of Search Results"))
    sort_by = models.CharField(max_length=9, choices=SORT_CHOICES,
                               default='Relevance', verbose_name=_("Sort by"))
    feed = models.URLField(max_length=300)
    is_active = models.BooleanField(default=True,
                                    verbose_name=_("Search is Active"))
    email = models.EmailField(max_length=255,
                              verbose_name=_("Which Email Address"))
    frequency = models.CharField(max_length=2, choices=FREQUENCY_CHOICES,
                                 default='W',
                                 verbose_name=_("Frequency"))
    day_of_month = models.IntegerField(choices=DOM_CHOICES,
                                       blank=True, null=True,
                                       verbose_name=_("on"))
    day_of_week = models.CharField(max_length=2, choices=DOW_CHOICES,
                                   blank=True, null=True,
                                   verbose_name=_("on"))
    jobs_per_email = models.PositiveSmallIntegerField(default=5,
                                         verbose_name=_("Jobs per Email"))
    notes = models.TextField(blank=True, null=True,
                             verbose_name=_("Comments"))
    last_sent = models.DateTimeField(blank=True, null=True, editable=False)

    # Custom messages were created for PartnerSavedSearches
    custom_message = models.TextField(max_length=300, blank=True, null=True)

    def get_company(self):
        """
        Attempts to match the feed url to an SeoSite and then determine the
        owner of that SeoSite.

        """
        from seo.models import SeoSite
        netloc = urlparse(self.feed).netloc
        try:
            site = SeoSite.objects.get(domain__iexact=netloc)
            return site.get_companies()[0].pk
        except (SeoSite.DoesNotExist, SeoSite.MultipleObjectsReturned,
                IndexError):
            # No match was found, so make the company DirectEmployers.
            return 999999

    def get_verbose_frequency(self):
        for choice in FREQUENCY_CHOICES:
            if choice[0] == self.frequency:
                return choice[1]

    def get_verbose_dow(self):
        for choice in DOW_CHOICES:
            if choice[0] == self.day_of_week:
                return choice[1]

    def get_feed_items(self, num_items=None):
        num_items = num_items or self.jobs_per_email
        url_of_feed = url_sort_options(self.feed, self.sort_by, self.frequency)
        url_of_feed = update_url_if_protected(url_of_feed, self.user)
        parse_feed_args = {
            'feed_url': url_of_feed, 'frequency': self.frequency,
            'return_items': num_items,
            'last_sent': self.last_sent
        }
        if hasattr(self, 'partnersavedsearch'):
            parse_feed_args['ignore_dates'] = True
        items = parse_feed(**parse_feed_args)
        return items

    def send_email(self, custom_msg=None):
        items, count = self.get_feed_items()
        if self.user.can_receive_myjobs_email() and items:
            is_pss = hasattr(self, 'partnersavedsearch')
            if is_pss:
                extras = self.partnersavedsearch.url_extras
                if extras:
                    mypartners.helpers.add_extra_params_to_jobs(items, extras)
                    self.url = mypartners.helpers.add_extra_params(self.url,
                                                                   extras)
            if self.custom_message and not custom_msg:
                custom_msg = self.custom_message

            context_dict = {'saved_searches': [(self, items, count)],
                            'custom_msg': custom_msg,
                            'contains_pss': is_pss}
            subject = self.label.strip()
            message = render_to_string('mysearches/email_single.html',
                                       context_dict)
            msg = EmailMessage(subject, message, settings.SAVED_SEARCH_EMAIL,
                               [self.email])
            msg.content_subtype = 'html'
            msg.send()
            self.last_sent = datetime.now()
            self.save()

            if is_pss:
                self.partnersavedsearch.create_record(custom_msg)

    def send_initial_email(self, custom_msg=None):
        if self.user.opt_in_myjobs:
            context_dict = {'saved_searches': [(self,)],
                            'custom_msg': custom_msg,
                            'contains_pss': hasattr(self, 'partnersavedsearch')}
            subject = "My.jobs New Saved Search - %s" % self.label.strip()
            message = render_to_string("mysearches/email_initial.html",
                                       context_dict)
            message = Pynliner().from_string(message).run()

            msg = EmailMessage(subject, message, settings.SAVED_SEARCH_EMAIL,
                               [self.email])
            msg.content_subtype = 'html'
            msg.send()
    
    def send_update_email(self, msg, custom_msg=None):
        """
        This function is meant to be called from the shell. It sends a notice to
        the user that their saved search has been updated by the system or an 
        admin.
        
        Inputs:
        :msg:   The description of the update. Passed through verbatim to the
                template.
                
        Returns:
        nothing
        
        """
        context_dict = {
            'saved_searches': [(self,)],
            'message': msg,
            'custom_msg': custom_msg,
            'contains_pss': hasattr(self, 'partnersavedsearch')
        }
        subject = "My.jobs Saved Search Updated - %s" % self.label.strip()
        message = render_to_string("mysearches/email_update.html",
                                   context_dict)

        msg = EmailMessage(subject, message, settings.SAVED_SEARCH_EMAIL,
                           [self.email])
        msg.content_subtype = 'html'
        msg.send()
        
    def create(self, *args, **kwargs):
        """
        On creation, check if that same URL exists for the user and raise
        validation if it's a duplicate.
        """

        duplicates = SavedSearch.objects.filter(user=self.user, url=self.url)

        if duplicates:
            raise ValidationError('Saved Search URLS must be unique.')
        super(SavedSearch, self).create(*args, **kwargs)

    def save(self, *args, **kwargs):
        """"
        Create a new saved search digest if one doesn't exist yet
        """

        if not SavedSearchDigest.objects.filter(user=self.user):
            SavedSearchDigest.objects.create(user=self.user, email=self.email)

        super(SavedSearch, self).save(*args, **kwargs)

    def __unicode__(self):
        return "Saved Search %s for %s" % (self.url, self.user.email)

    class Meta:
        verbose_name_plural = "saved searches"

    def disable_or_fix(self):
        """
        Disables or fixes this saved search based on the presence or lack of an
        rss feed on the search url. Sends a "search has been disabled" email
        if this is not fixable.
        """
        try:
            _, feed = validate_dotjobs_url(self.url, self.user)
        except ValueError:
            feed = None

        if feed is None:
            # search url did not contain an rss link and is not valid
            self.is_active = False
            self.save()
            self.send_disable_email()
        elif self.feed == '':
            # search url passed validation in the past even though there was
            # an issue retrieving the page; update the feed url
            self.feed = feed
            self.save()

    def send_disable_email(self):
        subject = 'Invalid search url in your My.jobs saved search'
        message = render_to_string('mysearches/email_disable.html',
                                   {'saved_search': self})

        msg = EmailMessage(subject, message, settings.SAVED_SEARCH_EMAIL,
                           [self.email])
        msg.content_subtype = 'html'
        msg.send()


class SavedSearchDigest(models.Model):
    is_active = models.BooleanField(default=False)
    user = models.OneToOneField('myjobs.User', editable=False)
    email = models.EmailField(max_length=255)
    frequency = models.CharField(max_length=2, choices=FREQUENCY_CHOICES,
                                 default='D',
                                 verbose_name=_("How often:"))
    day_of_month = models.IntegerField(choices=DOM_CHOICES,
                                       blank=True, null=True,
                                       verbose_name=_("on"))
    day_of_week = models.CharField(max_length=2, choices=DOW_CHOICES,
                                   blank=True, null=True,
                                   verbose_name=_("on"))

    # For now, emails will only be sent if they have searches; When this
    # functionality is added, remove `editable=False` to show this option on
    # the form
    send_if_none = models.BooleanField(default=False,
                                       verbose_name=_("Send even if there are"
                                                      " no results"),
                                       editable=False)

    def send_email(self, custom_msg=None):
        saved_searches = self.user.savedsearch_set.filter(is_active=True)
        search_list = []
        contains_pss = False
        for search in saved_searches:
            items, count = search.get_feed_items()
            pss = None
            if hasattr(search, 'partnersavedsearch'):
                pss = search.partnersavedsearch
            elif isinstance(search, PartnerSavedSearch):
                pss = search

            if pss is not None:
                contains_pss = True
                extras = pss.url_extras
                if extras:
                    mypartners.helpers.add_extra_params_to_jobs(items, extras)
                    search.url = mypartners.helpers.add_extra_params(search.url,
                                                                     extras)
                pss.create_record(custom_msg)
            search_list.append((search, items, count))
        saved_searches = [(search, items, count)
                          for search, items, count in search_list
                          if items]
        if self.user.can_receive_myjobs_email() and saved_searches:
            subject = _('Your Daily Saved Search Digest')
            context_dict = {
                'saved_searches': saved_searches,
                'digest': self,
                'custom_msg': custom_msg,
                'contains_pss': contains_pss
            }
            message = render_to_string('mysearches/email_digest.html',
                                       context_dict)
            msg = EmailMessage(subject, message, settings.SAVED_SEARCH_EMAIL,
                               [self.email])
            msg.content_subtype = 'html'
            msg.send()

    def disable_or_fix(self):
        """
        Calls SavedSearch.disable_or_fix for each saved search associated
        with the owner of this digest.
        """
        for search in self.user.savedsearch_set.filter(is_active=True):
            search.disable_or_fix()


class PartnerSavedSearch(SavedSearch):
    """
    Partner Saved Search (PSS) is a subclass of SavedSearch. PSSs' emails are
    sent out as if it is a SavedSearch. When a PSS is created a SavedSearch
    is also created and is attached to the User. Then the PSS is connected via
    a OneToOne relationship to the SavedSearch. Only way to access a PSS from a
    User is SavedSearch.partnersavedsearch.

    """
    provider = models.ForeignKey('seo.Company')
    partner = models.ForeignKey(Partner)
    url_extras = models.CharField(max_length=255, blank=True,
                                  help_text="Anything you put here will be "
                                            "added as query string parameters "
                                            "to each of links in the saved "
                                            "search.")
    partner_message = models.TextField(
        blank=True, help_text="Use this field to provide a customized "
                              "greeting that will be sent with each copy "
                              "of this saved search.")
    tags = models.ManyToManyField('mypartners.Tag', null=True)
    account_activation_message = models.TextField(blank=True)
    created_by = models.ForeignKey(User, editable=False)

    def __unicode__(self):
        if not hasattr(self, 'user'):
            return "Saved Search %s for %s" % (self.url, self.email)
        else:
            return "Saved Search %s for %s" % (self.url, self.user.email)

    def save(self, *args, **kwargs):
        created = False if self.pk else True
        super(PartnerSavedSearch, self).save(*args, **kwargs)
        if created:
            self.send_initial_email()

    def send_initial_email(self, custom_msg=None):
        super(PartnerSavedSearch, self).send_initial_email(custom_msg)
        change_msg = "Automatic sending of initial partner saved search."
        self.create_record(change_msg)

    def send_update_email(self, msg, custom_msg=None):
        super(PartnerSavedSearch, self).send_update_email(msg, custom_msg)
        change_msg = "Automatic sending of updated partner saved search."
        self.create_record(change_msg)

    def create_record(self, change_msg=None):
        items, count = self.get_feed_items()
        if change_msg is None:
            change_msg = "Automatic sending of partner saved search."

        extras = self.partnersavedsearch.url_extras
        if extras:
            mypartners.helpers.add_extra_params_to_jobs(items, extras)
            self.url = mypartners.helpers.add_extra_params(self.url, extras)

        custom_msg = self.custom_message if self.custom_message else ''
        context_dict = {
            'saved_searches': [(self, items, count)],
            'custom_msg': custom_msg,
            'contains_pss': True
        }
        subject = self.label.strip()
        message = render_to_string('mysearches/email_single.html',
                                   context_dict)

        contact = Contact.objects.filter(partner=self.partner,
                                         user=self.user)[0]
        record = ContactRecord.objects.create(
            partner=self.partner,
            contact_type='pssemail',
            contact_name=contact.name,
            contact_email=self.user.email,
            created_by=self.created_by,
            date_time=datetime.now(),
            subject=subject,
            notes=message,
        )
        mypartners.helpers.log_change(record, None, None, self.partner,
                                      self.user.email, action_type=EMAIL,
                                      change_msg=change_msg)
