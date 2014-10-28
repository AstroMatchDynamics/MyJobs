from collections import namedtuple
from datetime import datetime, time, timedelta
from urlparse import urlparse, parse_qsl, urlunparse
from urllib import urlencode

from django.db.models import Min, Max, Q
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMessage
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.text import get_text_list, force_unicode, force_text
from django.utils.timezone import get_current_timezone_name, now
from django.utils.translation import ugettext
from lxml import html
from lxml.cssselect import CSSSelector
import pytz
import requests
import states
from universal.helpers import (get_domain, get_company, get_company_or_404,
                               get_int_or_none)
from mypartners.models import (Contact, ContactLogEntry, CONTACT_TYPE_CHOICES, 
                               CHANGE, Location, Partner, PartnerLibrary, Tag)
from registration.models import ActivationProfile


def prm_worthy(request):
    """
    Makes sure the User is worthy enough to use PRM.

    """
    company = get_company(request)
    if company is None:
        raise Http404

    partner_id = get_int_or_none(request.REQUEST.get('partner'))
    partner = get_object_or_404(company.partner_set, id=partner_id)

    return company, partner, request.user


def add_extra_params(url, extra_urls):
    """
    Adds extra parameters to a url

    Inputs:
    :url: Url that parameters will be added to
    :extra_urls: Extra parameters to be added

    Outputs:
    :url: Input url with parameters added
    """
    extra_urls = extra_urls.lstrip('?&')
    new_queries = dict(parse_qsl(extra_urls, keep_blank_values=True))

    # By default, extra parameters besides vs are discarded by the redirect
    # server. We can get around this by adding &z=1 to the url, which enables
    # custom query parameter overrides.
    new_queries['z'] = '1'

    parts = list(urlparse(url))
    query = dict(parse_qsl(parts[4], keep_blank_values=True))
    query.update(new_queries)
    parts[4] = urlencode(query)
    return urlunparse(parts)


def add_extra_params_to_jobs(items, extra_urls):
    """
    Adds extra parameters to all jobs in a list

    Inputs:
    :items: List of jobs to which extra parameters should be added
    :extra_urls: Extra parameters to be added

    Modifies:
    :items: List is mutable and is modified in-place
    """
    for item in items:
        item['link'] = add_extra_params(item['link'], extra_urls)


def log_change(obj, form, user, partner, contact_identifier,
               action_type=CHANGE, change_msg=None):
    """
    Creates a ContactLogEntry for obj.

    inputs:
    :obj: The object a log entry is being created for
    :form: The form the log entry is being created from. This is optional,
        but without it a valuable change message can't be created, so either
        one will need to be passed to the function or there won't be a change
        message for this log entry.
    :user: The user who caused the change. Can be null, but shouldn't be unless
        in most cases.
    :partner: The partner this object applies to. Should never be null.
    :contact_identifier: Some meaningful piece of information (e.g. name,
        email, phone number) that identifies the person being contacted.
    :action_type: The action being taken. Available types are in
        mypartners.models.
    :change_msg: A short description of the changes made. If one isn't provided,
        the change_msg will attempt to be created from the form.

    """
    if not change_msg:
        change_msg = get_change_message(form) if action_type == CHANGE else ''

    ContactLogEntry.objects.create(
        action_flag=action_type,
        change_message=change_msg,
        contact_identifier=contact_identifier,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        object_repr=force_text(obj)[:200],
        partner=partner,
        user=user,
    )


def get_change_message(form):
    """
    Creates a list of changes made from a form.

    """
    change_message = []
    if not form:
        return ''
    if form.changed_data:
        change_message = (ugettext('Changed %s.') %
                          get_text_list(form.changed_data, ugettext('and')))
    return change_message or ugettext('No fields changed.')


def get_attachment_link(partner_id, attachment_id, attachment_name):
    """
    Creates a link (html included) to a PRMAttachment.

    """
    url = '/prm/download?partner=%s&id=%s' % (partner_id, attachment_id)

    html = "<a href='{url}' target='_blank'>{attachment_name}</a>"
    return mark_safe(html.format(url=url, attachment_name=attachment_name))


def retrieve_fields(model):
    fields = [field for field in model._meta.get_all_field_names()
              if unicode(field) not in [u'id', u'prmattachment']]
    return fields


def contact_record_val_to_str(value):
    """
    Translates a field value from a contact record into a human-readable string.
    Dates are formatted "ShortMonth Day, Year Hour:Minute AMorPM"
    Times are formatted "XX Hours XX Minutes"
    If the value matches a contact type choice it's translated to the
    verbose form.
    """
    value = (value.strftime('%b %d, %Y %I:%M %p') if type(value)
             is datetime else value.strftime('%H hours %M minutes')
             if type(value) is time else force_unicode(value))


    contact_types = dict(CONTACT_TYPE_CHOICES)
    if value in contact_types:
        value = contact_types[value]

    return value


def get_records_from_request(request):
    """
    Filters a list of records on partner, date_time, contact_name, and
    contact_type based on the request

    outputs:
    The date range filtered on, A string "X Day(s)" representing the
    date filtered on, and the filtered records.
    """
    _, partner, _ = prm_worthy(request)

    # extract reelvant values from the request object
    contact, contact_type, admin, range_start, range_end = [
        value if value not in ["all", "undefined", ""] else None for value in [
            request.REQUEST.get(field) for field in [
                "contact", "contact_type", "admin",
                "date_start", "date_end"]]]

    records = partner.get_contact_records(contact_name=contact,
        record_type=contact_type, created_by=admin)

    if not range_start and not range_end:
        date_str = "View All"
        range_start = records.aggregate(Min('date_time')).get(
            'date_time__min', now())
        range_end = records.aggregate(Max('date_time')).get(
            'date_time__max', now())
    else:
        if range_start:
            range_start = datetime.strptime(range_start, '%m/%d/%Y').date()
        else:
            range_start = records.aggregate(Min('date_time')).get(
                'date_time__min', now()).date()

        if range_end:
            range_end = datetime.strptime(range_end, '%m/%d/%Y').date()
        else:
            range_end = now().date()

        days = (range_end - range_start).days
        date_str = '%i Day%s' % (days, '' if days == 1 else 's')

    records = records.filter(date_time__range=[range_start, range_end])

    return (range_start, range_end), date_str, records


def send_contact_record_email_response(created_records, created_contacts,
                                       attachment_failures, unmatched_contacts,
                                       error, to_email):
    ctx = {
        'created_records': created_records,
        'created_contacts': created_contacts,
        'error': error,
        'unmatched_contacts': unmatched_contacts,
        'attachment_failures': attachment_failures,
    }

    subject = 'Partner Relationship Manager Contact Records'
    message = render_to_string('mypartners/email/email_response.html',
                               ctx)

    msg = EmailMessage(subject, message, settings.PRM_EMAIL, [to_email])
    msg.content_subtype = 'html'
    msg.send()


def find_partner_from_email(partner_list, email):
    """
    Finds a possible partner based on the email domain.

    inputs:
    :partner_list: The partner list to compare the email against.
    :email: The email address the domain is needed for.

    outputs:
    A matching partner if there is one, otherwise None.

    """
    if not email or '@' not in email or not partner_list:
        return None
    email_domain = email.split('@')[-1]

    for partner in partner_list:
        url = get_domain(partner.uri)
        # Pass through get_domain() to strip subdomains
        email_domain = get_domain(email_domain)

        if email_domain and url and email_domain.lower() == url.lower():
            return partner

    return None


def send_custom_activation_email(search):
    activation = ActivationProfile.objects.get(user=search.user)
    employee_name = search.created_by.get_full_name(default="An employee")
    ctx = {
        'activation': activation,
        'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS,
        'search': search,
        'creator': employee_name,
        'company': search.provider
    }
    subject = "Saved search created on your behalf"
    message = render_to_string('mypartners/partner_search_new_user.html',
                               ctx)
    msg = EmailMessage(subject, message, settings.DEFAULT_FROM_EMAIL,
                       [search.user.email])
    msg.content_subtype = 'html'
    msg.send()


def get_library_as_html():
    """ Get partner library data in HTML format.

        The POST request is necessary in order to get the cookie required by
        the GET request in order to obtain useful results.
    """
    cookie_url = 'http://www.dol-esa.gov/errd/directory.jsp'
    excel_url = 'http://www.dol-esa.gov/errd/directoryexcel.jsp'
    response = requests.post(cookie_url, data=dict(
        reg='ALL', # Region
        stat='None', # State
        name='',
        city='',
        sht='None', # Contractor Type
        lst='None', # Resource Organization
        sortorder='asc'))

    return requests.get(excel_url, cookies=response.cookies).text


def get_library_partners(path=None):
    """ Generator that produces partner library info.

        If no path is given, then the data is downloaded from
        "www.dol-esa.gov/errd".

        This generator yields a CompliancePartner namedtuple whose fields
        coincide with the table headers present in `html_file`. In the case of
        `state` there exists two fields:

        state
            The long version of the state. Presumably indicative of the state
            in which the organization operates in.

        st
            This is the two-letter state abbreviation. Unlike `state`, this
            field indicates the state in which the organization's home office
            resides.
    """

    if path:
        text = open(path, "r").read()
    else:
        text = get_library_as_html()

    tree = html.fromstring(text)

    # convert column headers to valid Python identifiers, and rename duplicates
    cols = []
    for header in CSSSelector("p ~ table th")(tree):
        col = header.text.lower()
        if col in cols:
            cols.append(col[:2])
        else:
            cols.append(col.replace(" ", "_"))

    CompliancePartner = namedtuple("CompliancePartner", cols)
    for row in CSSSelector("p ~ table tr")(tree):
        fields = dict((cols[i], (td.text or "").strip()) for i, td in
                      enumerate(CSSSelector("td")(row)))

        for column, value in fields.items():
            if value in [u"\xa0", None]:
                fields[column] = ""
            elif value == "Y":
                fields[column] = True
            elif value == "N":
                fields[column] = False

            if column in ["minority", "female", "disabled", "veteran",
                          "disabled_veteran", "exec_om", "first_om",
                          "professional", "technician", "sales",
                          "admin_support", "craft", "operative", "labor",
                          "service"]:
                fields[column] = bool(value)

        if len(fields) > 1:
            yield CompliancePartner(**fields)


def filter_partners(request, partner_library=False):
    """
    Advanced partner filtering. 

    If True, the partner_library parameter will determine whether or not the
    OFCCP Partner Library should be filtered for results instead of the current
    company's manually created partners.

    The following request parameters may be used to manipulate the results:

        keywords
            A comma-separated string of keywords which are checked against the
            partner name, contact name and URI.
        city
            The city in which the partner is located.
        state
            The state in which the partner is located.

    When partner_library is True, the following parameter is also available:

        special_interest
            An array of special interest groups to which the partner belongs.
            Possible values are 'minority', 'female', 'disabled', 'veteran',
            and 'disabled_veteran'.

    In addition to filtering, the following sort parameters may be passed:

        desc
            Any truthy string passed along here will indicate to this function
            that the result list should be sorted descending.
        sort_by
            Determines which column is used to sort the results. Officially,
            only 'location'-- which sorts by city and state-- and name -- which
            sorts by partner name -- are allowed.
    """
    sort_order = "-" if request.REQUEST.get("desc", False) else ""
    sort_by = sort_order + request.REQUEST.get('sort_by', 'name')
    city = request.REQUEST.get('city', '').strip()
    state = request.REQUEST.get('state', '').strip()
    tags = [tag.strip() for tag in request.REQUEST.get('tag', '').split(',') if tag]
    keywords = [keyword.strip() for keyword in request.REQUEST.get(
        'keywords', '').split(',') if keyword]
    

    if partner_library:
        special_interest = [
            si if si != "disability" else "disabled" 
            for si in request.REQUEST.getlist('special_interest')]


        library_ids = Partner.objects.exclude(
            library__isnull=True).values_list('library', flat=True)
        # hide partners that the user has already added 
        partners = PartnerLibrary.objects.exclude(id__in=library_ids)
        contact_city = 'city'
        contact_state = 'st'

        unspecified = Q()
        interests = Q()
        order_by = ['is_veteran', 'is_female', 'is_minority', 'is_disabled',
                    'is_disabled_veteran'] 

        if "unspecified" in special_interest:
            special_interest.remove("unspecified")
            unspecified = Q(is_veteran=False, is_female=False,
                            is_minority=False, is_disabled=False,
                            is_disabled_veteran=False)

        for interest in special_interest:
            interests &= Q(**{"is_%s" % interest.replace(' ', '_'): True})

        query = Q(interests | unspecified)
    else:
        start_date = request.REQUEST.get('start_date')
        end_date = request.REQUEST.get('end_date')

        partners = Partner.objects.prefetch_related(
            'contact_set', 'contact_set__tags', 'contact_set__locations',
            'tags')
        contact_city = 'contact__locations__city'
        contact_state = 'contact__locations__state'
        sort_by.replace('city', 'contact__locations__city')
        order_by = []

        query = Q(owner=get_company_or_404(request).id)

        # If both start and end date are passed, we should filter, creating
        # reasonable bounds for either one if they are missing. Otherwise, we
        # don't filter by either.
        if any([start_date, end_date]):
            start_date = datetime.strptime(
                start_date or '11/30/1899', '%m/%d/%Y')
            end_date = datetime.strptime(
                end_date or datetime.now().strftime('%m/%d/%Y'), '%m/%d/%Y')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query &= Q(contactrecord__date_time__range=[start_date, end_date])

    for keyword in keywords:
        query &= (Q(name__icontains=keyword) | Q(uri__icontains=keyword) |
                  (Q(contact_name__icontains=keyword) if partner_library else
                   Q(contact__name__icontains=keyword)) |
                  (Q(email__icontains=keyword) if partner_library else
                   Q(contact__email__icontains=keyword)))

    if city:
        query &= Q(**{'%s__icontains' % contact_city: city})

    if state:
        state_query = Q()
        for synonym in states.synonyms[state.strip().lower()]:
            state_query |= Q(**{'%s__iexact' % contact_state: synonym})

        query &= state_query

    partners = partners.distinct().filter(query)

    # filter by tags
    for tag in tags:
        partners = partners.filter(Q(tags__name__icontains=tag) | 
                                   Q(contact__tags__name__icontains=tag))

    if "location" in sort_by:
        if partner_library:
            # no foreign keys, so we can do the "right" thing
            partners = partners.extra(select={
                'no_city': "LENGTH(state) = 0",
                'no_state': "LENGTH(city) = 0"}).order_by(
                    *['%s%s' % (sort_order, column) 
                    for column in ['state', 'city', 'no_state', 'no_city']])
        else:
            # QuerySet.extra(select={}) doesn't traverse foreign keys, so we
            # use a few list transformations in order to sort by location and
            # put empty locations at the end.

            # shortcut to get locations from a partner
            locations = lambda p: p.get_contact_locations()
            # string reprensentation of the first location
            first_location = lambda p: str(
                locations(p)[0] if locations(p) else [])

            if sort_order:
                partners = sorted(
                    (p for p in partners),
                    key=lambda p:
                    (locations(p) != [], first_location(p)), reverse=True)
            # sort ascending
            else:
                partners = sorted(
                    (p for p in partners),
                    key=lambda p: (locations(p) == [], first_location(p)))

    elif "activity" in sort_by:
        # treat ascending as meaning most recent, not earliest activity
        sort_order = "" if sort_order else "-"
        if sort_order:
            partners = partners.annotate(
                earliest_activity=Min('contactrecord__date_time')).order_by(
                    '-earliest_activity')
        else:
            partners = partners.annotate(
                latest_activity=Max('contactrecord__date_time')).order_by(
                    'latest_activity')
    else:
        partners = partners.order_by(*[sort_by] + order_by)

    return list(partners)


def new_partner_from_library(request):
    company = get_company_or_404(request)

    try:
        library_id = int(request.REQUEST.get('library_id') or 0)
    except ValueError:
        raise Http404
    library = get_object_or_404(PartnerLibrary, pk=library_id)

    tags = []
    for interest, color in [('disabled_veteran', '659274'),
                            ('female', '4BB1CF'),
                            ('minority', 'FAA732'),
                            ('veteran', '5EB94E')]:

        if getattr(library, 'is_%s' % interest):
            tag, _ = Tag.objects.get_or_create(
                company=company, name=interest.replace('_', ' ').title(),
                defaults={'hex_color': color})
            tags.append(tag)

    if library.is_disabled:
        tag, _ = Tag.objects.get_or_create(
            company=company, name="Disability",
            defaults={'hex_color': '808A9A'})
        tags.append(tag)

    tags.append(Tag.objects.get_or_create(
        company=company, name='OFCCP Library')[0])

    partner = Partner.objects.create(
        name=library.name,
        uri=library.uri,
        owner=company,
        library=library)
    partner.tags = tags

    location = Location.objects.create(
        address_line_one=library.street1,
        address_line_two=library.street2,
        city=library.city,
        state=library.st,
        country_code="USA",
        postal_code=library.zip_code)

    contact = Contact.objects.create(
        partner=partner,
        name=library.contact_name or "Not Available",
        email=library.email,
        phone=library.phone,
        notes=("This contact was generated from content in the "
               "OFCCP directory."))

    contact.locations.add(location)
    contact.tags = tags
    contact.save()

    partner.primary_contact = contact
    partner.save()

    return partner


def tag_get_or_create(company_id, data):
    tags = []
    for tag in data:
        obj, created = Tag.objects.get_or_create(
            company_id=company_id, name__iexact=tag, defaults={"name": tag}
        )
        tags.append(obj.id)

    return tags
