from django.contrib import admin

from postajob.forms import (JobForm, ProductForm, ProductGroupingForm,
                            SitePackageForm)
from postajob.models import (Job, Product, ProductGrouping, SitePackage)


class ModelAdminWithRequest(admin.ModelAdmin):
    def get_form(self, request, obj=None, **kwargs):
        """
        Override get_form() to allow the request information to be
        passed along to the JobForm.

        """
        ModelForm = super(ModelAdminWithRequest, self).get_form(request, obj,
                                                                **kwargs)

        class ModelFormMetaClass(ModelForm):
            def __new__(cls, *args, **kwargs):
                kwargs['request'] = request
                return ModelForm(*args, **kwargs)
        return ModelFormMetaClass


class JobAdmin(ModelAdminWithRequest):
    form = JobForm
    list_display = ('__unicode__', 'guid', )
    search_fields = ('title', 'owner', 'site_packages__sites__domain', )

    fieldsets = (
        ('Job Information', {
            'fields': (('title', ), 'reqid', 'description',
                       'city', 'state', 'country', 'zipcode',
                       ('date_expired', 'is_expired', 'autorenew', )),
        }),
        ('Application Instructions', {
            'fields': ('apply_type', 'apply_link', 'apply_email',
                       'apply_info', ),
        }),
        ('Site Information', {
            'fields': ('owner', 'post_to', 'site_packages', ),
        }),
    )

    def delete_model(self, request, obj):
        # Django admin bulk delete doesn't trigger a post_delete signal. This
        # ensures that the remove_from_solr() usually handled by a delete
        # signal is called in those cases.
        obj.remove_from_solr()
        obj.delete()

    def queryset(self, request):
        """
        Prevent users from seeing jobs that don't belong to their company
        in the admin.

        """
        jobs = super(JobAdmin, self).queryset(request)
        if not request.user.is_superuser:
            jobs = jobs.filter(owner__admins=request.user)
        return jobs


class SitePackageAdmin(ModelAdminWithRequest):
    form = SitePackageForm
    list_display = ('id', 'name', )

    def queryset(self, request):
        """
        Make SeoSite-specific packages unavailable in the admin and prevent
        non-superusers from seeing packages.

        """
        packages = SitePackage.objects.user_available()
        if not request.user.is_superuser:
            packages = packages.filter(owner__admins=request.user)
        return packages


class ProductFormAdmin(ModelAdminWithRequest):
    form = ProductForm
    list_display = ('owner', 'site_package', )

    fieldsets = (
        ('', {
            'fields': ('name', )
        }),
        ('Company Information', {
            'fields': ('owner', 'site_package', )
        }),
        ('Package Details', {
            'fields': ('cost', 'posting_window_length',
                       'max_job_length', 'num_jobs_allowed', )
        }),
    )

    def queryset(self, request):
        products = Product.objects.all()
        if not request.user.is_superuser:
            products = products.filter(owner__admins=request.user)
        return products


class ProductGroupingFormAdmin(ModelAdminWithRequest):
    form = ProductGroupingForm
    list_display = ('score', 'grouping_name', )

    def queryset(self, request):
        groups = ProductGrouping.objects.all()
        if not request.user.is_superuser:
            groups = groups.filter(owner__admins=request.user)
        return groups


admin.site.register(Job, JobAdmin)
admin.site.register(SitePackage, SitePackageAdmin)
admin.site.register(Product, ProductFormAdmin)
admin.site.register(ProductGrouping, ProductGroupingFormAdmin)