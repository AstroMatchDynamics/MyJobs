import factory
import factory.django

from social_links.models import SocialLink, SocialLinkType


class SocialLinkFactory(factory.django.DjangoModelFactory):
    FACTORY_FOR = SocialLink

    link_url = 'google.com'
    link_title = 'Link Title'
    link_type = 'DirectEmployers'
    link_icon = 'www.example.com'
    content_type_id = 1


class SocialLinkTypeFactory(factory.django.DjangoModelFactory):
    FACTORY_FOR = SocialLinkType

    site = 'Social Site'
    icon = factory.django.FileField(filename='icon.png')
