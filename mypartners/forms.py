from django import forms
from django.core.exceptions import ValidationError
from django.forms.util import ErrorList
from django.utils.timezone import get_current_timezone_name

from collections import OrderedDict
import pytz

from myprofile.forms import generate_custom_widgets
from mypartners.models import (Contact, OFCCPContact, Partner, ContactRecord, 
                               PRMAttachment, ADDITION, CHANGE, 
                               MAX_ATTACHMENT_MB)
from mypartners.helpers import log_change, get_attachment_link
from mypartners.widgets import (MultipleFileField,
                                SplitDateTimeDropDownField, TimeDropDownField)


class ContactForm(forms.ModelForm):
    """
    Creates a new contact or edits an existing one.
    """
    def __init__(self, *args, **kwargs):
        super(ContactForm, self).__init__(*args, **kwargs)
        self.fields['name'] = forms.CharField(
            label="Name", max_length=255, required=True,
            widget=forms.TextInput(attrs={'placeholder': 'Full Name',
                                          'id': 'id_contact-name'}))
        if self.instance.user:
            self.fields['email'].widget.attrs['readonly'] = True
            self.fields['email'].help_text = 'This email address is ' \
                                             'maintained by the owner ' \
                                             'of the My.jobs email account ' \
                                             'and cannot be changed.'

    class Meta:
        form_name = "Contact Information"
        model = Contact
        exclude = ['user', 'partner']
        widgets = generate_custom_widgets(model)
        widgets['notes'] = forms.Textarea(
            attrs={'rows': 5, 'cols': 24,
                   'placeholder': 'Notes About This Contact'})

    def clean_email(self):
        if self.instance.user:
            return self.instance.email
        return self.cleaned_data['email']

    def save(self, user, partner, commit=True):
        new_or_change = CHANGE if self.instance.pk else ADDITION
        partner = Partner.objects.get(id=self.data['partner'])
        self.instance.partner = partner
        contact = super(ContactForm, self).save(commit)

        log_change(contact, self, user, partner, contact.name,
                   action_type=new_or_change)

        return contact


class PartnerInitialForm(forms.ModelForm):
    """
    This form is used when an employer currently has no partner to create a
    partner (short and sweet version).

    """
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', '')
        super(PartnerInitialForm, self).__init__(*args, **kwargs)
        self.fields['pc-contactname'] = forms.CharField(
            label="Primary Contact Name", max_length=255, required=False,
            widget=forms.TextInput(
                attrs={'placeholder': 'Primary Contact Name'}))
        self.fields['pc-contactemail'] = forms.EmailField(
            label="Primary Contact Email", max_length=255, required=False,
            widget=forms.TextInput(
                attrs={'placeholder': 'Primary Contact Email'}))

    class Meta:
        form_name = "Partner Information"
        model = Partner
        fields = ['name', 'uri']
        widgets = generate_custom_widgets(model)

    def save(self, commit=True):
        new_or_change = CHANGE if self.instance.pk else ADDITION
        self.instance.owner_id = self.data['company_id']
        partner = super(PartnerInitialForm, self).save(commit)

        contact_name = self.data.get('pc-contactname')
        contact_email = self.data.get('pc-contactemail', '')
        if contact_name:
            contact = Contact.objects.create(name=contact_name,
                                             email=contact_email,
                                             partner=partner)
            contact.save()
            log_change(contact, self, self.user, partner, contact.name,
                       action_type=ADDITION)
            partner.primary_contact = contact
            partner.save()

        log_change(partner, self, self.user, partner, partner.name,
                   action_type=new_or_change)

        return partner


class NewPartnerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        """
        This form is used only to create a partner.

        Had to change self.fields into an OrderDict to preserve order then
        'append' to the new fields because new fields need to be first.

        """
        self.user = kwargs.pop('user', '')
        super(NewPartnerForm, self).__init__(*args, **kwargs)
        for field in self.fields.itervalues():
            field.label = "Primary Contact " + field.label
        model_fields = OrderedDict(self.fields)

        new_fields = {
            'partnername': forms.CharField(
                label="Partner Organization", max_length=255, required=True,
                widget=forms.TextInput(
                    attrs={'placeholder': 'Partner Organization',
                           'id': 'id_partner-partnername'})),
            'partnerurl': forms.URLField(
                label="Partner URL", max_length=255, required=False,
                widget=forms.TextInput(attrs={'placeholder': 'Partner URL',
                                              'id': 'id_partner-partnerurl'}))
        }

        ordered_fields = OrderedDict(new_fields)
        ordered_fields.update(model_fields)
        self.fields = ordered_fields

    class Meta:
        form_name = "Partner Information"
        model = Contact
        exclude = ['user', 'partner']
        widgets = generate_custom_widgets(model)
        widgets['notes'] = forms.Textarea(
            attrs={'rows': 5, 'cols': 24,
                   'placeholder': 'Notes About This Contact'})

    def save(self, commit=True):
        # self.instance is a Contact instance
        company_id = self.data['company_id']

        partner_url = self.data.get('partnerurl', '')

        partner = Partner.objects.create(name=self.data['partnername'],
                                         uri=partner_url, owner_id=company_id)

        log_change(partner, self, self.user, partner, partner.name,
                   action_type=ADDITION)

        self.data = remove_partner_data(self.data,
                                        ['partnername', 'partnerurl',
                                         'csrfmiddlewaretoken', 'company',
                                         'company_id', 'ct'])
        has_data = False
        for value in self.data.itervalues():
            if value != [''] and value != ['USA']:
                has_data = True
        if has_data:
            self.instance.partner = partner
            instance = super(NewPartnerForm, self).save(commit)
            partner.primary_contact = instance
            partner.save()
            log_change(instance, self, self.user, partner, instance.name,
                       action_type=ADDITION)

            return instance
        # No contact was created
        return None


def remove_partner_data(dictionary, keys):
    new_dictionary = dict(dictionary)
    for key in keys:
        del new_dictionary[key]
    return new_dictionary


class PartnerForm(forms.ModelForm):
    """
    This form is used only to edit the partner form. (see prm/view/details)

    """
    def __init__(self, *args, **kwargs):
        super(PartnerForm, self).__init__(*args, **kwargs)
        contacts = Contact.objects.filter(partner=kwargs['instance'])
        choices = [(contact.id, contact.name) for contact in contacts]

        if kwargs['instance'].primary_contact:
            for choice in choices:
                if choice[0] == kwargs['instance'].primary_contact_id:
                    choices.insert(0, choices.pop(choices.index(choice)))
            if not kwargs['instance'].primary_contact:
                choices.insert(0, ('', "No Primary Contact"))
            else:
                choices.append(('', "No Primary Contact"))
        else:
            choices.insert(0, ('', "No Primary Contact"))
        self.fields['primary_contact'] = forms.ChoiceField(
            label="Primary Contact", required=False, initial=choices[0][0],
            choices=choices)

    class Meta:
        form_name = "Partner Information"
        model = Partner
        fields = ['name', 'uri']
        widgets = generate_custom_widgets(model)

    def save(self, user, commit=True):
        new_or_change = CHANGE if self.instance.pk else ADDITION

        instance = super(PartnerForm, self).save(commit)
        # Explicity set the primary_contact for the partner and re-save.
        try:
            instance.primary_contact = Contact.objects.get(
                pk=self.data['primary_contact'], partner=self.instance)
        except (Contact.DoesNotExist, ValueError):
            instance.primary_contact = None
        instance.save()
        log_change(instance, self, user, instance, instance.name,
                   action_type=new_or_change)

        return instance


class BasicPartnerSearchForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', '')
        super(BasicPartnerSearchForm, self).__init__(*args, **kwargs)

    class Meta:
        form_name = "Basic Partner Search"
        model =  OFCCPContact
        widgets = generate_custom_widgets(model)

class AdvancedPartnerSearchForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', '')
        super(AdvancedPartnerForm, self).__init__(*args, **kwargs)

    class Meta:
        form_name = "Advanced Partner Search"
        model =  OFCCPContact
        widgets = generate_custom_widgets(model)

def PartnerEmailChoices(partner):
    choices = [(None, '----------')]
    contacts = Contact.objects.filter(partner=partner)
    for contact in contacts:
        if contact.user:
            choices.append((contact.user.email, contact.name))
        else:
            if contact.email:
                choices.append((contact.email, contact.name))
    return choices


class ContactRecordForm(forms.ModelForm):
    date_time = SplitDateTimeDropDownField(label='Date & Time')
    length = TimeDropDownField()
    attachment = MultipleFileField(required=False,
                                   help_text="Max file size %sMB" %
                                             MAX_ATTACHMENT_MB)

    class Meta:
        form_name = "Contact Record"
        exclude = ('created_by', )
        fields = ('contact_type', 'contact_name',
                  'contact_email', 'contact_phone', 'location',
                  'length', 'subject', 'date_time', 'job_id',
                  'job_applications', 'job_interviews', 'job_hires',
                  'notes', 'attachment')
        model = ContactRecord

    def __init__(self, *args, **kwargs):
        partner = kwargs.pop('partner')
        instance = kwargs.get('instance')
        contacts = Contact.objects.filter(partner=partner)
        choices = [(c.id, c.name) for c in contacts]
        if not instance:
            choices.insert(0, ('None', '----------'))
        else:
            try:
                index = [x[1] for x in choices].index(instance.contact_name)
            except ValueError:
                # This is a ContactRecord for a contact that has been
                # deleleted.
                tup = (instance.contact_name, instance.contact_name)
                choices.insert(0, tup)
            else:
                tup = choices[index]
                choices.pop(index)
                choices.insert(0, tup)
        super(ContactRecordForm, self).__init__(*args, **kwargs)

        if not instance or instance.contact_type != 'pssemail':
            # Remove Partner Saved Search from the list of valid
            # contact type choices.
            contact_type_choices = self.fields["contact_type"].choices
            index = [x[0] for x in contact_type_choices].index("pssemail")
            contact_type_choices.pop(index)
            self.fields["contact_type"] = forms.ChoiceField(
                widget=forms.Select(), choices=contact_type_choices,
                label="Contact Type")

        self.fields["contact_name"] = forms.ChoiceField(
            widget=forms.Select(), choices=choices, label="Contact")

        # If there are attachments create a checkbox option to delete them.
        if instance:
            attachments = PRMAttachment.objects.filter(contact_record=instance)
            if attachments:
                choices = [(a.pk, get_attachment_link(
                    partner.owner.id, partner.id, a.id,
                    a.attachment.name.split("/")[-1])) for a in attachments]
                self.fields["attach_delete"] = forms.MultipleChoiceField(
                    required=False, choices=choices, label="Delete Files",
                    widget=forms.CheckboxSelectMultiple)

    def clean(self):
        contact_type = self.cleaned_data.get('contact_type', None)
        if contact_type == 'email' and not self.cleaned_data['contact_email']:
            self._errors['contact_email'] = ErrorList([""])
        elif contact_type == 'phone' and not self.cleaned_data['contact_phone']:
            self._errors['contact_phone'] = ErrorList([""])
        elif contact_type == 'meetingorevent' and not self.cleaned_data['location']:
            self._errors['location'] = ErrorList([""])
        elif contact_type == 'job' and not self.cleaned_data['job_id']:
            self._errors['job_id'] = ErrorList([""])
        return self.cleaned_data

    def clean_contact_name(self):
        contact_id = self.cleaned_data['contact_name']
        if contact_id == 'None' or not contact_id:
            raise ValidationError('required')
        try:
            return Contact.objects.get(id=int(contact_id)).name
        except (Contact.DoesNotExist, ValueError):
            # Contact has been deleted. Preserve the contact name.
            return self.cleaned_data['contact_name']

    def clean_attachment(self):
        attachments = self.cleaned_data.get('attachment', None)
        for attachment in attachments:
            if attachment and attachment.size > (MAX_ATTACHMENT_MB << 20):
                raise ValidationError('File too large')
        return self.cleaned_data['attachment']

    def clean_date_time(self):
        """
        Converts date_time field from localized time zone to utc.

        """
        date_time = self.cleaned_data['date_time']
        user_tz = pytz.timezone(get_current_timezone_name())
        date_time = user_tz.localize(date_time)
        return date_time.astimezone(pytz.utc)

    def save(self, user, partner, commit=True):
        new_or_change = CHANGE if self.instance.pk else ADDITION
        self.instance.partner = partner
        self.instance.created_by = user
        instance = super(ContactRecordForm, self).save(commit)

        attachments = self.cleaned_data.get('attachment', None)
        for attachment in attachments:
            if attachment:
                prm_attachment = PRMAttachment(attachment=attachment,
                                               contact_record=self.instance)
                setattr(prm_attachment, 'partner', self.instance.partner)
                prm_attachment.save()

        attach_delete = self.cleaned_data.get('attach_delete', [])
        for attachment in attach_delete:
            PRMAttachment.objects.get(pk=attachment).delete()

        try:
            identifier = instance.contact_email if instance.contact_email \
                else instance.contact_phone if instance.contact_phone \
                else instance.contact_name
        except Contact.DoesNotExist:
            # This should only happen if the user is editing the ids in the drop
            # down list of contacts. Since it's too late for a validation error
            # the user can deal with the logging issues they created.
            identifier = "unknown contact"

        log_change(instance, self, user, partner, identifier,
                   action_type=new_or_change)

        return instance

