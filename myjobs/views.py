import json
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.forms.models import model_to_dict
from django.http import HttpResponseRedirect, HttpResponse
from django.template import RequestContext
from django.shortcuts import render_to_response, get_object_or_404
from django.views.generic import TemplateView

from myjobs.forms import *
from myjobs.helpers import *
from myprofile.forms import *
from registration.forms import *



logger = logging.getLogger('__name__')

class About(TemplateView):
    template_name = "about.html"


class Privacy(TemplateView):
    template_name = "privacy.html"


def home(request):
    """
    The home page view receives 2 separate Ajax requests, one for the registration
    form and another for the initial profile information form. If everything
    checks out alright and the form saves with no errors, it returns a simple string,
    'valid', as an HTTP Response, which the front end recognizes as a signal to
    continue with the account creation process. If an error occurs, this triggers
    the jQuery to update the page. The form instances with errors must be passed
    back to the form template it was originally from.

    """

    registrationform = RegistrationForm(auto_id=False)
    loginform = CustomAuthForm(auto_id=False)

    
    # Parameters passed into the form class. See forms.py in myprofile
    # for more detailed docs
    settings = {'auto_id':False, 'empty_permitted':True, 'only_show_required':True,
                'user': request.user}
    settings_show_all = {'auto_id':False, 'empty_permitted':True,
                         'only_show_required':False, 'user': request.user}
    
    name_form = instantiate_profile_forms(request,[NameForm],settings)[0]
    education_form = instantiate_profile_forms(request,[EducationForm],
                                               settings)[0]
    phone_form = instantiate_profile_forms(request,[PhoneForm],settings)[0]
    work_form = instantiate_profile_forms(request,[EmploymentForm],settings)[0]
    address_form = instantiate_profile_forms(request,[AddressForm],settings)[0]

        
    data_dict = {'registrationform':registrationform,
                 'loginform': loginform,
                 'name_form': name_form,
                 'phone_form': phone_form,
                 'address_form': address_form,
                 'work_form': work_form,
                 'education_form': education_form,
                 'name_obj': get_name_obj(request)}

    if request.method == "POST":
        if request.POST['action'] == "register":
            registrationform = RegistrationForm(request.POST, auto_id=False)
            if registrationform.is_valid():
                new_user = User.objects.create_inactive_user(**registrationform.
                                                             cleaned_data)
                user_cache = authenticate(username = registrationform.
                                          cleaned_data['email'],
                                          password = registrationform.
                                          cleaned_data['password1'])
                login(request, user_cache)
                # pass in gravatar url once user is logged in. Image generated
                # in AJAX success
                data={'gravatar_url': new_user.get_gravatar_url(size=100)}
                return HttpResponse(json.dumps(data))
            else:
                return render_to_response('includes/widget-user-registration.html',
                                          {'form': registrationform},
                                          context_instance=RequestContext(request))
                
        elif request.POST['action'] == "login":
            loginform = CustomAuthForm(request.POST)
            if loginform.is_valid():
                login(request, loginform.get_user())
                return HttpResponseRedirect('/account')
                
        elif request.POST['action'] == "save_profile":
            # rebuild the form object with the post parameter = True            
            name_form = instantiate_profile_forms(request,[NameForm],
                                                  settings,post=True)[0]
            education_form = instantiate_profile_forms(request,[EducationForm],
                                                  settings,post=True)[0]
            phone_form = instantiate_profile_forms(request,[PhoneForm],
                                                  settings,post=True)[0]
            work_form = instantiate_profile_forms(request,[EmploymentForm],
                                                  settings,post=True)[0]
            address_form = instantiate_profile_forms(request,[AddressForm],
                                                  settings_show_all,post=True)[0]
            #required_forms = [name_form,phone_form]
            form_list = []
            form_list.append(name_form)
            form_list.append(education_form)
            form_list.append(phone_form)
            form_list.append(work_form)
            form_list.append(address_form)
            all_valid = True
            for form in form_list:
                if not form.is_valid():
                    all_valid = False

            if all_valid:
                for form in form_list:
                    if form.cleaned_data:
                        form.save()
                return HttpResponse('valid')
            else:
                return render_to_response('includes/initial-profile-form.html',
                                          {'name_form': name_form,
                                           'phone_form': phone_form,
                                           'address_form': address_form,
                                           'work_form': work_form,
                                           'education_form': education_form},
                                          context_instance=RequestContext(request))
            
    return render_to_response('index.html', data_dict, RequestContext(request))

    
@login_required
def view_account(request):
    ctx = {'name_obj': get_name_obj(request)}
    return render_to_response('done.html', ctx, RequestContext(request))

@login_required
def edit_account(request):
    initial_dict = model_to_dict(request.user)
    name_obj = get_name_obj(request)
    if name_obj:
        initial_dict.update(model_to_dict(name_obj))
    
    if request.method == "POST":
        form = EditProfileForm(request.POST)
        if form.is_valid():
            form.save(request.user)
            return HttpResponseRedirect('/account')
    else:
        form = EditProfileForm(initial=initial_dict)
        
    ctx = {'form': form,
           'user': request.user,
           'gravatar_100': request.user.get_gravatar_url(size=100),
           'name_obj': name_obj}
    
    return render_to_response('edit-account.html', ctx,
                              RequestContext(request))

@login_required
def change_password(request):
    if request.method == "POST":
        form = ChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/account')
    else:
        form = ChangePasswordForm(user=request.user)
    
    ctx = {
        'form':form,
        'name_obj': get_name_obj(request)
        }
    return render_to_response('registration/password_change_form.html', ctx,
                              RequestContext(request))

def error(request):
    """Error view"""
    messages = get_messages(request)
    ctx = {
        'name_obj': get_name_object(request),
        'version': version,
        'messages': messages
        }
    return render_to_response('error.html', ctx, RequestContext(request))