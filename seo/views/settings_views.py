from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.views.generic import View

from seo.forms import settings_forms
from seo.models import SeoSite
from universal.views import RequestFormViewBase


class SeoSiteSettingsFormView(RequestFormViewBase):
    display_name = 'Site'
    form_class = settings_forms.SeoSiteSettingsForm
    template_name = 'postajob/form.html'

    add_name = 'seosite_settings_add'
    update_name = 'seosite_settings_update'
    delete_name = 'seosite_settings_delete'

    def get_queryset(self, request):
        return SeoSite.objects.all()


class EmailDomainFormView(View):
    base_template_context = {
        'custom_action': 'Edit',
        'display_name': 'Email Domains'
    }

    def success_url(self):
        return reverse('purchasedmicrosite_admin_overview')

    def get(self, request):
        form = settings_forms.EmailDomainForm(request=request)
        kwargs = dict(self.base_template_context)
        kwargs.update({
            'form': form,
        })
        return render_to_response('postajob/form.html', kwargs,
                                  context_instance=RequestContext(request))

    def post(self, request):
        form = settings_forms.EmailDomainForm(request.POST, request=request)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(self.success_url())
        kwargs = dict(self.base_template_context)
        kwargs.update({
            'form': form,
        })
        return render_to_response('postajob/form.html', kwargs,
                                  context_instance=RequestContext(request))