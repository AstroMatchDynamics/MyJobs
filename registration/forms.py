from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth import authenticate
from django.utils.translation import ugettext_lazy as _

from myjobs.models import User


class CustomAuthForm(AuthenticationForm):
    """
    Custom login form based on Django's default login form. This allows us to
    bypass the is_active check on the user in order to allow a limited profile
    view for users that haven't activated yet.
    
    """
    username = forms.CharField(error_messages={'required':'Email is required.'},
                               label=_("Email"), required=True,
                               widget=forms.TextInput(
                                   attrs={'placeholder': _('Email'),
                                          'id':'id_username'}))
    password = forms.CharField(error_messages={'required':'Password is required.'},
                               label=_("Password"), required=True,
                               widget=forms.PasswordInput(
                                   attrs={'placeholder':_('Password'),
                                          'id':'id_password'},
                                   render_value=False,))

    remember_me = forms.BooleanField(label=_('Keep me logged in for 2 weeks'), required=False,
                                     widget=forms.CheckboxInput(
                                         attrs={'id':'id_remember_me'}))

    def __init__(self, request=None, *args, **kwargs):
        super(CustomAuthForm, self).__init__(request, *args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                error_msg = [
                    u"Invalid username or password. Please try again.",
                    u""]

                self._errors['username'] = self.error_class([error_msg[0]])
                self._errors['password'] = self.error_class([error_msg[1]])

                # These fields are no longer valid. Remove them from the
                # cleaned data
                del self.cleaned_data['username']
                del self.cleaned_data['password']  

        self.check_for_test_cookie()
        return self.cleaned_data

    def check_for_test_cookie(self):
        if self.request and not self.request.session.test_cookie_worked():
            raise forms.ValidationError(self.error_messages['no_cookies'])

    def get_user_id(self):
        if self.user_cache:
            return self.user_cache.id
        return None

    def get_user(self):
        return self.user_cache


class CustomPasswordResetForm(PasswordResetForm):
    """
    Custom password reset form validates even when user is not active.
    """
    email = forms.CharField(error_messages={'required': 'Email is required.'},
                            label=_("Email"), required=True,
                            widget=forms.TextInput(
                                attrs={'placeholder': _('Email'),
                                       'id': 'id_email',
                                       'class': 'reset-pass-input'}))


class RegistrationForm(forms.Form):
    email = forms.EmailField(error_messages={'required':'Email is required.'},
                             label=_("Email"), required=True,
                             widget=forms.TextInput(attrs={
                                 'placeholder': _('Email'), 
                                 'id':'id_email',
                                 'autocomplete':'off'}),
                             max_length=255)
    password1 = forms.CharField(error_messages={'required':'Password is required.'},
                                label=_("Password"), required=True,
                                widget=forms.PasswordInput(attrs={
                                    'placeholder':_('Password'),
                                    'id':'id_password1',
                                    'autocomplete':'off'},
                                    render_value=False))
    password2 = forms.CharField(error_messages={'required':'Password (again) is required.'},
                                label=_("Password (again)"), required=True,
                                widget=forms.PasswordInput(attrs={
                                    'placeholder': _('Password (again)'),
                                    'id': 'id_password2',
                                    'autocomplete':'off'}, 
                                render_value=False))

    def clean_email(self):
        """
        Validate that the username is alphanumeric and is not already
        in use.
        
        """
        if User.objects.get_email_owner(self.cleaned_data['email']):
            raise forms.ValidationError(_("A user with that email already exists."))
        else:
            return self.cleaned_data['email']

    def clean(self):
        """
        Verify that the values entered into the two password fields
        match.
        
        """
        if 'password1' in self.cleaned_data and 'password2' in self.cleaned_data:
            if self.cleaned_data['password1'] != self.cleaned_data['password2']:
                error_msg = u"The new password fields did not match."
                self._errors["password1"] = self.error_class([error_msg])
                self._errors["password2"] = self.error_class([error_msg])

                # These fields are no longer valid. Remove them from the
                # cleaned data.
                del self.cleaned_data["password1"]
                del self.cleaned_data["password2"]

            else:
                return self.cleaned_data
