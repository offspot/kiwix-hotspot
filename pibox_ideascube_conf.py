from .base import *  # pragma: no flakes

from tzlocal import get_localzone

ALLOWED_HOSTS = ['.koombook.lan', 'localhost', '127.0.0.1']
TIME_ZONE = get_localzone().zone
DOMAIN = 'koombook.lan'
STAFF_HOME_CARDS = [c for c in STAFF_HOME_CARDS  # pragma: no flakes
                    if c['url'] in ['user_list', 'server:settings']]
BUILTIN_APP_CARDS = []
EXTRA_APP_CARDS = []
