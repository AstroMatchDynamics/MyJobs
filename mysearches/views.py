import json
from datetime import datetime
from itertools import chain

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse
from django.template import RequestContext, loader
from django.shortcuts import render_to_response, get_object_or_404

from mysearches.models import SavedSearch, SavedSearchDigest
from mysearches.forms import SavedSearchForm, DigestForm
from mysearches.helpers import *

@login_required
def delete_saved_search(request,search_id):
    saved_search = SavedSearch.objects.get(id=search_id)
    if request.user == saved_search.user:
        saved_search.delete()
    return  HttpResponseRedirect('/saved-search')
        
@login_required
def saved_search_main(request):
    # instantiate the form if the digest object exists
    try:
        digest_obj = SavedSearchDigest.objects.get(user=request.user)
    except:
        digest_obj = None
    saved_searches = SavedSearch.objects.filter(user=request.user)
    email = request.user.email
    choices = ((email, email),)
    if request.method == "POST":
        action = request.POST.get('action')

        add_form = SavedSearchForm(user=request.user, instance=digest_obj)
        add_form.fields['email'].choices = choices
        add_form.fields['email'].initial = choices[0][0]
        if action in ['validate', 'save']:
            form = DigestForm(user=request.user, data=request.POST,
                              instance=digest_obj)
        else:
            form = DigestForm(user=request.user, instance=digest_obj)

        form.fields['email'].choices = choices
        form.fields['email'].initial = choices[0][0]

        if action == "validate":
            # Ensure that url is a valid job rss feed
            return validate_url(request, form)
        elif action == "save":
            # Save digest form
            return save_digest_form(request, form)
        elif action == "delete":
            # Remove digest from user
            try:
                SavedSearchDigest.objects.get(user=request.user)
            except SavedSearchDigest.DoesNotExist:
                pass
            return HttpResponse('success')
        elif action == "new_search":
            # Save new search form
            add_form = SavedSearchForm(user=request.user, data=request.POST)
            add_form.fields['email'].choices = choices
            add_form.fields['email'].initial = choices[0][0]
            return save_new_search_form(request, add_form)
        elif action == "get_edit":
            search_id = request.POST.get('search_id')
            saved_search = SavedSearch.objects.get(id=search_id)
            form = SavedSearchForm(user=request.user, instance=saved_search,
                                   auto_id='id_edit_%s')
            form.fields['email'].choices = choices
            form.fields['email'].initial = choices[0][0]
            return get_edit_template(request, form, search_id)
        elif action == "save_edit":
            search_id = request.POST.get('search_id')
            saved_search = SavedSearch.objects.get(id=search_id)
            form = SavedSearchForm(user=request.user, data=request.POST,
                                   instance=saved_search)
            form.fields['email'].choices = choices
            form.fields['email'].initial = choices[0][0]
            return save_edit_form(request, form, saved_search)
    else:
        form = DigestForm(user=request.user, instance=digest_obj)
        form.fields['email'].choices = choices
        form.fields['email'].initial = choices[0][0]
        add_form = SavedSearchForm(user=request.user)
        add_form.fields['email'].choices = choices
        add_form.fields['email'].initial = choices[0][0]
    return render_to_response('mysearches/saved_search_main.html',
                              {'saved_searches': saved_searches,
                               'form':form, 'add_form': add_form},
                              RequestContext(request))

@login_required
def view_full_feed(request, search_id):
    saved_search = SavedSearch.objects.get(id=search_id)
    if request.user == saved_search.user:
        items = parse_rss(saved_search.feed, saved_search.frequency)
        date = datetime.date.today()
        label = saved_search.label
        return render_to_response('mysearches/view_full_feed.html',
                                  {'label': label,
                                   'feed': saved_search.feed,
                                   'frequency': saved_search.frequency,
                                   'verbose_frequency':
                                     saved_search.get_verbose_frequency(),
                                   'link': saved_search.url,
                                   'items': items},
                                  RequestContext(request))
    else:
        return HttpResponseRedirect('/saved-search')

def more_feed_results(request):
    # Ajax request comes from the view_full_feed view when user scrolls to
    # bottom of the page
    if request.is_ajax():
        items = parse_rss(request.GET['feed'], request.GET['frequency'],
                          offset=request.GET['offset'])
        return render_to_response('mysearches/feed_page.html',
                                  {'items':items}, RequestContext(request))

def validate_url(request, form):
    rss_url, rss_soup = validate_dotjobs_url(request.POST['url'])
    if rss_url:
       feed_title = get_feed_title(rss_soup)
       # returns the RSS url via AJAX to show if field is validated
       # id valid, the label field is auto populated with the feed_title
       data = {'rss_url': rss_url,
               'feed_title': feed_title,
               'url_status': 'valid'
       }
    else:
        data = {'url_status': 'not valid'}
    return HttpResponse(json.dumps(data))

def save_digest_form(request, form):
    if form.is_valid():
        form.save()
        data = "success"
    else:
        data = "failure"
    return HttpResponse(data)

def save_new_search_form(request, add_form):
    if add_form.is_valid():
        add_form.save()
        data = "success"
        return HttpResponse(data)
    else:
        return HttpResponse(json.dumps(add_form.errors.keys()))

def get_edit_template(request, form, search_id):
    return render_to_response('mysearches/saved_search_edit.html',
                              {'form':form, 'search_id':search_id},
                              RequestContext(request))

def save_edit_form(request, form, saved_search):
    if request.user == saved_search.user:
        if form.is_valid():
            form.save()
            return HttpResponse('success')
        else:
            return HttpResponse(json.dumps(form.errors.keys()))
