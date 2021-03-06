import uuid
import factory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'myjobs.User'

    email = 'alice@example.com'
    gravatar = 'alice@example.com'
    password = '5UuYquA@'
    user_guid = factory.LazyAttribute(lambda n: '{0}'.format(uuid.uuid4()))
    is_active = True
    is_verified = True

    @classmethod
    def _prepare(cls, create, **kwargs):
        password = kwargs.pop('password', None)
        user = super(UserFactory, cls)._prepare(create, **kwargs)
        if password:
            user.set_password(password)
            if create:
                user.save()
        return user
