import os
import sys

sys.path.append('/home/ubuntu/django-apps/')

os.environ['DJANGO_SETTINGS_MODULE'] = 'flangio.settings'

import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()

