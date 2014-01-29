from django import forms
from collections import OrderedDict

from myprofile.forms import generate_custom_widgets
from myjobs.forms import BaseUserForm
from mypartners.models import Contact, Partner


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

    class Meta:
        form_name = "Contact Information"
        model = Contact
        exclude = ['user']
        widgets = generate_custom_widgets(model)
        widgets['notes'] = forms.Textarea(
            attrs={'rows': 5, 'cols': 24,
                   'placeholder': 'Notes About This Contact'})

    def save(self, commit=True):
        partner = Partner.objects.get(id=self.data['partner'])
        contact = self.instance
        contact.save()

        partner.add_contact(contact)
        partner.save()
        return


class PartnerInitialForm(BaseUserForm):
    """
    This form is used when an employer currently has no partner to create a
    partner (short and sweet version).
    """
    def __init__(self, *args, **kwargs):
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
        company_id = self.data['company_id']
        self.instance.owner_id = company_id

        if self.data['pc-contactname'] or self.data['pc-contactemail']:
            if self.data['pc-contactname'] and self.data['pc-contactemail']:
                contact = Contact(name=self.data['pc-contactname'],
                                  email=self.data['pc-contactemail'])
            elif self.data['pc-contactname']:
                contact = Contact(name=self.data['pc-contactname'])
            else:
                contact = Contact(email=self.data['pc-contactemail'])
            contact.save()

            self.instance.primary_contact = contact
            self.instance.save()
            self.instance.add_contact(contact)

        self.instance.save()


class NewPartnerForm(BaseUserForm):
    def __init__(self, *args, **kwargs):
        """
        This form is used only to create a partner.

        Had to change self.fields into an OrderDict to preserve order then
        'append' to the new fields because new fields need to be first.
        """
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
        exclude = ['user']
        widgets = generate_custom_widgets(model)
        widgets['notes'] = forms.Textarea(
            attrs={'rows': 5, 'cols': 24,
                   'placeholder': 'Notes About This Contact'})

    def save(self, commit=True):
        company_id = self.data['company_id']
        owner_id = company_id
        if self.data['partnerurl']:
            partner = Partner(name=self.data['partnername'],
                              uri=self.data['partnerurl'], owner_id=owner_id)
            partner.save()
        else:
            partner = Partner(name=self.data['partnername'], owner_id=owner_id)
            partner.save()

        self.data = self.remove_partner_data(
            self.data, ['partnername', 'partnerurl', 'csrfmiddlewaretoken',
                        'company', 'company_id', 'ct'])

        has_data = False
        for value in self.data.itervalues():
            if value != ['']:
                if value == ['USA']:
                    continue
                has_data = True

        if has_data:
            self.instance.save()
            partner.add_contact(self.instance)
            partner.primary_contact_id = self.instance.id
            partner.save()
        else:
            return

    def remove_partner_data(self, dictionary, keys):
        new_dictionary = dict(dictionary)
        for key in keys:
            del new_dictionary[key]
        return new_dictionary


class PartnerForm(BaseUserForm):
    """
    This form is used only to edit the partner form. (see prm/view/details)
    """
    def __init__(self, *args, **kwargs):
        super(PartnerForm, self).__init__(*args, **kwargs)
        choices = [(contact.id, contact.name) for contact in
                   kwargs['instance'].contacts.all()]
        if kwargs['instance'].primary_contact:
            for choice in choices:
                if choice[0] == kwargs['instance'].primary_contact_id:
                    choices.insert(0, choices.pop(choices.index(choice)))
        else:
            choices.insert(0, ('', "No Primary Contact"))
        self.fields['primary_contact'] = forms.ChoiceField(
            label="Primary Contact", required=False, choices=choices)

    class Meta:
        form_name = "Partner Information"
        model = Partner
        fields = ['name', 'uri']
        widgets = generate_custom_widgets(model)

    def save(self, commit=True):
        if self.data['primary_contact']:
            self.instance.primary_contact_id = self.data['primary_contact']
        self.instance.save()
        return
