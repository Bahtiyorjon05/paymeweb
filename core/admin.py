from django.contrib import admin
from .models import User, Transaction, Card, Contact, Complaint



admin.site.register(User)
admin.site.register(Transaction)
admin.site.register(Card)
admin.site.register(Contact)
admin.site.register(Complaint)