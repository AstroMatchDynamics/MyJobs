import json
from datetime import datetime, date, timedelta
from itertools import chain

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.template import RequestContext, loader
from django.shortcuts import render_to_response, get_object_or_404

from myjobs.decorators import user_is_allowed
from myjobs.models import User
from mysearches.models import SavedSearch, SavedSearchDigest
from mysearches.forms import (SavedSearchForm, DigestForm,
                              PartnerSubSavedSearchForm)
from mysearches.helpers import *


@user_is_allowed(SavedSearch, 'id', pass_user=True)
def delete_saved_search(request, user=None):
    search_id = request.REQUEST.get('id')
    user = user or request.user
    try:
        search_id = int(search_id)

        # a single search is being deleted
        search = get_object_or_404(SavedSearch, id=search_id,
                                   user=user)
        search_name = search.label.title()
        search.delete()
    except ValueError:
        # all searches are being deleted
        SavedSearch.objects.filter(user=user).delete()
        search_name = 'all'

    return HttpResponseRedirect(
        reverse('saved_search_main_query')+'?d='+str(search_name))


@user_is_allowed()
@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def saved_search_main(request):
    # instantiate the form if the digest object exists
    try:
        digest_obj = SavedSearchDigest.objects.get(user=request.user)
    except:
        digest_obj = None
    updated = request.REQUEST.get('d')
    saved_searches = list(SavedSearch.objects.filter(user=request.user))
    partner_saved_searches = []
    # Check to see if any searches are PartnerSavedSearches
    for saved_search in saved_searches:
        if hasattr(saved_search, 'partnersavedsearch'):
            partner_saved_searches.append(
                saved_searches.pop(saved_searches.index(saved_search)))
    form = DigestForm(user=request.user, instance=digest_obj)
    add_form = SavedSearchForm(user=request.user)
    return render_to_response('mysearches/saved_search_main.html',
                              {'saved_searches': saved_searches,
                               'partner_saved_searches': partner_saved_searches,
                               'form': form,
                               'add_form': add_form,
                               'updated': updated,
                               'view_name': 'Saved Searches'},
                              RequestContext(request))


@user_is_allowed()
@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def view_full_feed(request):
    search_id = request.REQUEST.get('id')
    saved_search = SavedSearch.objects.get(id=search_id)
    if hasattr(saved_search, 'partnersavedsearch'):
        is_pss = True
    else:
        is_pss = False
    if request.user == saved_search.user:
        url_of_feed = url_sort_options(saved_search.feed,
                                       saved_search.sort_by,
                                       saved_search.frequency)
        # We don't care about the count; discard it
        items, count = parse_feed(url_of_feed, saved_search.frequency)
        start_date = date.today() + timedelta(get_interval_from_frequency(
                                                      saved_search.frequency))
        return render_to_response('mysearches/view_full_feed.html',
                                  {'search': saved_search,
                                   'items': items,
                                   'view_name': 'Saved Searches',
                                   'is_pss': is_pss,
                                   'start_date': start_date,
                                   'count': count},
                                  RequestContext(request))
    else:
        return HttpResponseRedirect(reverse('saved_search_main'))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def more_feed_results(request):
    # Ajax request comes from the view_full_feed view when user scrolls to
    # bottom of the page
    if request.is_ajax():
        url_of_feed = url_sort_options(request.GET['feed'],
                                       request.GET['sort_by'],
                                       request.GET['frequency'])
        items = parse_feed(url_of_feed, request.GET['frequency'],
                          offset=request.GET['offset'])[0]
        return render_to_response('mysearches/feed_page.html',
                                  {'items': items}, RequestContext(request))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def validate_url(request):
    if request.is_ajax():
        feed_title, rss_url = validate_dotjobs_url(request.POST['url'])
        if rss_url:
            # returns the RSS url via AJAX to show if field is validated
            # id valid, the label field is auto populated with the feed_title
            data = {'rss_url': rss_url,
                    'feed_title': feed_title,
                    'url_status': 'valid'}

        else:
            data = {'url_status': 'not valid'}
        return HttpResponse(json.dumps(data))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def save_digest_form(request):
    if request.method == 'POST':
        try:
            digest_obj = SavedSearchDigest.objects.get(user=request.user)
        except:
            digest_obj = None

        form = DigestForm(user=request.user, data=request.POST,
                          instance=digest_obj)
        if form.is_valid():
            form.save()
            data = ""
        else:
            data = json.dumps(form.errors)

        if request.is_ajax():
            # If this is an ajax request, we can return success/failure
            return HttpResponse(data)

    # The request is not ajax; Redirect to the main saved search page
    return HttpResponseRedirect(reverse('saved_search_main'))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def save_search_form(request):
    search_id = request.POST.get('search_id')

    try:
        search_id = int(search_id)
        original = SavedSearch.objects.get(id=search_id,
                                           user=request.user)
        if hasattr(original, 'partnersavedsearch'):
            form = PartnerSubSavedSearchForm(user=request.user,
                                             data=request.POST,
                                             instance=original)
        else:
            form = SavedSearchForm(user=request.user,
                                   data=request.POST,
                                   instance=original)
    except:
        form = SavedSearchForm(user=request.user, data=request.POST)

    if form.is_valid():
        form.save()

        if request.is_ajax():
            return HttpResponse(status=200)
        else:
            return HttpResponseRedirect(reverse('saved_search_main'))
    else:
        if request.is_ajax():
            return HttpResponse(json.dumps(form.errors))
        else:
            return render_to_response('mysearches/saved_search_edit.html',
                                      {'form': form,
                                       'search_id': search_id},
                                      RequestContext(request))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def edit_search(request):
    search_id = request.REQUEST.get('id')
    partner_saved_search = request.REQUEST.get('pss')
    if not partner_saved_search:
        if search_id:
            saved_search = get_object_or_404(SavedSearch, id=search_id,
                                             user=request.user)
            if hasattr(saved_search, 'partnersavedsearch'):
                raise Http404
        else:
            saved_search = None

        is_pss = False
        form = SavedSearchForm(user=request.user, instance=saved_search,
                               auto_id='id_edit_%s')
    else:
        if search_id:
            saved_search = get_object_or_404(SavedSearch, id=search_id,
                                             user=request.user)
            if hasattr(saved_search, 'partnersavedsearch'):
                is_pss = True
                form = PartnerSubSavedSearchForm(
                    instance=saved_search.partnersavedsearch,
                    auto_id=False)
        else:
            raise Http404

    return render_to_response('mysearches/saved_search_edit.html',
                              {'form': form, 'search_id': search_id,
                               'view_name': 'Saved Searches',
                               'search': saved_search,
                               'is_pss': is_pss,
                               'label': form.instance.label},
                              RequestContext(request))


@user_passes_test(User.objects.is_active)
@user_passes_test(User.objects.not_disabled)
def save_edit_form(request):
    if request.is_ajax():
        search_id = request.POST.get('search_id')
        saved_search = SavedSearch.objects.get(id=search_id)
        if request.user == saved_search.user:
            form = SavedSearchForm(user=request.user, data=request.POST,
                                   instance=saved_search)
            if form.is_valid():
                form.save()
                return HttpResponse('success')
            else:
                return HttpResponse(json.dumps(form.errors))


@user_is_allowed(SavedSearch, 'id', pass_user=True)
def unsubscribe(request, user=None):
    """
    Deactivates a user's saved searches.

    Inputs:
    :request: HttpRequest object
    :search_id: the string 'digest' to disable all searches
        or the id value of a specific search to be disabled
    """
    search_id = request.REQUEST.get('id')
    user = user or request.user
    try:
        search_id = int(search_id)
        saved_search = get_object_or_404(SavedSearch, id=search_id,
                                         user=user,
                                         is_active=True)

        # saved_search is a single search rather than a queryset this time
        cache = [saved_search]
        saved_search.is_active = False
        saved_search.save()
    except ValueError:
        digest = SavedSearchDigest.objects.get_or_create(
            user=user)[0]
        if digest.is_active:
            digest.is_active = False
            digest.save()
        saved_searches = SavedSearch.objects.filter(user=user,
                                                    is_active=True)
        # Updating the field that a queryset was filtered on seems to empty
        # that queryset; Make a copy and then update the queryset
        cache = list(saved_searches)
        saved_searches.update(is_active=False)

    return render_to_response('mysearches/saved_search_disable.html',
                              {'search_id': search_id,
                               'searches': cache,
                               'email_user': user},
                              RequestContext(request))
