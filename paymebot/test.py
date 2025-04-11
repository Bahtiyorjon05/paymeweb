

import os
import django
from django.contrib.auth.hashers import make_password

# Tell the toy box where the castle rules are
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paymebot.settings')

# Set up the castle rules
django.setup()

# Make the new key for "Ben1234!"
new_key = make_password("Ben1234!")
print("Here’s your new key:", new_key)