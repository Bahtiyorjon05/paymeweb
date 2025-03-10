

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class User(AbstractUser):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')], null=True)
    phone_number = models.CharField(max_length=20, unique=True)
    joined_at = models.DateTimeField(default=timezone.now)
    default_currency = models.CharField(max_length=3, default='USD', choices=[('UZS', 'Uzbek Som'), ('RUB', 'Russian Rubles'), ('USD', 'US Dollar'), ('KRW', 'Korean Won'), ('EUR', 'Euro')])
    two_factor_code = models.CharField(max_length=50, null=True, blank=True)
    is_blocked = models.BooleanField(default=False)
    block_until = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(default=timezone.now)
    email = models.EmailField(unique=True, null=True, blank=True, default=None)

    groups = models.ManyToManyField('auth.Group', related_name='core_user_groups', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='core_user_permissions', blank=True)

    def __str__(self):
        return self.username
    
class Card(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cards')
    card_number = models.CharField(max_length=19, unique=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    password = models.CharField(max_length=6)
    created_at = models.DateTimeField(default=timezone.now)
    currency = models.CharField(max_length=3, default='USD', choices=[
        ('UZS', 'Uzbek Som'),
        ('RUB', 'Russian Rubles'),
        ('USD', 'US Dollar'),
        ('KRW', 'Korean Won'),
        ('EUR', 'Euro')
    ])
    def __str__(self):
        return f"{self.card_number} ({self.user.username})"

class Contact(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contacts')
    contact_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contacted_by')
    added_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} -> {self.contact_user.username}"

class Transaction(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_transactions')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_transactions')
    sender_card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='sent_from', null = True, blank = True)
    receiver_card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='received_to', null = True, blank = True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, choices=User._meta.get_field('default_currency').choices)
    received_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True)
    received_currency = models.CharField(max_length=3, choices=[('UZS', 'Uzbek Som'), ('RUB', 'Russian Rubles'), ('USD', 'US Dollar'), ('KRW', 'Korean Won'), ('EUR', 'Euro')], null=True)
    timestamp = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, default='completed')

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username}: {self.amount} {self.currency}"
    
class Complaint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints', null=True, blank=True)
    issue = models.TextField()
    submitted_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, default='pending')
    response = models.TextField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username if self.user else 'Anonymous'}: {self.issue[:20]}..."