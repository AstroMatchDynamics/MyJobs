from django.conf.urls import *
from django.contrib import admin
from django.db.models.loading import cache as model_cache
from django.views.generic import RedirectView

from seo.views.search_views import BusinessUnitAdminFilter


# This is a bit of code pulled from a Django TRAC ticket describing a problem
# I was seeing when working with the inline model forms:
# https://code.djangoproject.com/ticket/10405#comment:11

# Without this, on pages that aren't serving job-related content, e.g. sitemap,
# stylesheet, etc. pages, we'd see an error like:
# AttributeError: 'str' object has no attribute '_default_manager'

# The Trac ticket linked above recommended including this bit of code, and also
# included a comprehensive explanation. When/if this particular issue gets
# resolved we can safely remove this conditional.
if not model_cache.loaded:
    model_cache.get_models()

from tastypie.api import Api
from seo.api.resources import *

v1_api = Api(api_name="v1")
v1_api.register(SeoSiteResource())
v1_api.register(ATSResource())
v1_api.register(GroupResource())
v1_api.register(ViewSourceResource())
v1_api.register(BusinessUnitResource())
v1_api.register(GoogleAnalyticsResource())
v1_api.register(GoogleAnalyticsCampaignResource())
v1_api.register(SpecialCommitmentResource())
v1_api.register(CustomFacetResource())
v1_api.register(ConfigurationResource())
v1_api.register(FeaturedCompanyResource())
v1_api.register(CompanyResource())
v1_api.register(BillboardImageResource())
v1_api.register(BillboardHotspotResource())
v1_api.register(MocResource())
v1_api.register(MocDetailResource())
v1_api.register(OnetResource())
v1_api.register(JobSearchResource())
v1_api.register(JobResource())

admin.autodiscover()
handler404 = 'seo.views.search_views.dseo_404'
handler500 = 'seo.views.search_views.dseo_500'


# API endpoints
urlpatterns = patterns('',
    url('^api/', include(v1_api.urls))
)

# secure.my.jobs redirects
urlpatterns += patterns('',
    url(r'^about/$',
        RedirectView.as_view(url='https://secure.my.jobs/about')),
    url(r'^account/$',
        RedirectView.as_view(url='https://secure.my.jobs/account/edit')),
    url(r'^candidates/$',
        RedirectView.as_view(url='https://secure.my.jobs/candidates/view')),
    url(r'^contact/$',
        RedirectView.as_view(url='https://secure.my.jobs/contact/')),
    url(r'^privacy/$',
        RedirectView.as_view(url='https://secure.my.jobs/privacy/')),
    url(r'^profile/$',
        RedirectView.as_view(url='https://secure.my.jobs/profile/view')),
    url(r'^savedsearch/$',
        RedirectView.as_view(url='https://secure.my.jobs/saved-search/view')),
    url(r'^terms/$',
        RedirectView.as_view(url='https://secure.my.jobs/terms/')),
    )

# Custom Admin URLs
urlpatterns += patterns('seo.views.search_views',
    url(r'^admin/groupsites/$', 'get_group_sites'),
    url(r'^admin/grouprelationships/$', 'get_group_relationships'),
)

urlpatterns += patterns('',
    url(r'^admin/', include(admin.site.urls)),
    url('', include('seo.urls.search_urls', app_name='seo')),
    url('settings/', include('seo.urls.settings_urls')),
    url('^mocmaps/', include('moc_coding.urls', app_name='moc_coding')),
    url(r'^logout/$', 'django.contrib.auth.views.logout', {'next_page': '/'},
        name='auth_logout'),
    url(r'^posting/', include('postajob.urls', app_name='postajob')),
)


urlpatterns += patterns(
    '',
    # Filtering urls
    url(r'^data/filter/business_units/$', BusinessUnitAdminFilter.as_view(),
        name='buid_admin_fsm'),
)


from myjobs.views import About, Testimonials, Privacy, Terms

urlpatterns += patterns(
    '',
    url(r'^accounts/', include('registration.urls')),
    url(r'^about/$', About.as_view(), name='about'),
    url(r'^about/testimonials/$', Testimonials.as_view(), name='testimonials'),
    url(r'^privacy/$', Privacy.as_view(), name='privacy'),
    url(r'^terms/$', Terms.as_view(), name='terms'),
    url(r'^contact/$', 'contact', name='contact'),
    url(r'^contact-faq', 'contact_faq', name='contact_faq'),
)
urlpatterns += patterns(
    'myjobs.views',
    url(r'^edit/$', 'edit_account', name='edit_account'),
)