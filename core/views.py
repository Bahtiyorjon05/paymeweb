from django.shortcuts import render, redirect, get_object_or_404
from .forms import SignupForm, LoginForm, AddCardForm, AddMoneyForm, RemoveCardForm, SendMoneyToCardForm, SendMoneyToContactForm
from django.contrib import messages
from .models import User, Card, Transaction, Contact, Complaint
from django.contrib.auth import login, authenticate, logout
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum, Max, Min, Count, Func, Value, CharField, Case, When, Value, IntegerField
from decimal import Decimal
import phonenumbers
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from datetime import timedelta, datetime
import random
import requests
from django.views.decorators.csrf import csrf_exempt 
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from django.urls import reverse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models.functions import ExtractYear, ExtractMonth, ExtractDay, ExtractWeek, ExtractHour, Cast
import subprocess
import os
from django.http import StreamingHttpResponse

import socket

def home(request):
    return render(request, 'core/home.html')

def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.email = None
            user.save()
            messages.success(request, 'Signup successful! Please log in.')
            return redirect('login')
        else:
            messages.error(request, 'Signup failed! Please correct the errors below:')
    else:
        form = SignupForm()
    return render(request, 'core/signup.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        print(f"DEBUG: Login attempt for username: {request.POST.get('username')}")
        form = LoginForm(request.POST)
        if form.is_valid():
            print("DEBUG: Form is valid")
            username = form.cleaned_data['username']
            try:
                user = User.objects.get(username=username)
                print(f"DEBUG: User {username} found in DB")
                if user.block_until and user.block_until > timezone.now():
                    messages.error(request, f"You’re blocked until {user.block_until.strftime('%Y-%m-%d %H:%M:%S UTC')}! Please contact admin for help!")
                    return render(request, 'core/login.html', {'form': form})
                login(request, user)
                print("DEBUG: Login successful")
                user.last_activity = timezone.now()
                user.save()
                if user.two_factor_code:
                    request.session['pending_2fa_user'] = user.id
                    return redirect('verify_two_factor')
                messages.success(request, 'Login successful! Welcome back!')
                return redirect('dashboard')
            except User.DoesNotExist:
                print(f"DEBUG: User {username} DOES NOT EXIST (caught in try-except)")
                messages.error(request, "Username doesn’t exist!")
                return render(request, 'core/login.html', {'form': form})
        else:
            print(f"DEBUG: Form invalid. Errors: {form.errors}")
            
            # --- DEEP DEBUGGING START ---
            dbg_username = form.cleaned_data.get('username')
            dbg_password = form.cleaned_data.get('password')
            if dbg_username and dbg_password:
                try:
                    user_debug = User.objects.get(username=dbg_username)
                    print(f"DEBUG: Deep check for user '{dbg_username}'")
                    print(f"DEBUG: is_active: {user_debug.is_active}")
                    print(f"DEBUG: check_password() result: {user_debug.check_password(dbg_password)}")
                    print(f"DEBUG: DB Password hash: {user_debug.password}")
                except User.DoesNotExist:
                    print(f"DEBUG: User '{dbg_username}' not found in database.")
            # --- DEEP DEBUGGING END ---

            username = request.POST.get('username')
            try:
                user = User.objects.get(username=username)
                if user.block_until and user.block_until > timezone.now():
                    messages.error(request, f"You’re blocked until {user.block_until.strftime('%Y-%m-%d %H:%M:%S UTC')}! Please contact admin for help!")
                    return render(request, 'core/login.html', {'form': form})
                failed_attempts = request.session.get(f'user_attempts_{username}', 0) + 1
                request.session[f'user_attempts_{username}'] = failed_attempts
                if failed_attempts >= 3:
                    user.block_until = timezone.now() + timedelta(minutes=5)
                    user.save()
                    request.session[f'user_attempts_{username}'] = 0
                    messages.error(request, 'Account blocked for 5 minutes!')
                else:
                    messages.error(request, f'Wrong password! {3 - failed_attempts} left.')
            except User.DoesNotExist:
                messages.error(request, "Username doesn’t exist!")
            return render(request, 'core/login.html', {'form': form})
    else:
        form = LoginForm()
        storage = messages.get_messages(request)
        if storage:
            for _ in storage:
                pass
            storage.used = True
        return render(request, 'core/login.html', {'form': form})
    

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')
    pending_requests = Transaction.objects.filter(receiver=request.user, status='request')
    gender_emoji = '🧑'
    if hasattr(request.user, 'gender'):
        if request.user.gender == 'male':
            gender_emoji = '👦'
        elif request.user.gender == 'female':
            gender_emoji = '👧'

    return render(request, 'core/dashboard.html', {
        'user': request.user,
        'pending_requests': pending_requests,
        'gender_emoji': gender_emoji
    })

def add_card(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        form = AddCardForm(request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.user = request.user  # Tie to logged-in user
            card.save()
            messages.success(request, 'Card added successfully!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please fix the errors below:')
    else:
        form = AddCardForm()
    return render(request, 'core/add_card.html', {'form': form})


def view_cards(request):
    if not request.user.is_authenticated:
        messages.error(request, "Log in first, dude!")
        return redirect('login')
    
    cards = Card.objects.filter(user=request.user)
    return render(request, 'core/view_cards.html', {
        'cards': [{
            'card_number': card.card_number,
            'balance': f"{card.balance:.2f}",
            'currency': card.currency, 
        } for card in cards]
    })

def add_money(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Check if user has any cards before proceeding
    cards = Card.objects.filter(user=request.user)
    if not cards.exists():
        messages.error(request, "You don’t have any cards to add money! Add a card first! 💳")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AddMoneyForm(request.user, request.POST)
        if form.is_valid():
            card = form.cleaned_data['card']
            amount = form.cleaned_data['amount']
            card.balance += amount
            card.save()
            messages.success(request, f'Added {amount} {card.currency} to card {card.card_number}! 🎉')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please fix the errors below:')
    else:
        form = AddMoneyForm(user=request.user)  # Ensure user is passed here
    return render(request, 'core/add_money.html', {'form': form})

def remove_card(request):
    if not request.user.is_authenticated:
        return redirect('login')
    cards = Card.objects.filter(user=request.user)
    if not cards.exists():
        messages.error(request, "You don’t have any cards to remove. Add a card first! 💳")
        return redirect('dashboard')
    if request.method == 'POST':
        form = RemoveCardForm(request.user, request.POST)
        if form.is_valid():
            card = form.cleaned_data['card']
            password = form.cleaned_data['password']
            attempts = request.session.get('remove_attempts', 0)
            if card.password != password:
                attempts += 1
                request.session['remove_attempts'] = attempts
                if attempts >= 3:
                    messages.error(request, 'Too many incorrect attempts. Process canceled.')
                    request.session['remove_attempts'] = 0
                    return redirect('dashboard')
                messages.error(request, f'Incorrect password. {3 - attempts} attempts left.')
                return render(request, 'core/remove_card.html', {'form': form})
            # Password correct, ask for confirmation
            request.session['card_to_remove'] = card.id
            request.session['remove_attempts'] = 0
            return render(request, 'core/confirm_remove.html', {'card': card})
        else:
            messages.error(request, 'Please fix the errors below:')
    else:
        form = RemoveCardForm(user=request.user)
        request.session['remove_attempts'] = 0
    return render(request, 'core/remove_card.html', {'form': form})

def confirm_remove_card(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        card_id = request.POST.get('card_id')
        try:
            card = Card.objects.get(id=card_id, user=request.user)
            card.delete()
            messages.success(request, f'Card {card.card_number} removed successfully!')
        except Card.DoesNotExist:
            messages.error(request, 'Card not found!')
    return redirect('dashboard')

def send_money(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if not Card.objects.filter(user=request.user).exists() or not Card.objects.filter(user=request.user, balance__gt=0).exists():
        messages.error(request, "You don’t have any cards with a balance to send money.")
        return redirect('dashboard')
    return render(request, 'core/send_money.html')


def send_to_contact(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    contacts = Contact.objects.filter(user=request.user)
    if not contacts.exists():
        messages.error(request, "No contacts to send to. Add some first!")
        return redirect('manage_contacts')
    
    if request.method == 'POST':
        form = SendMoneyToContactForm(user=request.user, data=request.POST)
        if form.is_valid():
            receiver = form.cleaned_data['receiver']
            amount = form.cleaned_data['amount']
            sender_card = form.cleaned_data['sender_card']
            
            # Verify password
            attempts = request.session.get('send_contact_attempts', 0)
            password = request.POST.get('password', '')
            if sender_card.password != password:
                attempts += 1
                request.session['send_contact_attempts'] = attempts
                if attempts >= 3:
                    messages.error(request, 'Too many wrong attempts! Process canceled.')
                    request.session['send_contact_attempts'] = 0
                    return redirect('dashboard')
                messages.error(request, f'Incorrect password. {3 - attempts} attempts left.')
                return render(request, 'core/send_to_contact.html', {'form': form, 'contacts': contacts})
            
            # Correct password, reset attempts
            request.session['send_contact_attempts'] = 0
            
            if sender_card.balance < amount:
                messages.error(request, "Not enough balance on your card! 💸")
                return render(request, 'core/send_to_contact.html', {'form': form, 'contacts': contacts})
            
            # Fetch live rates vs sender’s currency
            sender_currency = sender_card.currency
            receiver_currency = receiver.contact_user.default_currency
            api_url = f"https://api.exchangerate-api.com/v4/latest/{sender_currency}"
            
            try:
                response = requests.get(api_url)
                data = response.json()
                
                if 'rates' in data:
                    rates = data['rates']
                    rate_to_receiver = Decimal(str(rates.get(receiver_currency, 1))) / Decimal(str(rates.get(sender_currency, 1)))
                    received_amount = amount * rate_to_receiver
                    
                    # Create transaction (pending)
                    transaction = Transaction.objects.create(
                        sender=request.user,
                        receiver=receiver.contact_user,
                        sender_card=sender_card,  # Link the sender's card
                        amount=amount,
                        currency=sender_currency,
                        received_amount=received_amount.quantize(Decimal('0.01')),
                        received_currency=receiver_currency,
                        status='pending'
                    )
                    
                    return redirect('confirm_send', transaction_id=transaction.id)
                else:
                    messages.error(request, "Couldn’t fetch rates! Try again! 😕")
            except Exception as e:
                messages.error(request, "Rate server’s down! Retry soon! 😬")
                print(f"Exception: {e}")
        else:
            messages.error(request, "Fix the form errors, dude! 😬")
    else:
        form = SendMoneyToContactForm(user=request.user)
        request.session['send_contact_attempts'] = 0  # Initialize attempts on GET
    
    return render(request, 'core/send_to_contact.html', {'form': form, 'contacts': contacts})

def send_to_card(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        form = SendMoneyToCardForm(request.user, request.POST)
        if form.is_valid():
            try:
                receiver_card = Card.objects.get(card_number=form.cleaned_data['receiver_card_number'])
                sender_card = form.cleaned_data['sender_card']
                amount = form.cleaned_data['amount']
                
                # Verify password
                attempts = request.session.get('send_attempts', 0)
                password = request.POST.get('password', '')
                if sender_card.password != password:
                    attempts += 1
                    request.session['send_attempts'] = attempts
                    if attempts >= 3:
                        messages.error(request, 'Too many wrong attempts! Process canceled.')
                        request.session['send_attempts'] = 0
                        return redirect('dashboard')
                    messages.error(request, f'Incorrect password. {3 - attempts} attempts left.')
                    return render(request, 'core/send_to_card.html', {'form': form})
                
                # Correct password, reset attempts
                request.session['send_attempts'] = 0
                
                # Fetch live rates vs sender’s currency
                sender_currency = sender_card.currency
                receiver_currency = receiver_card.currency
                api_url = f"https://api.exchangerate-api.com/v4/latest/{sender_currency}"
                try:
                    response = requests.get(api_url)
                    data = response.json()
                    if 'rates' in data:
                        rates = data['rates']
                        if sender_currency == receiver_currency:
                            received_amount = amount
                        else:
                            rate_to_receiver = Decimal(str(rates.get(receiver_currency, 1))) / Decimal(str(rates.get(sender_currency, 1)))
                            received_amount = amount * rate_to_receiver
                        
                        # Create transaction (pending)
                        transaction = Transaction.objects.create(
                            sender=request.user,
                            receiver=receiver_card.user,  # Link to receiver’s user
                            sender_card=sender_card,      # Link the sender's card
                            receiver_card=receiver_card,  # Link the receiver's card
                            amount=amount,
                            currency=sender_currency,
                            received_amount=received_amount.quantize(Decimal('0.01')),
                            received_currency=receiver_currency,
                            status='pending'
                        )
                        return redirect('confirm_send', transaction_id=transaction.id)
                    else:
                        messages.error(request, "Couldn’t fetch rates! Try again! 😕")
                except Exception as e:
                    messages.error(request, "Rate server’s down! Retry soon! 😬")
                    print(f"Exception: {e}")
                return render(request, 'core/send_to_card.html', {'form': form})
            except Card.DoesNotExist:
                messages.error(request, 'Receiver card not found!')
        else:
            messages.error(request, 'Please fix the errors below:')
    else:
        form = SendMoneyToCardForm(request.user)
    return render(request, 'core/send_to_card.html', {'form': form})

def confirm_send(request, transaction_id):
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Fetch the transaction
    try:
        transaction = Transaction.objects.get(id=transaction_id, sender=request.user, status='pending')
    except Transaction.DoesNotExist:
        messages.error(request, "Transaction not found or already processed!")
        return redirect('dashboard')
    
    # Retrieve the sender's card from the transaction
    sender_card = transaction.sender_card
    
    if request.method == 'POST':
        # Check if the sender has sufficient balance
        if sender_card.balance >= transaction.amount:
            # Pick receiver’s card (first available for simplicity)
            receiver_card = Card.objects.filter(user=transaction.receiver).first()
            if not receiver_card:
                messages.error(request, "Receiver has no card to receive money! 😬")
                return render(request, 'core/confirm_send.html', {'transaction': transaction})
            
            # Deduct from sender
            sender_card.balance -= transaction.amount
            sender_card.save()
            
            # Credit receiver with converted amount
            receiver_card.balance += transaction.received_amount
            receiver_card.currency = transaction.received_currency  # Sync currency
            receiver_card.save()
            
            # Complete transaction
            transaction.status = 'completed'
            transaction.save()
            
            messages.success(request, f"Sent {transaction.amount} {transaction.currency} → {transaction.received_amount} {transaction.received_currency} to {transaction.receiver.username}! 🎉")
            return redirect('dashboard')
        else:
            messages.error(request, "Not enough funds on your card! 💸")
    
    # Render the confirmation page
    return render(request, 'core/confirm_send.html', {'transaction': transaction})

def manage_contacts(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'core/manage_contacts.html')

def add_contact(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '')
        attempts = request.session.get('add_contact_attempts', 0)
        try:
            parsed_number = phonenumbers.parse(phone_number)
            if not phonenumbers.is_valid_number(parsed_number):
                raise phonenumbers.NumberParseException(0, "Invalid phone number!")
            try:
                contact_user = User.objects.get(phone_number=phone_number)
                if contact_user == request.user:
                    messages.error(request, "You can’t add yourself as a contact!")
                    return render(request, 'core/add_contact.html')
                if Contact.objects.filter(user=request.user, contact_user=contact_user).exists():
                    messages.error(request, "This contact already exists!")
                    return render(request, 'core/add_contact.html')
                request.session['add_contact_phone'] = phone_number
                request.session['add_contact_attempts'] = 0
                return render(request, 'core/confirm_add_contact.html', {
                    'contact_user': contact_user
                })
            except User.DoesNotExist:
                attempts += 1
                request.session['add_contact_attempts'] = attempts
                if attempts >= 3:
                    messages.error(request, "Too many incorrect attempts! Process canceled.")
                    request.session['add_contact_attempts'] = 0
                    return redirect('manage_contacts')
                else:
                    messages.error(request, f"User not found! {3 - attempts} attempts left.")
                    return render(request, 'core/add_contact.html')
        except phonenumbers.NumberParseException:
            attempts += 1
            request.session['add_contact_attempts'] = attempts
            if attempts >= 3:
                messages.error(request, "Too many incorrect attempts! Process canceled.")
                request.session['add_contact_attempts'] = 0
                return redirect('manage_contacts')
            else:
                messages.error(request, f"Invalid phone number! {3 - attempts} attempts left.")
                return render(request, 'core/add_contact.html')
    else:
        request.session['add_contact_attempts'] = 0
    return render(request, 'core/add_contact.html')

def confirm_add_contact(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '')
        try:
            contact_user = User.objects.get(phone_number=phone_number)
            Contact.objects.create(user=request.user, contact_user=contact_user)
            messages.success(request, f"Added {contact_user.first_name} {contact_user.last_name} as a contact!")
        except User.DoesNotExist:
            messages.error(request, "User not found!")
        return redirect('manage_contacts')
    return redirect('manage_contacts')

def remove_contact(request):
    if not request.user.is_authenticated:
        return redirect('login')
    contacts = Contact.objects.filter(user=request.user)
    if not contacts.exists():
        messages.error(request, "You don’t have any contacts to remove.")
        return redirect('manage_contacts')
    if request.method == 'POST':
        contact_id = request.POST.get('contact_id')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
            request.session['remove_contact_id'] = contact.id
            return render(request, 'core/confirm_remove_contact.html', {
                'contact': contact
            })
        except Contact.DoesNotExist:
            messages.error(request, "Contact not found!")
    return render(request, 'core/remove_contact.html', {'contacts': contacts})

def confirm_remove_contact(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        contact_id = request.POST.get('contact_id')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
            contact_name = f"{contact.contact_user.first_name} {contact.contact_user.last_name}"
            contact.delete()
            messages.success(request, f"Removed {contact_name} from your contacts!")
        except Contact.DoesNotExist:
            messages.error(request, "Contact not found!")
        return redirect('manage_contacts')
    return redirect('manage_contacts')

def view_contacts(request):
    if not request.user.is_authenticated:
        return redirect('login')
    contacts = Contact.objects.filter(user=request.user)
    return render(request, 'core/view_contacts.html', {'contacts': contacts})

def request_money(request):
    if not request.user.is_authenticated:
        return redirect('login')
    contacts = Contact.objects.filter(user=request.user)
    if not contacts.exists():
        messages.error(request, "You don’t have any contacts to request money from. Add some first!")
        return redirect('dashboard')
    if request.method == 'POST':
        contact_id = request.POST.get('contact_id')
        amount = request.POST.get('amount')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
            amount_decimal = Decimal(amount)
            if amount_decimal <= 0:
                messages.error(request, "Amount must be greater than zero!")
                return render(request, 'core/request_money.html', {'contacts': contacts})
            request.session['request_money_data'] = {
                'contact_id': contact.id,
                'amount': str(amount_decimal),
            }
            return render(request, 'core/confirm_request_money.html', {
                'contact': contact,
                'amount': amount_decimal
            })
        except Contact.DoesNotExist:
            messages.error(request, "Contact not found!")
        except ValueError:
            messages.error(request, "Please enter a valid amount!")
    return render(request, 'core/request_money.html', {'contacts': contacts})

def confirm_request_money(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        contact_id = request.POST.get('contact_id')
        amount = request.POST.get('amount')
        try:
            contact = Contact.objects.get(id=contact_id, user=request.user)
            amount_decimal = Decimal(amount)
        
            Transaction.objects.create(
                sender=request.user,  # Sender is the contact (who’ll pay)
                receiver=contact.contact_user,      # Receiver is the requester
                amount=amount_decimal,
                currency=request.user.default_currency,
                status='request'              # Custom status for pending request
            )
            messages.success(request, f"Requested {amount_decimal} {request.user.default_currency} from {contact.contact_user.first_name} {contact.contact_user.last_name}!")
            return redirect('dashboard')
        except Contact.DoesNotExist:
            messages.error(request, "Contact not found!")
        except ValueError:
            messages.error(request, "Invalid amount.")
    return redirect('dashboard')

def pay_request(request, transaction_id):
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        transaction = Transaction.objects.get(id=transaction_id, receiver=request.user, status='request')
    except Transaction.DoesNotExist:
        messages.error(request, "Request not found or not yours to pay!")
        return redirect('dashboard')
    
    # Fetch user’s cards and ensure they exist
    cards = Card.objects.filter(user=request.user)
    if not cards.exists():
        messages.error(request, "You don’t have any cards to pay with. Add one first! 💳")
        return redirect('add_card')

    if request.method == 'POST':
        card_id = request.POST.get('card_id')
        password = request.POST.get('password', '')

        # Validate card_id is legit
        if not card_id:
            messages.error(request, "Pick a card, dude! No sneaky stuff! 😬")
            return render(request, 'core/pay_request.html', {'transaction': transaction, 'cards': cards})
        
        try:
            sender_card = Card.objects.get(id=card_id, user=request.user)
        except Card.DoesNotExist:
            messages.error(request, "That card’s not yours or doesn’t exist! Stop messing around! 😡")
            return render(request, 'core/pay_request.html', {'transaction': transaction, 'cards': cards})

        # Password check with proper cancellation
        attempts = request.session.get('pay_request_attempts', 0)
        if sender_card.password != password:
            attempts += 1
            request.session['pay_request_attempts'] = attempts
            if attempts >= 3:
                messages.error(request, 'Too many wrong attempts! Process canceled. 😬')
                request.session['pay_request_attempts'] = 0
                return redirect('dashboard')
            messages.error(request, f'Incorrect password. {3 - attempts} attempts left.')
            return render(request, 'core/pay_request.html', {'transaction': transaction, 'cards': cards})
        
        # Correct password, reset attempts
        request.session['pay_request_attempts'] = 0

        # Use user’s default_currency for display, not hardcoded USD
        user_currency = request.user.default_currency
        
        # Basic balance check (detailed conversion happens in confirm)
        if sender_card.currency == transaction.currency and sender_card.balance < transaction.amount:
            messages.error(request, f"Not enough {sender_card.currency} on this card! Need {transaction.amount}!")
            return render(request, 'core/pay_request.html', {'transaction': transaction, 'cards': cards})
        elif sender_card.currency != transaction.currency:
            messages.info(request, f"Amount will convert from {transaction.currency} to your card’s {sender_card.currency}.")

        # Store data for confirmation
        request.session['pay_request_data'] = {
            'transaction_id': transaction.id,
            'card_id': sender_card.id
        }
        return render(request, 'core/confirm_pay_request.html', {
            'transaction': transaction,
            'sender_card': sender_card,
            'user_currency': user_currency  # Pass for display
        })
    else:
        # Reset attempts on GET
        request.session['pay_request_attempts'] = 0
    
    # Pass user’s default currency to template on GET
    return render(request, 'core/pay_request.html', {
        'transaction': transaction,
        'cards': cards,
        'user_currency': request.user.default_currency
    })


def confirm_pay_request(request):
    if not request.user.is_authenticated:
        return redirect('login')

    pay_data = request.session.get('pay_request_data')
    if not pay_data:
        messages.error(request, "Invalid payment data. Start over, dude! 😬")
        return redirect('dashboard')

    try:
        transaction = Transaction.objects.get(id=pay_data['transaction_id'], receiver=request.user, status='request')
        sender_card = Card.objects.get(id=pay_data['card_id'], user=request.user)
        receiver_card = Card.objects.filter(user=transaction.sender).first()
    except (Transaction.DoesNotExist, Card.DoesNotExist):
        messages.error(request, "Transaction or card not found. Something’s fishy! 😡")
        return redirect('dashboard')

    if request.method == 'POST':
        if not receiver_card:
            messages.error(request, "The requester has no card to receive money!")
            return redirect('dashboard')

        # Fetch live exchange rates
        sender_currency = sender_card.currency
        receiver_currency = receiver_card.currency
        requested_currency = transaction.currency
        api_url = f"https://api.exchangerate-api.com/v4/latest/{requested_currency}"
        try:
            response = requests.get(api_url)
            data = response.json()
            if 'rates' not in data:
                messages.error(request, "Couldn’t fetch rates! Try again! 😕")
                return redirect('dashboard')
            rates = data['rates']

            # Sender’s amount
            if sender_currency == requested_currency:
                amount_to_deduct = transaction.amount
            else:
                rate_to_sender = Decimal(str(rates.get(sender_currency, 1))) / Decimal(str(rates.get(requested_currency, 1)))
                amount_to_deduct = transaction.amount * rate_to_sender

            # Receiver’s amount
            if receiver_currency == requested_currency:
                received_amount = transaction.amount
            else:
                rate_to_receiver = Decimal(str(rates.get(receiver_currency, 1))) / Decimal(str(rates.get(requested_currency, 1)))
                received_amount = transaction.amount * rate_to_receiver

            if sender_card.balance < amount_to_deduct:
                messages.error(request, f"Insufficient balance! Need {amount_to_deduct} {sender_currency}.")
                return redirect('dashboard')

            # Process the transaction
            sender_card.balance -= amount_to_deduct
            receiver_card.balance += received_amount.quantize(Decimal('0.01'))
            sender_card.save()
            receiver_card.save()

            # Update transaction
            transaction.sender_card = sender_card
            transaction.receiver_card = receiver_card
            transaction.amount = amount_to_deduct
            transaction.currency = sender_currency
            transaction.received_amount = received_amount
            transaction.received_currency = receiver_currency
            transaction.status = 'completed'
            transaction.save()

            messages.success(request, f"Paid {amount_to_deduct} {sender_currency} → {received_amount} {receiver_currency} to {transaction.sender.first_name} {transaction.sender.last_name}! 🎉")
            del request.session['pay_request_data']
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, "Rate server’s down or something broke! Retry soon! 😬")
            print(f"Exception: {e}")
            return redirect('dashboard')

    else:  # GET request - show confirmation page
        if not receiver_card:
            messages.error(request, "The requester has no card to receive money!")
            return redirect('dashboard')

        # Pre-calculate amounts for display
        sender_currency = sender_card.currency
        receiver_currency = receiver_card.currency
        requested_currency = transaction.currency
        api_url = f"https://api.exchangerate-api.com/v4/latest/{requested_currency}"
        try:
            response = requests.get(api_url)
            data = response.json()
            if 'rates' not in data:
                messages.error(request, "Couldn’t fetch rates! Try again! 😕")
                return redirect('dashboard')
            rates = data['rates']

            # Sender’s amount
            if sender_currency == requested_currency:
                amount_to_deduct = transaction.amount
            else:
                rate_to_sender = Decimal(str(rates.get(sender_currency, 1))) / Decimal(str(rates.get(requested_currency, 1)))
                amount_to_deduct = transaction.amount * rate_to_sender

            # Receiver’s amount
            if receiver_currency == requested_currency:
                received_amount = transaction.amount
            else:
                rate_to_receiver = Decimal(str(rates.get(receiver_currency, 1))) / Decimal(str(rates.get(requested_currency, 1)))
                received_amount = transaction.amount * rate_to_receiver

            if sender_card.balance < amount_to_deduct:
                messages.error(request, f"Insufficient balance! Need {amount_to_deduct} {sender_currency}.")
                return redirect('dashboard')

            return render(request, 'core/confirm_pay_request.html', {
                'transaction': transaction,
                'sender_card': sender_card,
                'user_currency': request.user.default_currency,
                'amount_to_deduct': amount_to_deduct.quantize(Decimal('0.01')),
                'received_amount': received_amount.quantize(Decimal('0.01')),
                'receiver_currency': receiver_currency
            })

        except Exception as e:
            messages.error(request, "Rate server’s down! Retry soon! 😬")
            print(f"Exception: {e}")
            return redirect('dashboard')
        
def cancel_request(request, transaction_id):
    if not request.user.is_authenticated:
        return redirect('login')
    try:
        transaction = Transaction.objects.get(id=transaction_id, receiver=request.user, status='request')
    except Transaction.DoesNotExist:
        messages.error(request, "Request not found or not yours to cancel.")
        return redirect('dashboard')
    if request.method == 'POST':
        transaction.delete()
        messages.success(request, f"Cancelled request from {transaction.sender.first_name} {transaction.sender.last_name} for {transaction.amount} {transaction.currency}!")
        return redirect('dashboard')
    return render(request, 'core/confirm_cancel_request.html', {'transaction': transaction})

def manage_transactions(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'sort_transactions':
            sort_by = request.POST.get('sort_by', 'date_desc')
            transactions = Transaction.objects.filter(
                Q(sender=request.user) | Q(receiver=request.user)
            )
            if sort_by == 'date_asc':
                transactions = transactions.order_by('timestamp')
            elif sort_by == 'date_desc':
                transactions = transactions.order_by('-timestamp')
            elif sort_by == 'amount_asc':
                transactions = transactions.order_by('amount')
            elif sort_by == 'amount_desc':
                transactions = transactions.order_by('-amount')
            return render(request, 'core/sort_transactions.html', {'transactions': transactions, 'sort_by': sort_by})
        elif action == 'download_transactions':
            date_filter = request.POST.get('date_filter', 'all')
            transactions = Transaction.objects.filter(
                Q(sender=request.user) | Q(receiver=request.user)
            )
            if date_filter != 'all':
                try:
                    date = datetime.strptime(date_filter, '%Y-%m-%d')
                    transactions = transactions.filter(timestamp__date=date)
                except ValueError:
                    messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
                    return render(request, 'core/manage_transactions.html')
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            p.setFont("Helvetica", 12)
            p.drawString(100, 750, f"Transaction History for {request.user.first_name} {request.user.last_name}")
            y = 730
            for tx in transactions:
                line = f"{tx.timestamp.strftime('%Y-%m-%d %H:%M')} | {tx.sender.first_name} {tx.sender.last_name} -> {tx.receiver.first_name} {tx.receiver.last_name} | {tx.amount} {tx.currency} | {tx.status}"
                p.drawString(50, y, line)
                y -= 20
                if y < 50:
                    p.showPage()
                    y = 750
            p.showPage()
            p.save()
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="transactions_{request.user.username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
            return response
        elif action == 'generate_report':
            transactions = Transaction.objects.filter(
                Q(sender=request.user) | Q(receiver=request.user)
            )
            total_sent = transactions.filter(sender=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
            total_received = transactions.filter(receiver=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
            request_count = transactions.filter(status='request').count()
            now = timezone.now()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_txs = transactions.filter(timestamp__gte=month_start)
            highest_spend = month_txs.filter(sender=request.user).order_by('-amount').first()
            highest_spend_person = highest_spend.receiver.first_name + " " + highest_spend.receiver.last_name if highest_spend else "N/A"
            highest_spend_amount = highest_spend.amount if highest_spend else 0
            least_spend = month_txs.filter(sender=request.user).order_by('amount').first()
            least_spend_person = least_spend.receiver.first_name + " " + least_spend.receiver.last_name if least_spend else "N/A"
            least_spend_amount = least_spend.amount if least_spend else 0
            tips = [
                "Send more requests to keep the cash flowing!",
                "Watch your spending—small savings add up big!",
                "Download your history monthly to track trends!",
                "Mix it up—send to new contacts for variety!",
                "Got a big spend? Plan ahead next time!",
                "Requests are your friend—don’t be shy!",
                "Check your highest spends—any surprises?",
                "Low spends? You’re a saver—nice work!",
                "Share the wealth—send a little love today!",
                "Stay active—keep those transactions rolling!"
            ]
            tip = random.choice(tips)
            return render(request, 'core/generate_report.html', {
                'total_sent': total_sent,
                'total_received': total_received,
                'request_count': request_count,
                'highest_spend_person': highest_spend_person,
                'highest_spend_amount': highest_spend_amount,
                'least_spend_person': least_spend_person,
                'least_spend_amount': least_spend_amount,
                'tip': tip,
                'currency': request.user.default_currency,
                'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M')
            })
        elif action == 'download_report':
            messages.info(request, "Download Report should be triggered from the report page!")
    return render(request, 'core/manage_transactions.html')

def download_report(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        transactions = Transaction.objects.filter(
            Q(sender=request.user) | Q(receiver=request.user)
        )
        total_sent = transactions.filter(sender=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
        total_received = transactions.filter(receiver=request.user).aggregate(Sum('amount'))['amount__sum'] or 0
        request_count = transactions.filter(status='request').count()
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_txs = transactions.filter(timestamp__gte=month_start)
        highest_spend = month_txs.filter(sender=request.user).order_by('-amount').first()
        highest_spend_person = highest_spend.receiver.first_name + " " + highest_spend.receiver.last_name if highest_spend else "N/A"
        highest_spend_amount = highest_spend.amount if highest_spend else 0
        least_spend = month_txs.filter(sender=request.user).order_by('amount').first()
        least_spend_person = least_spend.receiver.first_name + " " + least_spend.receiver.last_name if least_spend else "N/A"
        least_spend_amount = least_spend.amount if least_spend else 0
        tips = [
            "Send more requests to keep the cash flowing!",
            "Watch your spending—small savings add up big!",
            "Download your history monthly to track trends!",
            "Mix it up—send to new contacts for variety!",
            "Got a big spend? Plan ahead next time!",
            "Requests are your friend—don’t be shy!",
            "Check your highest spends—any surprises?",
            "Low spends? You’re a saver—nice work!",
            "Share the wealth—send a little love today!",
            "Stay active—keep those transactions rolling!"
        ]
        tip = random.choice(tips)
        
        # Generate PDF
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(100, 750, f"Payme Transaction Report for {request.user.first_name} {request.user.last_name}")
        p.setFont("Helvetica", 12)
        p.drawString(100, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        p.drawString(100, 710, f"Total Sent: {total_sent} {request.user.default_currency}")
        p.drawString(100, 690, f"Total Received: {total_received} {request.user.default_currency}")
        p.drawString(100, 670, f"Pending Requests: {request_count}")
        p.drawString(100, 650, f"This Month’s Highest Spend: {highest_spend_amount} {request.user.default_currency} to {highest_spend_person}")
        p.drawString(100, 630, f"This Month’s Least Spend: {least_spend_amount} {request.user.default_currency} to {least_spend_person}")
        p.drawString(100, 610, "Creative Tip:")
        p.drawString(120, 590, tip)
        p.showPage()
        p.save()
        buffer.seek(0)
        
        # Serve PDF
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report_{request.user.username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        return response
    return redirect('manage_transactions')

def view_profile(request):
    if not request.user.is_authenticated:
        return redirect('login')
    card_count = Card.objects.filter(user=request.user).count()
    gender_emoji = '🧑'
    if hasattr(request.user, 'gender'):
        gender = getattr(request.user, 'gender', '')
        if request.user.gender == 'male':
            gender_emoji = '👦'
        elif request.user.gender == 'female':
            gender_emoji = '👧'

    return render(request, 'core/view_profile.html', {
        'user': request.user,
        'card_count': card_count,
        'gender_emoji': gender_emoji
    })

def edit_profile(request):
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method == 'POST':
        field = request.POST.get('field')
        new_value = request.POST.get('new_value', '').strip()
        current_password = request.POST.get('current_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        if not field:
            messages.error(request, "Please select a field to edit! 😕")
            return render(request, 'core/edit_profile.html')

        user = request.user

        # Handle Password Change
        if field == 'password':
            if not current_password:
                messages.error(request, "Enter your current password to proceed! 🔐")
                return render(request, 'core/edit_profile.html', {'show_password_form': True})
            if not user.check_password(current_password):
                messages.error(request, "Wrong current password! Try again! 😬")
                return render(request, 'core/edit_profile.html', {'show_password_form': True})
            if not new_password or not confirm_password:
                messages.error(request, "Enter your new password twice! ✍️")
                return render(request, 'core/edit_profile.html', {'show_password_form': True})
            if new_password != confirm_password:
                messages.error(request, "New passwords don’t match! Double-check! 😩")
                return render(request, 'core/edit_profile.html', {'show_password_form': True})
            if user.check_password(new_password):
                messages.error(request, "That’s your current password! Try a new one! 🤔")
                return render(request, 'core/edit_profile.html', {'show_password_form': True})

            # Set new password
            user.set_password(new_password)
            user.save()
            messages.success(request, "Password updated successfully! 🎉 Login with your new one next time!")
            return redirect('login')

        # Handle Other Fields
        if not new_value:
            messages.error(request, "Enter a new value, champ! ✍️")
            return render(request, 'core/edit_profile.html')

        current_value = getattr(user, field, None)
        if str(current_value) == new_value:
            messages.error(request, f"That’s already your {field.replace('_', ' ')}! 🤔")
            return render(request, 'core/edit_profile.html')

        # Validate & Update Age
        if field == 'age':
            try:
                new_age = int(new_value)
                if new_age < 13 or new_age > 120:
                    messages.error(request, "Age must be between 13 and 120! 😬")
                    return render(request, 'core/edit_profile.html')
                user.age = new_age
                user.save()
                messages.success(request, f"Updated age to {new_age}! 🎉")
                return render(request, 'core/edit_profile.html')
            except ValueError:
                messages.error(request, "Invalid age! Enter a number! 😬")
                return render(request, 'core/edit_profile.html')

        # Validate & Update Username
        if field == 'username':
            if User.objects.filter(username=new_value).exclude(id=user.id).exists():
                messages.error(request, "Username taken! Try another! 😩")
            else:
                user.username = new_value
                user.save()
                messages.success(request, f"Updated username to '{new_value}'! 🎉")
            return render(request, 'core/edit_profile.html')

        # Validate & Update Phone Number
        if field == 'phone_number':
            try:
                parsed = phonenumbers.parse(new_value, None)
                if not phonenumbers.is_valid_number(parsed):
                    messages.error(request, "Invalid phone number! Check it! 📵")
                else:
                    formatted_phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    if User.objects.filter(phone_number=formatted_phone).exclude(id=user.id).exists():
                        messages.error(request, "Phone number taken! Try another! 😩")
                    else:
                        user.phone_number = formatted_phone
                        user.save()
                        messages.success(request, f"Updated phone number to '{formatted_phone}'! 🎉")
                return render(request, 'core/edit_profile.html')
            except phonenumbers.NumberParseException:
                messages.error(request, "Invalid phone number! Try again! 📵")
                return render(request, 'core/edit_profile.html')

        # Handle First Name & Last Name
        if field in ['first_name', 'last_name']:
            setattr(user, field, new_value)
            user.save()
            messages.success(request, f"Updated {field.replace('_', ' ')} to '{new_value}'! 🎉")
            return render(request, 'core/edit_profile.html')

    return render(request, 'core/edit_profile.html')


def manage_currency(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    user = request.user
    default_currency = user.default_currency
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'live_rates':
            base_currency = request.POST.get('base_currency', default_currency)
            api_url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
            try:
                response = requests.get(api_url)
                data = response.json()
                if 'rates' in data:
                    rates = {
                        'UZS': data['rates'].get('UZS', 0),
                        'RUB': data['rates'].get('RUB', 0),
                        'USD': data['rates'].get('USD', 0),
                        'KRW': data['rates'].get('KRW', 0),
                        'EUR': data['rates'].get('EUR', 0)
                    }
                    print(f"Live Rates vs {base_currency}: {rates}")
                    return render(request, 'core/manage_currency.html', {
                        'rates': rates,
                        'base_currency': base_currency,
                        'default_currency': default_currency
                    })
                else:
                    messages.error(request, "Couldn’t snag those rates! Try again! 😕")
                    print(f"Live rates failed: {data}")
            except Exception as e:
                messages.error(request, "Rate server’s taking a nap! Retry soon! 😬")
                print(f"Live rates exception: {e}")
        
        elif action == 'select_currency':
            selected_currency = request.POST.get('base_currency', '').strip()  # Ensure empty string handling
            if not selected_currency:  # Check if no currency is selected
                messages.error(request, "Please choose one currency! 😕")
            elif selected_currency != default_currency:
                # Fetch rates vs old currency to convert to new
                api_url = f"https://api.exchangerate-api.com/v4/latest/{default_currency}"
                try:
                    response = requests.get(api_url)
                    data = response.json()
                    if 'rates' in data:
                        rates = data['rates']
                        print(f"Rates vs {default_currency}: {rates}")
                        for card in user.cards.all():
                            old_amount = card.balance
                            old_currency = card.currency
                            print(f"Card {card.card_number}: {old_amount} {old_currency}")
                            if old_currency == selected_currency:
                                new_amount = old_amount
                            else:
                                # Convert old currency to new currency
                                rate_to_new = Decimal(str(rates.get(selected_currency, 1))) / Decimal(str(rates.get(old_currency, 1)))
                                new_amount = old_amount * rate_to_new
                                print(f"Rate {old_currency} to {selected_currency}: {rate_to_new}")
                            print(f"Converted to {selected_currency}: {new_amount}")
                            if new_amount > Decimal('9999999999999.99'):
                                messages.error(request, f"Amount too big for {card.card_number}! Cap it, bro! 😬")
                            else:
                                card.balance = new_amount.quantize(Decimal('0.01'))
                                card.currency = selected_currency
                                card.save()
                                print(f"Saved: {card.balance} {card.currency}")
                    
                    user.default_currency = selected_currency
                    user.save()
                    messages.success(request, f"Default currency set to {selected_currency}! Cards updated! 🎉")
                except Exception as e:
                    messages.error(request, f"Conversion crashed! Retry soon! 😬 ({str(e)})")
                    print(f"Exception: {e}")
                    return render(request, 'core/manage_currency.html', {'default_currency': default_currency})
            else:
                messages.info(request, f"{selected_currency} is already your default! 😕")
            return render(request, 'core/manage_currency.html', {'default_currency': user.default_currency})
    
    return render(request, 'core/manage_currency.html', {'default_currency': default_currency})

def security_settings(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'core/security_settings.html', {'two_factor_enabled': bool(request.user.two_factor_code)})

def enable_two_factor(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.user.two_factor_code:
        messages.error(request, "Already enabled ✅")
        return render(request, 'core/security_settings.html', {'two_factor_enabled': True})
    
    if request.method == 'POST':
        step = request.POST.get('step')
        if step == 'email':  # Step 1: Ask for email
            email = request.POST.get('email')
            if not email:
                messages.error(request, "Gimme an email! 📧")
                return render(request, 'core/enable_two_factor.html', {'step': 'email'})
            request.session['two_factor_email'] = email
            code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            request.session['two_factor_verification_code'] = code
            try:
                send_mail(
                    'Your Payme 2FA Code',
                    f"Hey {request.user.username},\n\nYour 2FA code is: {code}\n\nStay secure!",
                    'your_email@gmail.com',  # Your Gmail
                    [email],
                    fail_silently=False,
                )
                print(f"Sent 2FA code {code} to {email}")
            except Exception as e:
                messages.error(request, "Email failed! Check console for code! 😬")
                print(f"Email Error: {e} - Code: {code}")
            return render(request, 'core/enable_two_factor.html', {'step': 'verify', 'email': email})
        
        elif step == 'verify':  # Step 2: Verify code
            code = request.POST.get('code')
            session_code = request.session.get('two_factor_verification_code')
            if code == session_code:
                return render(request, 'core/enable_two_factor.html', {'step': 'set_password'})
            else:
                messages.error(request, "Wrong code! Check your email! 😬")
                return render(request, 'core/enable_two_factor.html', {'step': 'verify', 'email': request.session['two_factor_email']})
        
        elif step == 'set_password':  # Step 3: Set 2FA password
            password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            if password and confirm_password and password == confirm_password:
                if len(password) < 6:
                    messages.error(request, "Password needs 6+ chars, dude! 😬")
                else:
                    request.user.two_factor_code = password
                    if not request.user.email:
                        request.user.email = request.session['two_factor_email']
                    request.user.save()
                    del request.session['two_factor_verification_code']
                    del request.session['two_factor_email']
                    messages.success(request, "2FA enabled! You’re locked down! 🔒")
                    return redirect('security_settings')
            else:
                messages.error(request, "Passwords don’t match or empty! 😬")
            return render(request, 'core/enable_two_factor.html', {'step': 'set_password'})
    
    return render(request, 'core/enable_two_factor.html', {'step': 'email'})

def disable_two_factor(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.method == 'POST':
        if request.user.two_factor_code:
            request.user.two_factor_code = None
            request.user.save()
            messages.success(request, "2FA disabled! Back to basics! 🎉")
        else:
            messages.info(request, "2FA wasn’t even on, buddy!")
        return redirect('security_settings')
    return render(request, 'core/disable_two_factor.html')


def verify_two_factor(request):
    if not request.session.get('pending_2fa_user'):
        return redirect('login')
    
    user = User.objects.get(id=request.session['pending_2fa_user'])
    if request.method == 'POST':
        code = request.POST.get('code')
        if code == user.two_factor_code:
            del request.session['pending_2fa_user']
            messages.success(request, "2FA verified! Welcome back! 🎉")
            return redirect('dashboard')
        else:
            messages.error(request, "Wrong 2FA code! Try again! 😬")
    return render(request, 'core/verify_two_factor.html', {'phone_number': user.phone_number})


def delete_account(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.method == 'POST':
        step = request.POST.get('step')
        if step == 'confirm':  # First POST: Yes clicked
            return render(request, 'core/delete_account_confirm.html')
        elif step == 'delete':  # Second POST: Word check
            confirmation = request.POST.get('confirmation')
            if confirmation == 'deletemyaccount':
                user = request.user
                logout(request)  # End session
                user.delete()    # Wipe user, cascades to related models
                messages.success(request, "Account deleted forever! Catch ya later! 👋")
                return redirect('login')
            else:
                messages.error(request, "Wrong word! Type 'deletemyaccount' exactly! 😬")
                return render(request, 'core/delete_account_confirm.html')
        else:  # No/Cancel
            messages.info(request, "Deletion canceled! You’re still in the game!")
            return redirect('dashboard')
    return render(request, 'core/delete_account.html')


def forgot_password(request):
    if request.method == 'POST':
        step = request.POST.get('step')

        if step == 'phone':  # Step 1: Check phone number
            phone = request.POST.get('phone_number')
            try:
                user = User.objects.get(phone_number=phone)
                request.session['reset_phone'] = phone
                return render(request, 'core/forgot_password.html', {'step': 'email'})
            except User.DoesNotExist:
                messages.error(request, "No user with that phone number, bro! 📱")
                return render(request, 'core/forgot_password.html', {'step': 'phone'})

        elif step == 'email':  # Step 2: Send code to email
            email = request.POST.get('email')
            if not email:
                messages.error(request, "Enter your email, dude! 📧")
                return render(request, 'core/forgot_password.html', {'step': 'email'})
            reset_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            request.session['reset_email'] = email
            request.session['reset_code'] = reset_code
            try:
                # Force IPv4 for Gmail in Docker
                orig_getaddrinfo = socket.getaddrinfo
                def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
                    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
                
                socket.getaddrinfo = getaddrinfo_ipv4
                try:
                    from django.core.mail import get_connection, EmailMessage
                    connection = get_connection(timeout=10)
                    email_msg = EmailMessage(
                        'Your Payme Password Reset Code',
                        f"Hey,\n\nForgot your password? Here’s your reset code: {reset_code}\n\nUse it quick, buddy!",
                        settings.EMAIL_HOST_USER or 'noreply@paymebot.com',
                        [email],
                        connection=connection
                    )
                    email_msg.send(fail_silently=False)
                finally:
                    socket.getaddrinfo = orig_getaddrinfo
                
                print(f"Sent reset code {reset_code} to {email}")
                messages.success(request, "Check your email for the code! 📩")
                return render(request, 'core/forgot_password.html', {'step': 'verify'})
            except Exception as e:
                messages.error(request, "Email failed! Check console for code! 😬")
                print(f"Email Error: {e} - Code: {reset_code}")
                return render(request, 'core/forgot_password.html', {'step': 'verify'})

        elif step == 'verify':  # Step 3: Check reset code
            code = request.POST.get('code')
            if code == request.session.get('reset_code'):
                return render(request, 'core/forgot_password.html', {'step': 'reset'})
            else:
                messages.error(request, "Wrong code! Check your email! 😬")
                return render(request, 'core/forgot_password.html', {'step': 'verify'})

        elif step == 'reset':  # Step 4: Set new password
            password = request.POST.get('password')
            confirm_password = request.POST.get('confirm_password')
            if password and confirm_password and password == confirm_password:
                if len(password) < 6:
                    messages.error(request, "Password needs 6+ chars, dude! 🔑")
                else:
                    phone = request.session.get('reset_phone')
                    user = User.objects.get(phone_number=phone)
                    user.password = make_password(password)  # Hash it
                    user.save()
                    del request.session['reset_phone']
                    del request.session['reset_email']
                    del request.session['reset_code']
                    messages.success(request, "Password reset! Log in now! 🎉")
                    return redirect('login')
            else:
                messages.error(request, "Passwords don’t match or empty! 😬")
            return render(request, 'core/forgot_password.html', {'step': 'reset'})

    return render(request, 'core/forgot_password.html', {'step': 'phone'})



def help_faq(request):
    return render(request, 'core/help_faq.html')

def contact_support(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        if name and email and message:
            # Save to Complaint (anonymous if not logged in)
            user = request.user if request.user.is_authenticated else None
            complaint = Complaint.objects.create(
                user=user,  # Can be None if model updated
                issue=f"Contact Query - Name: {name}, Email: {email}\nMessage: {message}"
            )
            # Notify admin via email
            try:
                send_mail(
                    'New Contact Query on Payme',
                    f"New query from {name} ({email}):\n{message}\nComplaint ID: {complaint.id}",
                    'paymebot7@gmail.com',  # From your email
                    ['paymebot7@gmail.com'],  # To admin
                    fail_silently=False,
                )
                messages.success(request, "Message sent! We’ll get back to you soon! 🎉")
            except Exception as e:
                messages.error(request, "Message sent but email failed! We’ll still respond. 😬")
                print(f"Email Error: {e}")
            return render(request, 'core/contact_support.html')
        else:
            messages.error(request, "Fill all fields, dude! 😬")
    return render(request, 'core/contact_support.html')


def report_issue(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        issue = request.POST.get('issue')
        if name and email and issue:  # All required
            user = request.user if request.user.is_authenticated else None
            complaint = Complaint.objects.create(
                user=user,
                issue=f"Report Issue - Name: {name}, Email: {email}\nIssue: {issue}"
            )
            # Notify admin via email
            try:
                send_mail(
                    'New Report Issue on Payme',
                    f"New report from {name} ({email}):\n{issue}\nComplaint ID: {complaint.id}",
                    'paymebot7@gmail.com',  # From your email
                    ['paymebot7@gmail.com'],  # To admin
                    fail_silently=False,
                )
                messages.success(request, "Issue reported! We’ll reach out to you soon! 🎉")
            except Exception as e:
                messages.error(request, "Issue reported but email failed! We’ll still respond. 😬")
                print(f"Email Error: {e}")
            return render(request, 'core/report_issue.html')  # Stay on page
        else:
            if not name and not email and not issue:
                messages.error(request, "Enter your name, email, and issue, dude! 😬")
            elif not name:
                messages.error(request, "Name is required! 😬")
            elif not email:
                messages.error(request, "Email is required to reach you, dude! 😬")
            elif not issue:
                messages.error(request, "Enter an issue, dude! 😬")
    return render(request, 'core/report_issue.html')

def currency_converter(request):
    # Fetch all available currencies from API
    api_url = "https://api.exchangerate-api.com/v4/latest/USD"  # Any base works for list
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        all_currencies = sorted(response.json().get('rates', {}).keys())
    except requests.RequestException as e:
        messages.error(request, "Can’t load currencies! Check back later! 😬")
        print(f"Error fetching currencies: {e}")
        all_currencies = ['USD', 'EUR', 'GBP']  # Fallback list

    if request.method == 'POST':
        base_currency = request.POST.get('base_currency', 'USD')
        target_currencies = request.POST.getlist('target_currencies')  # Multi-select
        convert_all = 'convert_all' in request.POST  # Check for "Convert to All" button

        if not target_currencies and not convert_all:
            messages.error(request, "Pick at least one currency or convert to all!")
            return render(request, 'core/currency_converter.html', {
                'all_currencies': all_currencies,
                'base_currency': base_currency,
            })

        if convert_all:
            target_currencies = all_currencies  # Convert to all currencies for rates
            # Reset target_currencies to empty for template rendering after conversion
            post_convert_targets = []  # Empty list to unselect checkboxes
        else:
            post_convert_targets = target_currencies  # Keep selected for regular conversion

        api_url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            if 'rates' in data:
                rates = {currency: data['rates'].get(currency, 'N/A') for currency in target_currencies}
                if not rates or all(value == 'N/A' for value in rates.values()):
                    messages.error(request, "No valid rates found! Try again! 😕")
                    return render(request, 'core/currency_converter.html', {
                        'all_currencies': all_currencies,
                        'base_currency': base_currency,
                        'target_currencies': post_convert_targets,
                    })
                return render(request, 'core/currency_converter.html', {
                    'all_currencies': all_currencies,
                    'base_currency': base_currency,
                    'target_currencies': post_convert_targets,  # Use empty list after "Convert to All"
                    'rates': rates
                })
            else:
                messages.error(request, "No rates found! Try again! 😕")
        except requests.RequestException as e:
            messages.error(request, "Rate server’s down! Retry soon! 😬")
            print(f"Error fetching rates: {e}")

    return render(request, 'core/currency_converter.html', {
        'all_currencies': all_currencies,
        'base_currency': 'USD'
    })
################################################

# Admin Views
from django.contrib.auth.hashers import check_password
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
import logging

logger = logging.getLogger(__name__)

def admin_login(request):
    if request.method == 'GET':
        if 'is_admin' in request.session and not request.session.get('_fresh_login', False):
            del request.session['is_admin']
        storage = messages.get_messages(request)
        for _ in storage:
            pass
        storage.used = True
        return render(request, 'core/admin_login.html')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        storage = messages.get_messages(request)
        for _ in storage:
            pass
        storage.used = True

        logger.info(f"Username entered: {username}, Expected: {settings.ADMIN_USERNAME}")
        logger.info(f"ADMIN_PASSWORD_HASH: {settings.ADMIN_PASSWORD_HASH}")

        # Use the hash from settings
        admin_password_hash = settings.ADMIN_PASSWORD_HASH
        if not admin_password_hash:
            logger.error("ADMIN_PASSWORD_HASH is not set in settings")
            messages.error(request, "Configuration error: Admin password hash not set")
            return render(request, 'core/admin_login.html')

        try:
            if username == settings.ADMIN_USERNAME and check_password(password, admin_password_hash):
                request.session.flush()
                request.session['is_admin'] = True
                request.session['_fresh_login'] = True
                messages.success(request, "Welcome, boss! You're in! 😎")
                return redirect('admin_dashboard')
            else:
                messages.error(request, "Wrong creds, dude! Try again!")
                return render(request, 'core/admin_login.html')
        except ValueError as e:
            logger.error(f"Hash error: {str(e)}, Hash value: {admin_password_hash}")
            messages.error(request, f"Config error: {str(e)}. Fix your setup, boy!")
            return render(request, 'core/admin_login.html')

    return render(request, 'core/admin_login.html')

def admin_dashboard(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    if request.session.get('_fresh_login', False):
        del request.session['_fresh_login']

    storage = messages.get_messages(request)
    for _ in storage:
        pass
    storage.used = True

    admin_options = [
        {'name': 'Manage Users', 'url': 'manage_users', 'emoji': '👤'},
        {'name': 'Manage Cards', 'url': 'manage_cards', 'emoji': '💳'},
        {'name': 'Manage Transactions', 'url': 'admin_manage_transactions', 'emoji': '💸'},
        {'name': 'Generate Report', 'url': 'admin_report', 'emoji': '📊'},
        {'name': 'View Complaints', 'url': 'view_complaints', 'emoji': '📩'},
        {'name': 'Backup Database', 'url': 'backup_database', 'emoji': '💾'},
        {'name': 'Logout', 'url': 'admin_logout', 'emoji': '🚪'},
    ]
    
    return render(request, 'core/admin_dashboard.html', {'admin_options': admin_options})

def manage_users(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')
    
    if request.method == 'GET':
        manage_users_options = [
            {'name': 'View All Users', 'url': 'view_all_users', 'emoji': '👀', 'action': 'view_all_users'},
            {'name': 'Sort Users', 'url': '#', 'emoji': '🔄', 'action': 'sort_users'},
            {'name': 'Search User', 'url': '#', 'emoji': '🔍', 'action': 'search_user'},
            {'name': 'Remove User', 'url': '#', 'emoji': '🗑️', 'action': 'remove_user'},
            {'name': 'View Blocked Users', 'url': '#', 'emoji': '🔴', 'action': 'view_blocked_users'},
            {'name': 'Unblock User', 'url': '#', 'emoji': '🔓', 'action': 'unblock_user'},
            {'name': 'Block User', 'url': '#', 'emoji': '🔒', 'action': 'block_user'},
            {'name': "View Users' Contacts", 'url': '#', 'emoji': '📇', 'action': 'view_users_contacts'},
            {'name': 'Back to Admin Menu', 'url': 'admin_dashboard', 'emoji': '🔙', 'action': 'back_menu'},
        ]
        return render(request, 'core/manage_users.html', {
            'manage_users_options': manage_users_options
        })
    
    elif request.method == 'POST':
        action = request.POST.get('action')
        if action == 'view_all_users':
            return JsonResponse({'redirect': reverse('view_all_users')})
        elif action == 'sort_users':
            return JsonResponse({'redirect': reverse('sort_users')})
        elif action == 'search_user':
            return JsonResponse({'redirect': reverse('search_user')})
        elif action == 'remove_user':
            return JsonResponse({'redirect': reverse('remove_user')})
        elif action == 'view_blocked_users':
            return JsonResponse({'redirect': reverse('view_blocked_users')})
        elif action == 'unblock_user':
            return JsonResponse({'redirect': reverse('unblock_user')})
        elif action == 'block_user':
            return JsonResponse({'redirect': reverse('block_user')})
        elif action == 'view_users_contacts':
            return JsonResponse({'redirect': reverse('view_users_contacts')})
        elif action == 'back_menu':
            return JsonResponse({'redirect': reverse('admin_dashboard')})
        else:
            return JsonResponse({'error': 'Invalid action, akhi!'}, status=400)
        

def view_all_users(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')
    
    # Clear messages for a clean slate
    storage = messages.get_messages(request)
    if storage:
        for message in storage:
            storage.used = True
        del storage

    # Fetch users efficiently, ordered by joined time (newest first)
    users = User.objects.all().order_by('-date_joined').defer('password')  # Skip password field
    
    # Build user data—fast and simple
    user_list = [
        {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
            'password': 'encrypted',  # Hardcode "encrypted"—no unhashing nonsense
            'phone_number': user.phone_number if user.phone_number else 'N/A',
            'joined_time': user.date_joined.strftime('%Y-%m-%d %H:%M') if user.date_joined else 'N/A',
            'two_factor_enabled': 'Yes 🔒' if user.two_factor_code else 'No',
        }
        for user in users
    ]

    return render(request, 'core/view_all_users.html', {'users': user_list})


def sort_users(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for message in storage:
            storage.used = True
        del storage

    # Default sort: Joined Newest First
    sort_by = request.GET.get('sort_by', 'joined_newest')
    users = User.objects.all().defer('password')  # Skip password for speed

    # Sorting logic
    if sort_by == 'joined_oldest':
        users = users.order_by('date_joined')
        sort_label = "Joined (Oldest First)"
    elif sort_by == 'joined_newest':
        users = users.order_by('-date_joined')
        sort_label = "Joined (Newest First)"
    elif sort_by == 'first_name_az':
        users = users.order_by('first_name')
        sort_label = "First Name (A-Z)"
    elif sort_by == 'first_name_za':
        users = users.order_by('-first_name')
        sort_label = "First Name (Z-A)"
    elif sort_by == 'last_name_az':
        users = users.order_by('last_name')
        sort_label = "Last Name (A-Z)"
    elif sort_by == 'last_name_za':
        users = users.order_by('-last_name')
        sort_label = "Last Name (Z-A)"
    elif sort_by == 'age_youngest':
        users = users.order_by('age')
        sort_label = "Age (Youngest First)"
    elif sort_by == 'age_oldest':
        users = users.order_by('-age')
        sort_label = "Age (Oldest First)"
    elif sort_by == 'gender_male':
        users = users.order_by('gender')  # Male first (alphabetical)
        sort_label = "Gender (Male First)"
    elif sort_by == 'gender_female':
        users = users.order_by('-gender')  # Female first (reverse alphabetical)
        sort_label = "Gender (Female First)"
    else:
        users = users.order_by('-date_joined')  # Fallback
        sort_label = "Joined (Newest First)"

    # Prep user data
    user_list = [
        {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
            'password': 'encrypted',
            'phone_number': user.phone_number if user.phone_number else 'N/A',
            'joined_time': user.date_joined.strftime('%Y-%m-%d %H:%M') if user.date_joined else 'N/A',
            'two_factor_enabled': 'Yes 🔒' if user.two_factor_code else 'No',
        }
        for user in users
    ]

    # Dropdown options—your exact list
    sort_options = [
        {'value': 'joined_oldest', 'label': 'Joined (Oldest First)', 'emoji': '🕰️'},
        {'value': 'joined_newest', 'label': 'Joined (Newest First)', 'emoji': '⏰'},
        {'value': 'first_name_az', 'label': 'First Name (A-Z)', 'emoji': '🔠'},
        {'value': 'first_name_za', 'label': 'First Name (Z-A)', 'emoji': '🔡'},
        {'value': 'last_name_az', 'label': 'Last Name (A-Z)', 'emoji': '📛'},
        {'value': 'last_name_za', 'label': 'Last Name (Z-A)', 'emoji': '📜'},
        {'value': 'age_youngest', 'label': 'Age (Youngest First)', 'emoji': '👶'},
        {'value': 'age_oldest', 'label': 'Age (Oldest First)', 'emoji': '👴'},
        {'value': 'gender_male', 'label': 'Gender (Male First)', 'emoji': '♂️'},
        {'value': 'gender_female', 'label': 'Gender (Female First)', 'emoji': '♀️'},
    ]

    return render(request, 'core/sort_users.html', {
        'users': user_list,
        'sort_by': sort_by,
        'sort_label': sort_label,
        'sort_options': sort_options,
    })


def search_user(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for message in storage:
            storage.used = True
        del storage

    return render(request, 'core/search_user.html')

def search_user_api(request):
    if not request.session.get('is_admin', False):
        return JsonResponse({'error': 'Not authorized'}, status=403)

    query = request.GET.get('q', '').strip()
    users = User.objects.all().defer('password')

    if query:
        # Search across all fields—broad and flexible
        try:
            age_query = int(query)  # If it’s a number, search age
            users = users.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(age=age_query) |
                Q(gender__icontains=query) |
                Q(phone_number__icontains=query) |
                Q(date_joined__icontains=query)
            )
        except ValueError:
            # Not a number—skip age filter
            users = users.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(gender__icontains=query) |
                Q(phone_number__icontains=query) |
                Q(date_joined__icontains=query)
            )

    # Prep user data for JSON
    user_list = [
        {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
            'password': 'encrypted',
            'phone_number': user.phone_number if user.phone_number else 'N/A',
            'joined_time': user.date_joined.strftime('%Y-%m-%d %H:%M') if user.date_joined else 'N/A',
            'two_factor_enabled': 'Yes 🔒' if user.two_factor_code else 'No',
        }
        for user in users
    ]

    return JsonResponse({'users': user_list})

def remove_user(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                User.objects.get(id=user_id)  # Check if user exists
                return redirect('confirm_remove_user', user_id=user_id)  # Redirect to confirm
            except User.DoesNotExist:
                messages.error(request, "User not found, dude! 🤔")
        else:
            messages.error(request, "Pick a user to remove, bro! 😏")
        return render(request, 'core/remove_user.html')  # Render if error

    # Search logic for GET
    query = request.GET.get('q', '').strip()
    users = User.objects.none()

    if query:
        try:
            age_query = int(query)
            users = User.objects.filter(
                Q(id__icontains=query) |
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(age=age_query) |
                Q(gender__icontains=query)
            ).defer('password')
        except ValueError:
            users = User.objects.filter(
                Q(id__icontains=query) |
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(gender__icontains=query)
            ).defer('password')

        if not users.exists():
            messages.info(request, f"No users found for '{query}', dude! 🔍")
    else:
        messages.info(request, "Search for a user to remove, bro! 🔎")

    user_list = [
        {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
        }
        for user in users
    ]

    return render(request, 'core/remove_user.html', {
        'users': user_list,
        'query': query,
    })

def confirm_remove_user(request, user_id):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found, dude! 🤔")
        return redirect('remove_user')

    if request.method == 'POST':
        if request.POST.get('confirm') == 'yes':
            user.delete()
            messages.success(request, f"User {user.username} wiped out, boss! 🗑️")
            return redirect('manage_users')
        else:
            messages.info(request, f"Removal of {user.username} canceled, boss! 😛")
            return redirect('remove_user')

    user_data = {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'age': user.age if user.age else 'N/A',
        'gender': user.gender if user.gender else 'N/A',
        'username': user.username,
    }

    return render(request, 'core/confirm_remove_user.html', {'user': user_data})

def view_blocked_users(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "Admin only, akhi!")
        return redirect('admin_login')

    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    blocked_users = User.objects.filter(block_until__gt=timezone.now()).defer('password')
    user_list = [
        {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'blocked_until': user.block_until.strftime('%Y-%m-%d %H:%M:%S UTC'),
        }
        for user in blocked_users
    ]

    if not user_list:
        messages.info(request, "No users blocked from login, alhamdulillah!")

    return render(request, 'core/view_blocked_users.html', {'blocked_users': user_list})

def unblock_user(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "Admin only, akhi!")
        return redirect('admin_login')

    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    blocked_users = User.objects.filter(block_until__gt=timezone.now()).defer('password')
    user_list = [
        {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
            'blocked_until': user.block_until.strftime('%Y-%m-%d %H:%M:%S UTC') if user.block_until else 'Not Blocked',
        }
        for user in blocked_users
    ]

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id, block_until__gt=timezone.now())
                user.block_until = None
                user.save()
                messages.success(request, f"User {user.username} unblocked, akhi! 🔓")
                # Refresh user_list after unblock
                blocked_users = User.objects.filter(block_until__gt=timezone.now()).defer('password')
                user_list = [
                    {
                        'id': u.id,
                        'first_name': u.first_name,
                        'last_name': u.last_name,
                        'age': u.age if u.age else 'N/A',
                        'gender': u.gender if u.gender else 'N/A',
                        'username': u.username,
                        'blocked_until': u.block_until.strftime('%Y-%m-%d %H:%M:%S UTC') if u.block_until else 'Not Blocked',
                    }
                    for u in blocked_users
                ]
            except User.DoesNotExist:
                messages.error(request, "User not found or not blocked, dude!")
        else:
            messages.error(request, "Pick a user to unblock, bro!")
        return render(request, 'core/unblock_user.html', {'blocked_users': user_list})

    if not user_list:
        messages.info(request, "No users blocked, alhamdulillah!")

    return render(request, 'core/unblock_user.html', {'blocked_users': user_list})


def block_user(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "Admin only, akhi!")
        return redirect('admin_login')

    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    query = request.GET.get('q', '').strip()
    users = User.objects.none()

    if query:
        try:
            age_query = int(query)
            users = User.objects.filter(
                Q(id__icontains=query) |
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(age=age_query) |
                Q(gender__icontains=query)
            ).defer('password')
        except ValueError:
            users = User.objects.filter(
                Q(id__icontains=query) |
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(gender__icontains=query)
            ).defer('password')

        if not users.exists():
            messages.info(request, f"No users found for '{query}', dude! 🔍")

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        minutes = request.POST.get('minutes')
        if user_id and minutes:
            try:
                minutes = int(minutes)
                if minutes <= 0:
                    messages.error(request, "Enter a positive number, bro!")
                else:
                    user = User.objects.get(id=user_id)
                    user.block_until = timezone.now() + timedelta(minutes=minutes)
                    user.save()
                    messages.success(request, f"User {user.username} blocked for {minutes} mins, akhi! 🔒")
            except ValueError:
                messages.error(request, "Minutes must be a number, dude!")
            except User.DoesNotExist:
                messages.error(request, "User not found, bro!")
        else:
            messages.error(request, "Pick a user and minutes, akhi!")
        # Refresh user_list after block
        if query:
            users = User.objects.filter(
                Q(id__icontains=query) |
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(gender__icontains=query)
            ).defer('password')

    user_list = [
        {
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age if user.age else 'N/A',
            'gender': user.gender if user.gender else 'N/A',
            'username': user.username,
            'blocked_until': user.block_until.strftime('%Y-%m-%d %H:%M:%S UTC') if user.block_until else 'Not Blocked',
        }
        for user in users
    ]

    if not query:
        messages.info(request, "Search for a user to block, bro! 🔎")

    return render(request, 'core/block_user.html', {'users': user_list, 'query': query})


def view_users_contacts(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "Admin only, akhi!")
        return redirect('admin_login')

    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    return render(request, 'core/view_users_contacts.html')

def view_users_contacts_api(request):
    if not request.session.get('is_admin', False):
        return JsonResponse({'error': 'Not authorized'}, status=403)

    query = request.GET.get('q', '').strip().lower()  # Case-insensitive
    user_id = request.GET.get('user_id')  # For fetching contacts of a specific user

    if user_id:  # Fetch contacts for a selected user
        try:
            user = User.objects.get(id=user_id)
            contacts = Contact.objects.filter(user=user)
            contact_list = [
                {
                    'contact_id': contact.contact_user.id,
                    'contact_name': f"{contact.contact_user.first_name} {contact.contact_user.last_name}",
                    'contact_phone': contact.contact_user.phone_number or 'N/A',
                    'added_at': contact.added_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                }
                for contact in contacts
            ]
            return JsonResponse({
                'user': {'name': f"{user.first_name} {user.last_name}"},
                'contacts': contact_list
            })
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found, akhi!'}, status=404)

    # Search users
    users = User.objects.all().defer('password')
    if query:
        users = users.filter(
            Q(id__icontains=query) |
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(phone_number__icontains=query)
        )

    user_list = [
        {
            'id': user.id,
            'first_name': user.first_name or 'N/A',
            'last_name': user.last_name or 'N/A',
            'username': user.username,
            'phone': user.phone_number or 'N/A',
        }
        for user in users
    ]
    return JsonResponse({'users': user_list})


def manage_cards(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    if request.method == 'GET':
        manage_cards_options = [
            {'name': 'View Cards', 'url': '#', 'emoji': '👀', 'action': 'view_cards'},
            {'name': 'Sort Cards', 'url': '#', 'emoji': '🔄', 'action': 'sort_cards'},
            {'name': 'Search Card', 'url': '#', 'emoji': '🔍', 'action': 'search_card'},
            {'name': 'Adjust Card', 'url': '#', 'emoji': '💰', 'action': 'adjust_card'},
            {'name': 'Remove Card', 'url': '#', 'emoji': '🗑️', 'action': 'remove_card'},
            {'name': 'Back to Dashboard', 'url': 'admin_dashboard', 'emoji': '🔙', 'action': 'back_dashboard'},
        ]
        return render(request, 'core/manage_cards.html', {
            'manage_cards_options': manage_cards_options
        })

    elif request.method == 'POST':
        action = request.POST.get('action')
        if action == 'view_cards':
            return JsonResponse({'redirect': reverse('admin_view_cards')})  # Placeholder
        elif action == 'sort_cards':
            return JsonResponse({'redirect': reverse('sort_cards')})  # Placeholder
        elif action == 'search_card':
            return JsonResponse({'redirect': reverse('search_card')})  # Placeholder
        elif action == 'adjust_card':
            return JsonResponse({'redirect': reverse('adjust_card')})  # Placeholder
        elif action == 'remove_card':
            return JsonResponse({'redirect': reverse('admin_remove_card')})  # Placeholder
        elif action == 'back_dashboard':
            return JsonResponse({'redirect': reverse('admin_dashboard')})
        else:
            return JsonResponse({'error': 'Invalid action, dude!'}, status=400)


def admin_view_cards(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages for a fresh look
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Fetch all cards, ordered by creation time (newest first)
    cards = Card.objects.all().order_by('-created_at').select_related('user')  # Optimize with user data

    # Build card data
    card_list = [
        {
            'id': card.id,
            'card_number': card.card_number,
            'card_password': card.password,  # 6-digit PIN
            'first_name': card.user.first_name or 'N/A',
            'last_name': card.user.last_name or 'N/A',
            'balance': f"{card.balance:.2f}",
            'currency': card.currency,
            'added_time': card.created_at.strftime('%Y-%m-%d %H:%M') if card.created_at else 'N/A',
        }
        for card in cards
    ]

    return render(request, 'core/admin_view_cards.html', {'cards': card_list})


def sort_cards(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Default sort: Added Time (Newest First)
    sort_by = request.GET.get('sort_by', 'added_newest')
    cards = Card.objects.all().select_related('user')  # Optimize with user data

    # Sorting logic
    if sort_by == 'balance_high':
        cards = cards.order_by('-balance')
        sort_label = "Balance (High to Low)"
    elif sort_by == 'balance_low':
        cards = cards.order_by('balance')
        sort_label = "Balance (Low to High)"
    elif sort_by == 'added_oldest':
        cards = cards.order_by('created_at')
        sort_label = "Added Time (Oldest First)"
    elif sort_by == 'added_newest':
        cards = cards.order_by('-created_at')
        sort_label = "Added Time (Newest First)"
    elif sort_by == 'currency':
        cards = cards.order_by('currency')
        sort_label = "Currency (A-Z)"
    elif sort_by == 'first_name_az':
        cards = cards.order_by('user__first_name')
        sort_label = "First Name (A-Z)"
    elif sort_by == 'first_name_za':
        cards = cards.order_by('-user__first_name')
        sort_label = "First Name (Z-A)"
    elif sort_by == 'last_name_az':
        cards = cards.order_by('user__last_name')
        sort_label = "Last Name (A-Z)"
    elif sort_by == 'last_name_za':
        cards = cards.order_by('-user__last_name')
        sort_label = "Last Name (Z-A)"
    else:
        cards = cards.order_by('-created_at')  # Fallback
        sort_label = "Added Time (Newest First)"

    # Prep card data
    card_list = [
        {
            'id': card.id,
            'card_number': card.card_number,
            'card_password': card.password,
            'first_name': card.user.first_name or 'N/A',
            'last_name': card.user.last_name or 'N/A',
            'balance': f"{card.balance:.2f}",
            'currency': card.currency,
            'added_time': card.created_at.strftime('%Y-%m-%d %H:%M') if card.created_at else 'N/A',
        }
        for card in cards
    ]

    # Sort options
    sort_options = [
        {'value': 'balance_high', 'label': 'Balance (High to Low)', 'emoji': '💸'},
        {'value': 'balance_low', 'label': 'Balance (Low to High)', 'emoji': '💵'},
        {'value': 'added_oldest', 'label': 'Added Time (Oldest First)', 'emoji': '🕰️'},
        {'value': 'added_newest', 'label': 'Added Time (Newest First)', 'emoji': '⏰'},
        {'value': 'currency', 'label': 'Currency (A-Z)', 'emoji': '💱'},
        {'value': 'first_name_az', 'label': 'First Name (A-Z)', 'emoji': '🔠'},
        {'value': 'first_name_za', 'label': 'First Name (Z-A)', 'emoji': '🔡'},
        {'value': 'last_name_az', 'label': 'Last Name (A-Z)', 'emoji': '📛'},
        {'value': 'last_name_za', 'label': 'Last Name (Z-A)', 'emoji': '📜'},
    ]

    return render(request, 'core/sort_cards.html', {
        'cards': card_list,
        'sort_by': sort_by,
        'sort_label': sort_label,
        'sort_options': sort_options,
    })


def search_card(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    return render(request, 'core/search_card.html')

def search_card_api(request):
    if not request.session.get('is_admin', False):
        return JsonResponse({'error': 'Not authorized'}, status=403)

    query = request.GET.get('q', '').strip().lower()  # Case-insensitive
    cards = Card.objects.all().select_related('user')

    if query:
        try:
            balance_query = float(query)  # If it’s a number, search balance
            cards = cards.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(balance=balance_query)
            )
        except ValueError:
            # Not a number—skip balance filter
            cards = cards.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            )

    card_list = [
        {
            'id': card.id,
            'card_number': card.card_number,
            'card_password': card.password,
            'first_name': card.user.first_name or 'N/A',
            'last_name': card.user.last_name or 'N/A',
            'balance': f"{card.balance:.2f}",
            'currency': card.currency,
            'added_time': card.created_at.strftime('%Y-%m-%d %H:%M') if card.created_at else 'N/A',
        }
        for card in cards
    ]

    return JsonResponse({'cards': card_list})


def adjust_card(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    if request.method == 'POST':
        card_id = request.POST.get('card_id')
        try:
            card = Card.objects.get(id=card_id)
            if 'update' in request.POST:
                # Update card details
                new_card_number = request.POST.get('card_number', '').strip()
                new_first_name = request.POST.get('first_name', '').strip()
                new_last_name = request.POST.get('last_name', '').strip()
                new_balance = request.POST.get('balance', '').strip()
                new_currency = request.POST.get('currency', '').strip()

                # Validate and update card number
                if new_card_number and new_card_number != card.card_number:
                    if Card.objects.filter(card_number=new_card_number).exclude(id=card.id).exists():
                        messages.error(request, "That card number’s taken, dude!")
                    else:
                        card.card_number = new_card_number
                        messages.success(request, f"Card number updated to {new_card_number}!")

                # Update user first/last names
                if new_first_name and new_first_name != card.user.first_name:
                    card.user.first_name = new_first_name
                    messages.success(request, f"First name updated to {new_first_name}!")
                if new_last_name and new_last_name != card.user.last_name:
                    card.user.last_name = new_last_name
                    messages.success(request, f"Last name updated to {new_last_name}!")

                # Update balance
                if new_balance:
                    try:
                        new_balance = Decimal(new_balance)
                        if new_balance < 0:
                            messages.error(request, "Balance can’t be negative, dude!")
                        elif new_balance != card.balance:
                            card.balance = new_balance
                            messages.success(request, f"Balance updated to {new_balance:.2f}!")
                    except ValueError:
                        messages.error(request, "Invalid balance, dude! Use numbers!")

                # Update currency (only Card.currency, not User.default_currency)
                if new_currency and new_currency != card.currency:
                    valid_currencies = [choice[0] for choice in Card._meta.get_field('currency').choices]
                    if new_currency in valid_currencies:
                        card.currency = new_currency
                        messages.success(request, f"Card currency updated to {new_currency}!")
                    else:
                        messages.error(request, "Invalid currency, dude!")

                # Save changes
                card.user.save()  # Save User changes (first/last name)
                card.save()       # Save Card changes (number, balance, currency)

            # Re-fetch card for display
            card_data = {
                'id': card.id,
                'card_number': card.card_number,
                'first_name': card.user.first_name or 'N/A',
                'last_name': card.user.last_name or 'N/A',
                'balance': f"{card.balance:.2f}",
                'currency': card.currency,  # Explicitly Card.currency
                'currencies': [choice[0] for choice in Card._meta.get_field('currency').choices],
            }
            return render(request, 'core/adjust_card.html', {'card': card_data})

        except Card.DoesNotExist:
            messages.error(request, "Card not found, dude!")

    # GET: Search for a card
    query = request.GET.get('q', '').strip().lower()
    cards = Card.objects.none()

    if query:
        try:
            balance_query = float(query)
            cards = Card.objects.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(balance=balance_query)
            ).select_related('user')
        except ValueError:
            cards = Card.objects.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            ).select_related('user')

    card_list = [
        {
            'id': card.id,
            'card_number': card.card_number,
            'first_name': card.user.first_name or 'N/A',
            'last_name': card.user.last_name or 'N/A',
            'balance': f"{card.balance:.2f}",
            'currency': card.currency,  # Explicitly Card.currency
        }
        for card in cards
    ]

    if query and not cards.exists():
        messages.info(request, f"No cards found for '{query}', dude!")

    return render(request, 'core/adjust_card.html', {
        'cards': card_list,
        'query': query,
    })


def admin_remove_card(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    if request.method == 'POST':
        card_id = request.POST.get('card_id')
        try:
            card = Card.objects.get(id=card_id)
            if 'confirm_remove' in request.POST:
                # Remove the card and stay on page
                card_number = card.card_number  # Store for message
                card.delete()
                messages.success(request, f"Card {card_number} removed, dude!")
                # Reset to search view after removal
                return render(request, 'core/admin_remove_card.html', {'cards': [], 'query': ''})
            elif 'cancel' in request.POST:
                messages.info(request, "Removal cancelled, dude!")
                # Reset to search view
                return render(request, 'core/admin_remove_card.html', {'cards': [], 'query': ''})

            # Show confirmation page
            card_data = {
                'id': card.id,
                'card_number': card.card_number,
                'first_name': card.user.first_name or 'N/A',
                'last_name': card.user.last_name or 'N/A',
                'balance': f"{card.balance:.2f}",
                'currency': card.currency,
            }
            return render(request, 'core/admin_remove_card.html', {'card': card_data})

        except Card.DoesNotExist:
            messages.error(request, "Card not found, dude!")

    # GET: Search for a card
    query = request.GET.get('q', '').strip().lower()
    cards = Card.objects.none()

    if query:
        try:
            balance_query = float(query)
            cards = Card.objects.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(balance=balance_query)
            ).select_related('user')
        except ValueError:
            cards = Card.objects.filter(
                Q(id__icontains=query) |
                Q(card_number__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query)
            ).select_related('user')

    card_list = [
        {
            'id': card.id,
            'card_number': card.card_number,
            'first_name': card.user.first_name or 'N/A',
            'last_name': card.user.last_name or 'N/A',
            'balance': f"{card.balance:.2f}",
            'currency': card.currency,
        }
        for card in cards
    ]

    if query and not cards.exists():
        messages.info(request, f"No cards found for '{query}', dude!")

    return render(request, 'core/admin_remove_card.html', {
        'cards': card_list,
        'query': query,
    })


def admin_view_transactions(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages for a fresh look
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Fetch all transactions
    transactions = Transaction.objects.all().select_related('sender', 'receiver')
    transaction_list = [
        {
            'id': t.id,
            'sender_name': f"{t.sender.first_name} {t.sender.last_name}",
            'receiver_name': f"{t.receiver.first_name} {t.receiver.last_name}",
            'amount': f"{t.amount:.2f}",
            'currency': t.currency,
            'status': t.status,
            'timestamp': t.timestamp.strftime('%Y-%m-%d %H:%M') if t.timestamp else 'N/A',
        }
        for t in transactions
    ]

    return render(request, 'core/admin_view_transactions.html', {'transactions': transaction_list})

def download_all_transactions_pdf(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    transactions = Transaction.objects.all().select_related('sender', 'receiver')
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("All Transactions Report", styles['Heading1']))
    story.append(Spacer(1, 12))
    for t in transactions:
        story.append(Paragraph(f"ID: {t.id}", styles['BodyText']))
        story.append(Paragraph(f"Sender: {t.sender.first_name} {t.sender.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Receiver: {t.receiver.first_name} {t.receiver.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Amount: {t.amount:.2f} {t.currency}", styles['BodyText']))
        story.append(Paragraph(f"Timestamp: {t.timestamp.strftime('%Y-%m-%d %H:%M') if t.timestamp else 'N/A'}", styles['BodyText']))
        story.append(Paragraph(f"Status: {t.status}", styles['BodyText']))
        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f"attachment; filename=\"all_transactions_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
    return response

def admin_sort_transactions(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages for a fresh look
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Default sort: Timestamp (Newest First)
    sort_by = request.GET.get('sort_by', 'timestamp_newest')
    transactions = Transaction.objects.all().select_related('sender', 'receiver')

    # Sorting logic
    if sort_by == 'sender_az':
        transactions = transactions.order_by('sender__first_name', 'sender__last_name')
        sort_label = "Sender Name (A-Z)"
    elif sort_by == 'sender_za':
        transactions = transactions.order_by('-sender__first_name', '-sender__last_name')
        sort_label = "Sender Name (Z-A)"
    elif sort_by == 'receiver_az':
        transactions = transactions.order_by('receiver__first_name', 'receiver__last_name')
        sort_label = "Receiver Name (A-Z)"
    elif sort_by == 'receiver_za':
        transactions = transactions.order_by('-receiver__first_name', '-receiver__last_name')
        sort_label = "Receiver Name (Z-A)"
    elif sort_by == 'amount_high':
        transactions = transactions.order_by('-amount')
        sort_label = "Amount (High to Low)"
    elif sort_by == 'amount_low':
        transactions = transactions.order_by('amount')
        sort_label = "Amount (Low to High)"
    elif sort_by == 'status_completed':
        transactions = transactions.annotate(
            status_order=Case(
                When(status='completed', then=Value(1)),
                When(status='pending', then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('status_order')
        sort_label = "Status (Completed First)"
    elif sort_by == 'status_pending':
        transactions = transactions.annotate(
            status_order=Case(
                When(status='pending', then=Value(1)),
                When(status='completed', then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('status_order')
        sort_label = "Status (Pending First)"
    elif sort_by == 'timestamp_oldest':
        transactions = transactions.order_by('timestamp')
        sort_label = "Timestamp (Oldest First)"
    elif sort_by == 'timestamp_newest':
        transactions = transactions.order_by('-timestamp')
        sort_label = "Timestamp (Newest First)"
    else:
        transactions = transactions.order_by('-timestamp')
        sort_label = "Timestamp (Newest First)"

    # Prep transaction data
    transaction_list = [
        {
            'id': t.id,
            'sender_name': f"{t.sender.first_name} {t.sender.last_name}",
            'receiver_name': f"{t.receiver.first_name} {t.receiver.last_name}",
            'amount': f"{t.amount:.2f}",
            'currency': t.currency,
            'status': t.status,
            'timestamp': t.timestamp.strftime('%Y-%m-%d %H:%M') if t.timestamp else 'N/A',
        }
        for t in transactions
    ]

    # Sort options
    sort_options = [
        {'value': 'sender_az', 'label': 'Sender Name (A-Z)', 'emoji': '👤'},
        {'value': 'sender_za', 'label': 'Sender Name (Z-A)', 'emoji': '👤'},
        {'value': 'receiver_az', 'label': 'Receiver Name (A-Z)', 'emoji': '👥'},
        {'value': 'receiver_za', 'label': 'Receiver Name (Z-A)', 'emoji': '👥'},
        {'value': 'amount_high', 'label': 'Amount (High to Low)', 'emoji': '💸'},
        {'value': 'amount_low', 'label': 'Amount (Low to High)', 'emoji': '💵'},
        {'value': 'status_completed', 'label': 'Status (Completed First)', 'emoji': '✅'},
        {'value': 'status_pending', 'label': 'Status (Pending First)', 'emoji': '⏳'},
        {'value': 'timestamp_oldest', 'label': 'Timestamp (Oldest First)', 'emoji': '🕰️'},
        {'value': 'timestamp_newest', 'label': 'Timestamp (Newest First)', 'emoji': '⏰'},
    ]

    return render(request, 'core/admin_sort_transactions.html', {
        'transactions': transaction_list,
        'sort_by': sort_by,
        'sort_label': sort_label,
        'sort_options': sort_options,
    })


def download_transaction_pdf(request, transaction_id):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    try:
        transaction = Transaction.objects.get(id=transaction_id)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Transaction ID: {transaction.id}", styles['Heading1']))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Sender: {transaction.sender.first_name} {transaction.sender.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Receiver: {transaction.receiver.first_name} {transaction.receiver.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Amount: {transaction.amount:.2f} {transaction.currency}", styles['BodyText']))
        story.append(Paragraph(f"Timestamp: {transaction.timestamp.strftime('%Y-%m-%d %H:%M') if transaction.timestamp else 'N/A'}", styles['BodyText']))
        story.append(Paragraph(f"Status: {transaction.status}", styles['BodyText']))

        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f"attachment; filename=\"transaction_{transaction.id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
        return response
    except Transaction.DoesNotExist:
        messages.error(request, "Transaction not found, dude!")
        return redirect('admin_manage_transactions')

def download_all_sorted_transactions_pdf(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    sort_by = request.GET.get('sort_by', 'timestamp_newest')
    transactions = Transaction.objects.all().select_related('sender', 'receiver')

    sort_options = {
        'sender_az': ('sender__first_name', 'sender__last_name', "Sender Name (A-Z)"),
        'sender_za': ('-sender__first_name', '-sender__last_name', "Sender Name (Z-A)"),
        'receiver_az': ('receiver__first_name', 'receiver__last_name', "Receiver Name (A-Z)"),
        'receiver_za': ('-receiver__first_name', '-receiver__last_name', "Receiver Name (Z-A)"),
        'amount_high': ('-amount', "Amount (High to Low)"),
        'amount_low': ('amount', "Amount (Low to High)"),
        'timestamp_oldest': ('timestamp', "Timestamp (Oldest First)"),
        'timestamp_newest': ('-timestamp', "Timestamp (Newest First)"),
    }

    if sort_by in sort_options:
        transactions = transactions.order_by(*sort_options[sort_by][:-1])
        sort_label = sort_options[sort_by][-1]
    elif sort_by == 'status_completed':
        transactions = transactions.annotate(
            status_order=Case(
                When(status='completed', then=Value(1)),
                When(status='pending', then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('status_order')
        sort_label = "Status (Completed First)"
    elif sort_by == 'status_pending':
        transactions = transactions.annotate(
            status_order=Case(
                When(status='pending', then=Value(1)),
                When(status='completed', then=Value(2)),
                default=Value(3),
                output_field=IntegerField()
            )
        ).order_by('status_order')
        sort_label = "Status (Pending First)"
    else:
        transactions = transactions.order_by('-timestamp')
        sort_label = "Timestamp (Newest First)"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Sorted Transactions Report - {sort_label}", styles['Heading1']))
    story.append(Spacer(1, 12))

    for t in transactions:
        story.append(Paragraph(f"ID: {t.id}", styles['BodyText']))
        story.append(Paragraph(f"Sender: {t.sender.first_name} {t.sender.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Receiver: {t.receiver.first_name} {t.receiver.last_name}", styles['BodyText']))
        story.append(Paragraph(f"Amount: {t.amount:.2f} {t.currency}", styles['BodyText']))
        story.append(Paragraph(f"Timestamp: {t.timestamp.strftime('%Y-%m-%d %H:%M') if t.timestamp else 'N/A'}", styles['BodyText']))
        story.append(Paragraph(f"Status: {t.status}", styles['BodyText']))
        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)

    filename = f"sorted_transactions_{sort_label.lower().replace(' ', '_')}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response

def admin_manage_transactions(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    if request.method == 'GET':
        transaction_options = [
            {'name': 'View Transactions', 'url': '#', 'emoji': '👀', 'action': 'view_transactions'},
            {'name': 'Sort Transactions', 'url': '#', 'emoji': '🔄', 'action': 'sort_transactions'},
            {'name': 'Generate Report', 'url': '#', 'emoji': '📊', 'action': 'generate_report'},  # Changed to Generate Report
            {'name': 'Search Transaction', 'url': '#', 'emoji': '🔍', 'action': 'search_transaction'},
            {'name': 'Back to Dashboard', 'url': 'admin_dashboard', 'emoji': '🔙', 'action': 'back_dashboard'},
        ]
        return render(request, 'core/admin_manage_transactions.html', {
            'transaction_options': transaction_options
        })

    elif request.method == 'POST':
        action = request.POST.get('action')
        if action == 'view_transactions':
            return JsonResponse({'redirect': reverse('admin_view_transactions')})
        elif action == 'sort_transactions':
            return JsonResponse({'redirect': reverse('admin_sort_transactions')})
        elif action == 'generate_report':
            return JsonResponse({'redirect': reverse('admin_generate_report')})
        elif action == 'search_transaction':
            return JsonResponse({'redirect': reverse('admin_search_transaction')})
        elif action == 'back_dashboard':
            return JsonResponse({'redirect': reverse('admin_dashboard')})
        else:
            return JsonResponse({'error': 'Invalid action, dude!'}, status=400)

def admin_generate_report(request):
    # Check admin access
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear old messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Base queryset
    transactions = Transaction.objects.all().select_related('sender', 'receiver')
    now = timezone.now()

    # Time filters from GET params, defaulting to current date
    selected_day = request.GET.get('day', now.strftime('%Y-%m-%d'))
    selected_week = request.GET.get('week', now.strftime('%Y-%W'))
    selected_month = request.GET.get('month', now.strftime('%Y-%m'))
    selected_year = request.GET.get('year', now.strftime('%Y'))

    # Dropdown options (database-agnostic)
    days = transactions.annotate(
        year=ExtractYear('timestamp'),
        month=ExtractMonth('timestamp'),
        day=ExtractDay('timestamp')
    ).values('year', 'month', 'day').distinct().order_by('year', 'month', 'day')

    weeks = transactions.annotate(
        year=ExtractYear('timestamp'),
        week=ExtractWeek('timestamp')
    ).values('year', 'week').distinct().order_by('year', 'week')

    months = transactions.annotate(
        year=ExtractYear('timestamp'),
        month=ExtractMonth('timestamp')
    ).values('year', 'month').distinct().order_by('year', 'month')

    years = transactions.annotate(
        year=ExtractYear('timestamp')
    ).values('year').distinct().order_by('year')

    # Daily Report
    try:
        daily_tx = transactions.filter(timestamp__date=datetime.strptime(selected_day, '%Y-%m-%d'))
    except ValueError:
        selected_day = now.strftime('%Y-%m-%d')
        daily_tx = transactions.filter(timestamp__date=now.date())
    daily_data = {
        'total': daily_tx.values('currency').annotate(total=Sum('amount')),
        'count': daily_tx.count(),
        'most_sender': daily_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': daily_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': daily_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': daily_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': daily_tx.order_by('-amount').first(),
    }

    # Weekly Report
    try:
        week_start = datetime.strptime(selected_week + '-1', '%Y-%W-%w').replace(tzinfo=timezone.get_current_timezone())
        week_end = week_start + timedelta(days=6)
    except ValueError:
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        selected_week = week_start.strftime('%Y-%W')
    weekly_tx = transactions.filter(timestamp__range=[week_start, week_end])
    weekly_data = {
        'total': weekly_tx.values('currency').annotate(total=Sum('amount')),
        'count': weekly_tx.count(),
        'most_sender': weekly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': weekly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': weekly_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': weekly_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': weekly_tx.order_by('-amount').first(),
        'busiest_day': weekly_tx.annotate(
            year=ExtractYear('timestamp'),
            month=ExtractMonth('timestamp'),
            day=ExtractDay('timestamp')
        ).values('year', 'month', 'day').annotate(total=Sum('amount')).order_by('-total').first(),
    }

    # Monthly Report
    try:
        year, month = map(int, selected_month.split('-'))
        monthly_tx = transactions.filter(timestamp__year=year, timestamp__month=month)
    except (ValueError, TypeError):
        year, month = now.year, now.month
        selected_month = f"{year}-{month:02d}"
        monthly_tx = transactions.filter(timestamp__year=year, timestamp__month=month)
    monthly_data = {
        'total': monthly_tx.values('currency').annotate(total=Sum('amount')),
        'count': monthly_tx.count(),
        'most_sender': monthly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': monthly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': monthly_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': monthly_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': monthly_tx.order_by('-amount').first(),
        'top_currency': monthly_tx.values('currency').annotate(total=Sum('amount')).order_by('-total').first(),
    }

    # Annual Report
    try:
        year = int(selected_year)
        annual_tx = transactions.filter(timestamp__year=year)
    except (ValueError, TypeError):
        year = now.year
        selected_year = str(year)
        annual_tx = transactions.filter(timestamp__year=year)
    annual_data = {
        'total': annual_tx.values('currency').annotate(total=Sum('amount')),
        'count': annual_tx.count(),
        'most_sender': annual_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': annual_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': annual_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': annual_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': annual_tx.order_by('-amount').first(),
        'growth': "Growth calculation TBD" if annual_tx.exists() else "N/A",
    }

    # Format report data for the template
    report_data = {
        'days': [f"{d['year']}-{d['month']:02d}-{d['day']:02d}" for d in days],
        'weeks': [f"{w['year']}-{w['week']:02d}" for w in weeks],
        'months': [f"{m['year']}-{m['month']:02d}" for m in months],
        'years': [str(y['year']) for y in years],
        'selected': {
            'day': selected_day,
            'week': selected_week,
            'month': selected_month,
            'year': selected_year
        },
        'daily': {
            'total': ", ".join(f"{t['total']:.2f} {t['currency']}" for t in daily_data['total']) if daily_data['total'] else "0.00",
            'count': daily_data['count'],
            'most_sender': (
                f"{daily_data['most_sender']['sender__first_name']} {daily_data['most_sender']['sender__last_name']} - {daily_data['most_sender']['total']:.2f} {daily_data['most_sender']['currency']}"
                if daily_data['most_sender'] else "N/A"
            ),
            'least_sender': (
                f"{daily_data['least_sender']['sender__first_name']} {daily_data['least_sender']['sender__last_name']} - {daily_data['least_sender']['total']:.2f} {daily_data['least_sender']['currency']}"
                if daily_data['least_sender'] else "N/A"
            ),
            'peak_hour': (
                f"{daily_data['peak_hour']['hour']}:00 - {daily_data['peak_hour']['count']} tx"
                if daily_data['peak_hour'] else "N/A"
            ),
            'status_split': (
                f"Completed: {daily_data['status_split']['completed']} ({(daily_data['status_split']['completed'] / daily_data['count'] * 100 if daily_data['count'] else 0):.1f}%), "
                f"Pending: {daily_data['status_split']['pending']} ({(daily_data['status_split']['pending'] / daily_data['count'] * 100 if daily_data['count'] else 0):.1f}%)"
            ),
            'largest_tx': (
                f"{daily_data['largest_tx'].amount:.2f} {daily_data['largest_tx'].currency} by {daily_data['largest_tx'].sender.first_name} {daily_data['largest_tx'].sender.last_name} "
                f"to {daily_data['largest_tx'].receiver.first_name} {daily_data['largest_tx'].receiver.last_name}"
                if daily_data['largest_tx'] else "N/A"
            ),
        },
        'weekly': {
            'total': ", ".join(f"{t['total']:.2f} {t['currency']}" for t in weekly_data['total']) if weekly_data['total'] else "0.00",
            'count': weekly_data['count'],
            'most_sender': (
                f"{weekly_data['most_sender']['sender__first_name']} {weekly_data['most_sender']['sender__last_name']} - {weekly_data['most_sender']['total']:.2f} {weekly_data['most_sender']['currency']}"
                if weekly_data['most_sender'] else "N/A"
            ),
            'least_sender': (
                f"{weekly_data['least_sender']['sender__first_name']} {weekly_data['least_sender']['sender__last_name']} - {weekly_data['least_sender']['total']:.2f} {weekly_data['least_sender']['currency']}"
                if weekly_data['least_sender'] else "N/A"
            ),
            'peak_hour': (
                f"{weekly_data['peak_hour']['hour']}:00 - {weekly_data['peak_hour']['count']} tx"
                if weekly_data['peak_hour'] else "N/A"
            ),
            'status_split': (
                f"Completed: {weekly_data['status_split']['completed']} ({(weekly_data['status_split']['completed'] / weekly_data['count'] * 100 if weekly_data['count'] else 0):.1f}%), "
                f"Pending: {weekly_data['status_split']['pending']} ({(weekly_data['status_split']['pending'] / weekly_data['count'] * 100 if weekly_data['count'] else 0):.1f}%)"
            ),
            'largest_tx': (
                f"{weekly_data['largest_tx'].amount:.2f} {weekly_data['largest_tx'].currency} by {weekly_data['largest_tx'].sender.first_name} {weekly_data['largest_tx'].sender.last_name} "
                f"to {weekly_data['largest_tx'].receiver.first_name} {weekly_data['largest_tx'].receiver.last_name}"
                if weekly_data['largest_tx'] else "N/A"
            ),
            'busiest_day': (
                f"{weekly_data['busiest_day']['year']}-{weekly_data['busiest_day']['month']:02d}-{weekly_data['busiest_day']['day']:02d} - {weekly_data['busiest_day']['total']:.2f}"
                if weekly_data['busiest_day'] else "N/A"
            ),
        },
        'monthly': {
            'total': ", ".join(f"{t['total']:.2f} {t['currency']}" for t in monthly_data['total']) if monthly_data['total'] else "0.00",
            'count': monthly_data['count'],
            'most_sender': (
                f"{monthly_data['most_sender']['sender__first_name']} {monthly_data['most_sender']['sender__last_name']} - {monthly_data['most_sender']['total']:.2f} {monthly_data['most_sender']['currency']}"
                if monthly_data['most_sender'] else "N/A"
            ),
            'least_sender': (
                f"{monthly_data['least_sender']['sender__first_name']} {monthly_data['least_sender']['sender__last_name']} - {monthly_data['least_sender']['total']:.2f} {monthly_data['least_sender']['currency']}"
                if monthly_data['least_sender'] else "N/A"
            ),
            'peak_hour': (
                f"{monthly_data['peak_hour']['hour']}:00 - {monthly_data['peak_hour']['count']} tx"
                if monthly_data['peak_hour'] else "N/A"
            ),
            'status_split': (
                f"Completed: {monthly_data['status_split']['completed']} ({(monthly_data['status_split']['completed'] / monthly_data['count'] * 100 if monthly_data['count'] else 0):.1f}%), "
                f"Pending: {monthly_data['status_split']['pending']} ({(monthly_data['status_split']['pending'] / monthly_data['count'] * 100 if monthly_data['count'] else 0):.1f}%)"
            ),
            'largest_tx': (
                f"{monthly_data['largest_tx'].amount:.2f} {monthly_data['largest_tx'].currency} by {monthly_data['largest_tx'].sender.first_name} {monthly_data['largest_tx'].sender.last_name} "
                f"to {monthly_data['largest_tx'].receiver.first_name} {monthly_data['largest_tx'].receiver.last_name}"
                if monthly_data['largest_tx'] else "N/A"
            ),
            'top_currency': (
                f"{monthly_data['top_currency']['currency']} - {monthly_data['top_currency']['total']:.2f}"
                if monthly_data['top_currency'] else "N/A"
            ),
        },
        'annual': {
            'total': ", ".join(f"{t['total']:.2f} {t['currency']}" for t in annual_data['total']) if annual_data['total'] else "0.00",
            'count': annual_data['count'],
            'most_sender': (
                f"{annual_data['most_sender']['sender__first_name']} {annual_data['most_sender']['sender__last_name']} - {annual_data['most_sender']['total']:.2f} {annual_data['most_sender']['currency']}"
                if annual_data['most_sender'] else "N/A"
            ),
            'least_sender': (
                f"{annual_data['least_sender']['sender__first_name']} {annual_data['least_sender']['sender__last_name']} - {annual_data['least_sender']['total']:.2f} {annual_data['least_sender']['currency']}"
                if annual_data['least_sender'] else "N/A"
            ),
            'peak_hour': (
                f"{annual_data['peak_hour']['hour']}:00 - {annual_data['peak_hour']['count']} tx"
                if annual_data['peak_hour'] else "N/A"
            ),
            'status_split': (
                f"Completed: {annual_data['status_split']['completed']} ({(annual_data['status_split']['completed'] / annual_data['count'] * 100 if annual_data['count'] else 0):.1f}%), "
                f"Pending: {annual_data['status_split']['pending']} ({(annual_data['status_split']['pending'] / annual_data['count'] * 100 if annual_data['count'] else 0):.1f}%)"
            ),
            'largest_tx': (
                f"{annual_data['largest_tx'].amount:.2f} {annual_data['largest_tx'].currency} by {annual_data['largest_tx'].sender.first_name} {annual_data['largest_tx'].sender.last_name} "
                f"to {annual_data['largest_tx'].receiver.first_name} {annual_data['largest_tx'].receiver.last_name}"
                if annual_data['largest_tx'] else "N/A"
            ),
            'growth': annual_data['growth'],
        },
    }

    return render(request, 'core/admin_generate_report.html', {'report': report_data})


def download_report_pdf(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    transactions = Transaction.objects.all().select_related('sender', 'receiver')
    now = timezone.now()

    selected_day = request.GET.get('day', now.strftime('%Y-%m-%d'))
    selected_week = request.GET.get('week', now.strftime('%Y-%W'))
    selected_month = request.GET.get('month', now.strftime('%Y-%m'))
    selected_year = request.GET.get('year', now.strftime('%Y'))

    # Daily Report
    try:
        daily_tx = transactions.filter(timestamp__date=datetime.strptime(selected_day, '%Y-%m-%d'))
    except ValueError:
        selected_day = now.strftime('%Y-%m-%d')
        daily_tx = transactions.filter(timestamp__date=now.date())
    daily_data = {
        'total': daily_tx.values('currency').annotate(total=Sum('amount')),
        'count': daily_tx.count(),
        'most_sender': daily_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': daily_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': daily_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': daily_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': daily_tx.order_by('-amount').first(),
    }

    # Weekly Report
    try:
        week_start = datetime.strptime(selected_week + '-1', '%Y-%W-%w').replace(tzinfo=timezone.get_current_timezone())
        week_end = week_start + timedelta(days=6)
    except ValueError:
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        selected_week = week_start.strftime('%Y-%W')
    weekly_tx = transactions.filter(timestamp__range=[week_start, week_end])
    weekly_data = {
        'total': weekly_tx.values('currency').annotate(total=Sum('amount')),
        'count': weekly_tx.count(),
        'most_sender': weekly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': weekly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': weekly_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': weekly_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': weekly_tx.order_by('-amount').first(),
        'busiest_day': weekly_tx.annotate(
            year=ExtractYear('timestamp'),
            month=ExtractMonth('timestamp'),
            day=ExtractDay('timestamp')
        ).values('year', 'month', 'day').annotate(total=Sum('amount')).order_by('-total').first(),
    }

    # Monthly Report
    try:
        year, month = map(int, selected_month.split('-'))
        monthly_tx = transactions.filter(timestamp__year=year, timestamp__month=month)
    except (ValueError, TypeError):
        year, month = now.year, now.month
        selected_month = f"{year}-{month:02d}"
        monthly_tx = transactions.filter(timestamp__year=year, timestamp__month=month)
    monthly_data = {
        'total': monthly_tx.values('currency').annotate(total=Sum('amount')),
        'count': monthly_tx.count(),
        'most_sender': monthly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': monthly_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': monthly_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': monthly_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': monthly_tx.order_by('-amount').first(),
        'top_currency': monthly_tx.values('currency').annotate(total=Sum('amount')).order_by('-total').first(),
    }

    # Annual Report
    try:
        year = int(selected_year)
        annual_tx = transactions.filter(timestamp__year=year)
    except (ValueError, TypeError):
        year = now.year
        selected_year = str(year)
        annual_tx = transactions.filter(timestamp__year=year)
    annual_data = {
        'total': annual_tx.values('currency').annotate(total=Sum('amount')),
        'count': annual_tx.count(),
        'most_sender': annual_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).order_by('-total').first(),
        'least_sender': annual_tx.values('sender__first_name', 'sender__last_name', 'currency').annotate(total=Sum('amount')).filter(total__gt=0).order_by('total').first(),
        'peak_hour': annual_tx.annotate(hour=ExtractHour('timestamp')).values('hour').annotate(count=Count('id')).order_by('-count').first(),
        'status_split': annual_tx.aggregate(
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status='pending'))
        ),
        'largest_tx': annual_tx.order_by('-amount').first(),
        'growth': "Growth calculation TBD" if annual_tx.exists() else "N/A",
    }

    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Payme Transactions Report", styles['Heading1']))
    story.append(Spacer(1, 12))

    # Daily Section
    story.append(Paragraph(f"Daily Report - {selected_day}", styles['Heading2']))
    daily_total = ', '.join([f"{t['total']:.2f} {t['currency']}" for t in daily_data['total']]) if daily_data['total'] else '0.00'
    story.append(Paragraph(f"Total: {daily_total} ({daily_data['count']} tx)", styles['BodyText']))
    story.append(Paragraph(
        f"Most Sender: {daily_data['most_sender']['sender__first_name']} {daily_data['most_sender']['sender__last_name']} - {daily_data['most_sender']['total']:.2f} {daily_data['most_sender']['currency']}" 
        if daily_data['most_sender'] else "Most Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Least Sender: {daily_data['least_sender']['sender__first_name']} {daily_data['least_sender']['sender__last_name']} - {daily_data['least_sender']['total']:.2f} {daily_data['least_sender']['currency']}" 
        if daily_data['least_sender'] else "Least Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Peak Hour: {daily_data['peak_hour']['hour']}:00 - {daily_data['peak_hour']['count']} tx" 
        if daily_data['peak_hour'] else "Peak Hour: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Status Split: Completed: {daily_data['status_split']['completed']} ({(daily_data['status_split']['completed'] / daily_data['count'] * 100 if daily_data['count'] else 0):.1f}%), "
        f"Pending: {daily_data['status_split']['pending']} ({(daily_data['status_split']['pending'] / daily_data['count'] * 100 if daily_data['count'] else 0):.1f}%)",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Largest Tx: {daily_data['largest_tx'].amount:.2f} {daily_data['largest_tx'].currency} by {daily_data['largest_tx'].sender.first_name} {daily_data['largest_tx'].sender.last_name} "
        f"to {daily_data['largest_tx'].receiver.first_name} {daily_data['largest_tx'].receiver.last_name}" 
        if daily_data['largest_tx'] else "Largest Tx: N/A",
        styles['BodyText']
    ))
    story.append(Spacer(1, 12))

    # Weekly Section
    story.append(Paragraph(f"Weekly Report - {selected_week}", styles['Heading2']))
    weekly_total = ', '.join([f"{t['total']:.2f} {t['currency']}" for t in weekly_data['total']]) if weekly_data['total'] else '0.00'
    story.append(Paragraph(f"Total: {weekly_total} ({weekly_data['count']} tx)", styles['BodyText']))
    story.append(Paragraph(
        f"Most Sender: {weekly_data['most_sender']['sender__first_name']} {weekly_data['most_sender']['sender__last_name']} - {weekly_data['most_sender']['total']:.2f} {weekly_data['most_sender']['currency']}" 
        if weekly_data['most_sender'] else "Most Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Least Sender: {weekly_data['least_sender']['sender__first_name']} {weekly_data['least_sender']['sender__last_name']} - {weekly_data['least_sender']['total']:.2f} {weekly_data['least_sender']['currency']}" 
        if weekly_data['least_sender'] else "Least Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Peak Hour: {weekly_data['peak_hour']['hour']}:00 - {weekly_data['peak_hour']['count']} tx" 
        if weekly_data['peak_hour'] else "Peak Hour: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Status Split: Completed: {weekly_data['status_split']['completed']} ({(weekly_data['status_split']['completed'] / weekly_data['count'] * 100 if weekly_data['count'] else 0):.1f}%), "
        f"Pending: {weekly_data['status_split']['pending']} ({(weekly_data['status_split']['pending'] / weekly_data['count'] * 100 if weekly_data['count'] else 0):.1f}%)",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Largest Tx: {weekly_data['largest_tx'].amount:.2f} {weekly_data['largest_tx'].currency} by {weekly_data['largest_tx'].sender.first_name} {weekly_data['largest_tx'].sender.last_name} "
        f"to {weekly_data['largest_tx'].receiver.first_name} {weekly_data['largest_tx'].receiver.last_name}" 
        if weekly_data['largest_tx'] else "Largest Tx: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Busiest Day: {weekly_data['busiest_day']['year']}-{weekly_data['busiest_day']['month']:02d}-{weekly_data['busiest_day']['day']:02d} - {weekly_data['busiest_day']['total']:.2f}" 
        if weekly_data['busiest_day'] else "Busiest Day: N/A",
        styles['BodyText']
    ))
    story.append(Spacer(1, 12))

    # Monthly Section
    story.append(Paragraph(f"Monthly Report - {selected_month}", styles['Heading2']))
    monthly_total = ', '.join([f"{t['total']:.2f} {t['currency']}" for t in monthly_data['total']]) if monthly_data['total'] else '0.00'
    story.append(Paragraph(f"Total: {monthly_total} ({monthly_data['count']} tx)", styles['BodyText']))
    story.append(Paragraph(
        f"Most Sender: {monthly_data['most_sender']['sender__first_name']} {monthly_data['most_sender']['sender__last_name']} - {monthly_data['most_sender']['total']:.2f} {monthly_data['most_sender']['currency']}" 
        if monthly_data['most_sender'] else "Most Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Least Sender: {monthly_data['least_sender']['sender__first_name']} {monthly_data['least_sender']['sender__last_name']} - {monthly_data['least_sender']['total']:.2f} {monthly_data['least_sender']['currency']}" 
        if monthly_data['least_sender'] else "Least Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Peak Hour: {monthly_data['peak_hour']['hour']}:00 - {monthly_data['peak_hour']['count']} tx" 
        if monthly_data['peak_hour'] else "Peak Hour: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Status Split: Completed: {monthly_data['status_split']['completed']} ({(monthly_data['status_split']['completed'] / monthly_data['count'] * 100 if monthly_data['count'] else 0):.1f}%), "
        f"Pending: {monthly_data['status_split']['pending']} ({(monthly_data['status_split']['pending'] / monthly_data['count'] * 100 if monthly_data['count'] else 0):.1f}%)",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Largest Tx: {monthly_data['largest_tx'].amount:.2f} {monthly_data['largest_tx'].currency} by {monthly_data['largest_tx'].sender.first_name} {monthly_data['largest_tx'].sender.last_name} "
        f"to {monthly_data['largest_tx'].receiver.first_name} {monthly_data['largest_tx'].receiver.last_name}" 
        if monthly_data['largest_tx'] else "Largest Tx: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Top Currency: {monthly_data['top_currency']['currency']} - {monthly_data['top_currency']['total']:.2f}" 
        if monthly_data['top_currency'] else "Top Currency: N/A",
        styles['BodyText']
    ))
    story.append(Spacer(1, 12))

    # Annual Section
    story.append(Paragraph(f"Annual Report - {selected_year}", styles['Heading2']))
    annual_total = ', '.join([f"{t['total']:.2f} {t['currency']}" for t in annual_data['total']]) if annual_data['total'] else '0.00'
    story.append(Paragraph(f"Total: {annual_total} ({annual_data['count']} tx)", styles['BodyText']))
    story.append(Paragraph(
        f"Most Sender: {annual_data['most_sender']['sender__first_name']} {annual_data['most_sender']['sender__last_name']} - {annual_data['most_sender']['total']:.2f} {annual_data['most_sender']['currency']}" 
        if annual_data['most_sender'] else "Most Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Least Sender: {annual_data['least_sender']['sender__first_name']} {annual_data['least_sender']['sender__last_name']} - {annual_data['least_sender']['total']:.2f} {annual_data['least_sender']['currency']}" 
        if annual_data['least_sender'] else "Least Sender: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Peak Hour: {annual_data['peak_hour']['hour']}:00 - {annual_data['peak_hour']['count']} tx" 
        if annual_data['peak_hour'] else "Peak Hour: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Status Split: Completed: {annual_data['status_split']['completed']} ({(annual_data['status_split']['completed'] / annual_data['count'] * 100 if annual_data['count'] else 0):.1f}%), "
        f"Pending: {annual_data['status_split']['pending']} ({(annual_data['status_split']['pending'] / annual_data['count'] * 100 if annual_data['count'] else 0):.1f}%)",
        styles['BodyText']
    ))
    story.append(Paragraph(
        f"Largest Tx: {annual_data['largest_tx'].amount:.2f} {annual_data['largest_tx'].currency} by {annual_data['largest_tx'].sender.first_name} {annual_data['largest_tx'].sender.last_name} "
        f"to {annual_data['largest_tx'].receiver.first_name} {annual_data['largest_tx'].receiver.last_name}" 
        if annual_data['largest_tx'] else "Largest Tx: N/A",
        styles['BodyText']
    ))
    story.append(Paragraph(f"Growth: {annual_data['growth']}", styles['BodyText']))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f"attachment; filename=\"transactions_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
    return response

def admin_search_transactions(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages for a fresh look
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    return render(request, 'core/admin_search_transactions.html')

def search_transactions_api(request):
    if not request.session.get('is_admin', False):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    query = request.GET.get('q', '').strip()
    transactions = []

    if query:
        filter_conditions = (
            Q(id__iexact=query) |
            Q(sender__first_name__icontains=query) |
            Q(sender__last_name__icontains=query) |
            Q(receiver__first_name__icontains=query) |
            Q(receiver__last_name__icontains=query)
        )
        try:
            amount = float(query)
            filter_conditions |= Q(amount__exact=amount)
        except ValueError:
            pass

        results = Transaction.objects.filter(filter_conditions).select_related('sender', 'receiver')
        transactions = [
            {
                'id': t.id,
                'sender_name': f"{t.sender.first_name} {t.sender.last_name}",
                'receiver_name': f"{t.receiver.first_name} {t.receiver.last_name}",
                'amount': f"{t.amount:.2f}",
                'currency': t.currency,
                'status': t.status,
                'timestamp': t.timestamp.strftime('%Y-%m-%d %H:%M') if t.timestamp else 'N/A',
            }
            for t in results
        ]

    return JsonResponse({'transactions': transactions})

def admin_report(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Total Users (Male/Female)
    total_users = User.objects.count()
    male_users = User.objects.filter(gender='male').count()
    female_users = User.objects.filter(gender='female').count()
    new_users_month = User.objects.filter(joined_at__gte=timezone.now().replace(day=1, hour=0, minute=0, second=0)).count()

    # Total Cards
    total_cards = Card.objects.count()
    cards_per_user = User.objects.annotate(card_count=Count('cards')).order_by('-card_count')
    most_cards_user = cards_per_user.first()
    least_cards_user = cards_per_user.filter(card_count__gt=0).last()
    most_cards = (
        {'username': most_cards_user.username, 'count': most_cards_user.card_count}
        if most_cards_user else {'username': 'N/A', 'count': 0}
    )
    least_cards = (
        {'username': least_cards_user.username, 'count': least_cards_user.card_count}
        if least_cards_user else {'username': 'N/A', 'count': 0}
    )

    # Total Transactions
    transactions = Transaction.objects.all()
    total_tx_count = transactions.count()
    tx_by_currency = transactions.values('currency').annotate(total_amount=Sum('amount'), count=Count('id'))
    most_active = transactions.values('sender__username').annotate(tx_count=Count('id')).order_by('-tx_count').first() or {'sender__username': 'N/A', 'tx_count': 0}
    least_active = transactions.values('sender__username').annotate(tx_count=Count('id')).filter(tx_count__gt=0).order_by('tx_count').last() or {'sender__username': 'N/A', 'tx_count': 0}
    busiest_day = transactions.values(day=Func('timestamp', Value('YYYY-MM-DD'), function='TO_CHAR', output_field=CharField())).annotate(total=Sum('amount')).order_by('-total').first()
    avg_tx_per_user = total_tx_count / total_users if total_users else 0
    top_currency = tx_by_currency.order_by('-total_amount').first() or {'currency': 'N/A', 'total_amount': 0}
    frequent_pair = transactions.values('sender__username', 'receiver__username').annotate(count=Count('id')).order_by('-count').first()
    pending_backlog = transactions.filter(status='pending').aggregate(total=Sum('amount'))['total'] or 0

    # Complaints (Separate Contact Queries and Report Issues)
    contact_queries = Complaint.objects.filter(issue__startswith='Contact Query -')
    report_issues = Complaint.objects.filter(issue__startswith='Report Issue -')
    total_complaints = Complaint.objects.count()
    total_contact_queries = contact_queries.count()
    total_report_issues = report_issues.count()
    open_contact_queries = contact_queries.filter(status='pending').count()
    open_report_issues = report_issues.filter(status='pending').count()

    # Contacts
    contacts_per_user = User.objects.annotate(contact_count=Count('contacts')).order_by('-contact_count')
    most_contacts_user = contacts_per_user.first()
    least_contacts_user = contacts_per_user.filter(contact_count__gt=0).last()
    most_contacts = (
        {'username': most_contacts_user.username, 'count': most_contacts_user.contact_count}
        if most_contacts_user else {'username': 'N/A', 'count': 0}
    )
    least_contacts = (
        {'username': least_contacts_user.username, 'count': least_contacts_user.contact_count}
        if least_contacts_user else {'username': 'N/A', 'count': 0}
    )

    report_data = {
        'total_users': total_users,
        'male_users': male_users,
        'female_users': female_users,
        'new_users_month': new_users_month,
        'total_cards': total_cards,
        'most_cards': most_cards,
        'least_cards': least_cards,
        'total_tx_count': total_tx_count,
        'tx_by_currency': [{'currency': t['currency'], 'total': f"{t['total_amount']:.2f}", 'count': t['count']} for t in tx_by_currency],
        'most_active': {'username': most_active['sender__username'], 'tx_count': most_active['tx_count']},
        'least_active': {'username': least_active['sender__username'], 'tx_count': least_active['tx_count']},
        'busiest_day': f"{busiest_day['day']} - {busiest_day['total']:.2f}" if busiest_day else 'N/A',
        'avg_tx_per_user': f"{avg_tx_per_user:.2f} tx",
        'top_currency': f"{top_currency['currency']} - {top_currency['total_amount']:.2f}",
        'frequent_pair': f"{frequent_pair['sender__username']} -> {frequent_pair['receiver__username']} ({frequent_pair['count']} tx)" if frequent_pair else 'N/A',
        'pending_backlog': f"{pending_backlog:.2f}",
        'total_complaints': total_complaints,
        'total_contact_queries': total_contact_queries,
        'total_report_issues': total_report_issues,
        'open_contact_queries': open_contact_queries,
        'open_report_issues': open_report_issues,
        'most_contacts': most_contacts,
        'least_contacts': least_contacts,
    }

    if 'download_pdf' in request.GET:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Payme Admin Report", styles['Heading1']))
        story.append(Spacer(1, 12))

        # User Stats
        story.append(Paragraph("User Stats", styles['Heading2']))
        story.append(Paragraph(f"Total Users: {report_data['total_users']}", styles['BodyText']))
        story.append(Paragraph(f"Male Users: {report_data['male_users']}", styles['BodyText']))
        story.append(Paragraph(f"Female Users: {report_data['female_users']}", styles['BodyText']))
        story.append(Paragraph(f"New Users This Month: {report_data['new_users_month']}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Card Stats
        story.append(Paragraph("Card Stats", styles['Heading2']))
        story.append(Paragraph(f"Total Cards: {report_data['total_cards']}", styles['BodyText']))
        story.append(Paragraph(f"Most Cards: {report_data['most_cards']['username']} ({report_data['most_cards']['count']})", styles['BodyText']))
        story.append(Paragraph(f"Least Cards: {report_data['least_cards']['username']} ({report_data['least_cards']['count']})", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Transaction Stats
        story.append(Paragraph("Transaction Stats", styles['Heading2']))
        story.append(Paragraph(f"Total Transactions: {report_data['total_tx_count']}", styles['BodyText']))
        for tx in report_data['tx_by_currency']:
            story.append(Paragraph(f"{tx['currency']}: {tx['total']} ({tx['count']} tx)", styles['BodyText']))
        story.append(Paragraph(f"Most Active: {report_data['most_active']['username']} ({report_data['most_active']['tx_count']} tx)", styles['BodyText']))
        story.append(Paragraph(f"Least Active: {report_data['least_active']['username']} ({report_data['least_active']['tx_count']} tx)", styles['BodyText']))
        story.append(Paragraph(f"Busiest Day: {report_data['busiest_day']}", styles['BodyText']))
        story.append(Paragraph(f"Avg Tx per User: {report_data['avg_tx_per_user']}", styles['BodyText']))
        story.append(Paragraph(f"Top Currency: {report_data['top_currency']}", styles['BodyText']))
        story.append(Paragraph(f"Frequent Pair: {report_data['frequent_pair']}", styles['BodyText']))
        story.append(Paragraph(f"Pending Backlog: {report_data['pending_backlog']}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Complaints & Issues
        story.append(Paragraph("Complaints & Issues", styles['Heading2']))
        story.append(Paragraph(f"Total Complaints: {report_data['total_complaints']}", styles['BodyText']))
        story.append(Paragraph(f"Total Contact Queries: {report_data['total_contact_queries']}", styles['BodyText']))
        story.append(Paragraph(f"Open Contact Queries: {report_data['open_contact_queries']}", styles['BodyText']))
        story.append(Paragraph(f"Total Report Issues: {report_data['total_report_issues']}", styles['BodyText']))
        story.append(Paragraph(f"Open Report Issues: {report_data['open_report_issues']}", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Contact Stats
        story.append(Paragraph("Contact Stats", styles['Heading2']))
        story.append(Paragraph(f"Most Contacts: {report_data['most_contacts']['username']} ({report_data['most_contacts']['count']})", styles['BodyText']))
        story.append(Paragraph(f"Least Contacts: {report_data['least_contacts']['username']} ({report_data['least_contacts']['count']})", styles['BodyText']))

        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f"attachment; filename=\"admin_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
        return response

    return render(request, 'core/admin_report.html', {'report': report_data})

def admin_view_complaints(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    return render(request, 'core/admin_view_complaints.html')

def view_all_complaints(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    complaints = Complaint.objects.all().order_by('-submitted_at')
    complaint_list = []
    for c in complaints:
        issue_text = c.issue
        name = "N/A"
        email = "N/A"
        message = "N/A"
        if "Name: " in issue_text:
            name_start = issue_text.find("Name: ") + 6
            name_end = issue_text.find(",", name_start)
            name = issue_text[name_start:name_end].strip()
        if "Email: " in issue_text:
            email_start = issue_text.find("Email: ") + 7
            email_end = issue_text.find(",", email_start) if "," in issue_text[email_start:] else len(issue_text)
            email = issue_text[email_start:email_end].strip()
        if "Message: " in issue_text:
            message_start = issue_text.find("Message: ") + 9
            message = issue_text[message_start:].strip()
        elif "Issue: " in issue_text:
            message_start = issue_text.find("Issue: ") + 7
            message = issue_text[message_start:].strip()

        complaint_list.append({
            'id': c.id,
            'name': name,
            'email': email,
            'message': message,
            'submitted_time': c.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if c.submitted_at else 'N/A',
            'status': c.status,
            'answered_time': c.responded_at.strftime('%Y-%m-%d %H:%M:%S') if c.responded_at else 'N/A',
        })

    if 'download_pdf' in request.GET:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("Payme Complaints Report", styles['Heading1']))
        story.append(Spacer(1, 12))

        for complaint in complaint_list:
            story.append(Paragraph(f"ID: {complaint['id']}", styles['BodyText']))
            story.append(Paragraph(f"Name: {complaint['name']}", styles['BodyText']))
            story.append(Paragraph(f"Email: {complaint['email']}", styles['BodyText']))
            story.append(Paragraph(f"Message: {complaint['message']}", styles['BodyText']))
            story.append(Paragraph(f"Submitted Time: {complaint['submitted_time']}", styles['BodyText']))
            story.append(Paragraph(f"Status: {complaint['status']}", styles['BodyText']))
            story.append(Paragraph(f"Answered Time: {complaint['answered_time']}", styles['BodyText']))
            story.append(Spacer(1, 12))

        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f"attachment; filename=\"complaints_report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
        return response

    return render(request, 'core/view_all_complaints.html', {
        'complaints': complaint_list,
    })


def respond_complaint(request, complaint_id):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    complaint = get_object_or_404(Complaint, id=complaint_id)
    issue_text = complaint.issue
    name = "N/A"
    email = "N/A"
    message = "N/A"

    # Parse 'issue' field correctly
    if "Name: " in issue_text:
        name_start = issue_text.find("Name: ") + 6
        name_end = issue_text.find(",", name_start)
        name = issue_text[name_start:name_end].strip()

    if "Email: " in issue_text:
        email_start = issue_text.find("Email: ") + 7
        # Stop at next field (e.g., "Issue: " or "Message: ") or end
        email_end = issue_text.find("Issue: ", email_start) if "Issue: " in issue_text[email_start:] else \
                   issue_text.find("Message: ", email_start) if "Message: " in issue_text[email_start:] else len(issue_text)
        email = issue_text[email_start:email_end].strip().rstrip(',')

    if "Issue: " in issue_text:
        message_start = issue_text.find("Issue: ") + 7
        message = issue_text[message_start:].strip()
    elif "Message: " in issue_text:
        message_start = issue_text.find("Message: ") + 9
        message = issue_text[message_start:].strip()

    complaint_data = {
        'id': complaint.id,
        'name': name,
        'email': email,
        'message': message,
        'submitted_time': complaint.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if complaint.submitted_at else 'N/A',
        'status': complaint.status,
    }

    if request.method == 'POST':
        response_text = request.POST.get('response')
        if response_text:
            complaint.response = response_text
            complaint.responded_at = timezone.now()
            complaint.status = 'responded'
            complaint.save()

            if email != "N/A":
                try:
                    send_mail(
                        'Response to Your Payme Complaint',
                        f"Dear {name},\n\nYour complaint (ID: {complaint.id}) has been responded to:\n\nComplaint: {message}\nResponse: {response_text}\n\nThanks for reaching out!\nPayme Team",
                        'paymebot7@gmail.com',
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, "Response saved and email sent! Check their inbox or spam, bro! 🎉")
                except Exception as e:
                    messages.error(request, f"Response saved, but email failed! Error: {str(e)} 😬")
            else:
                messages.success(request, "Response saved! No email provided to send, bro! 🎉")

            # Stay on page with updated data
            complaint_data['response'] = complaint.response
            complaint_data['answered_time'] = complaint.responded_at.strftime('%Y-%m-%d %H:%M:%S') if complaint.responded_at else 'N/A'
            complaint_data['status'] = complaint.status
            return render(request, 'core/respond_complaint.html', {'complaint': complaint_data})
        else:
            messages.error(request, "Type a response, dude! 😬")

    return render(request, 'core/respond_complaint.html', {'complaint': complaint_data})


def sort_complaints(request):
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    # Clear messages
    storage = messages.get_messages(request)
    if storage:
        for _ in storage:
            pass
        storage.used = True

    # Sort options with labels and emojis
    sort_options = [
        {'value': 'name_asc', 'label': 'Name (A-Z)', 'emoji': '🔤'},
        {'value': 'name_desc', 'label': 'Name (Z-A)', 'emoji': '🔤'},
        {'value': 'submitted_at_desc', 'label': 'Newest First', 'emoji': '🕒'},
        {'value': 'submitted_at_asc', 'label': 'Oldest First', 'emoji': '🕒'},
        {'value': 'status_pending', 'label': 'Pending First', 'emoji': '⏳'},
        {'value': 'status_responded', 'label': 'Responded First', 'emoji': '✅'},
        {'value': 'type_contact', 'label': 'Contact Query First', 'emoji': '📧'},
        {'value': 'type_report', 'label': 'Report Issue First', 'emoji': '⚠️'},
    ]
    sort_by = request.GET.get('sort_by', 'submitted_at_desc')  # Default: newest first
    sort_label = next((opt['label'] for opt in sort_options if opt['value'] == sort_by), 'Newest First')

    # Fetch and parse complaints
    complaints = Complaint.objects.all()
    complaint_list = []
    for c in complaints:
        issue_text = c.issue
        name = "N/A"
        email = "N/A"
        message = "N/A"
        complaint_type = "Contact Query" if "Contact Query" in issue_text else "Report Issue"

        if "Name: " in issue_text:
            name_start = issue_text.find("Name: ") + 6
            name_end = issue_text.find(",", name_start)
            name = issue_text[name_start:name_end].strip()
        if "Email: " in issue_text:
            email_start = issue_text.find("Email: ") + 7
            email_end = issue_text.find("Issue: ", email_start) if "Issue: " in issue_text[email_start:] else \
                       issue_text.find("Message: ", email_start) if "Message: " in issue_text[email_start:] else len(issue_text)
            email = issue_text[email_start:email_end].strip().rstrip(',')
        if "Issue: " in issue_text:
            message_start = issue_text.find("Issue: ") + 7
            message = issue_text[message_start:].strip()
        elif "Message: " in issue_text:
            message_start = issue_text.find("Message: ") + 9
            message = issue_text[message_start:].strip()

        complaint_list.append({
            'id': c.id,
            'name': name,
            'email': email,
            'message': message,
            'submitted_time': c.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if c.submitted_at else 'N/A',
            'status': c.status,
            'answered_time': c.responded_at.strftime('%Y-%m-%d %H:%M:%S') if c.responded_at else 'N/A',
            'type': complaint_type,
            'submitted_at': c.submitted_at,  # For sorting
        })

    # Sort the list
    if sort_by == 'name_asc':
        complaint_list.sort(key=lambda x: x['name'].lower())
    elif sort_by == 'name_desc':
        complaint_list.sort(key=lambda x: x['name'].lower(), reverse=True)
    elif sort_by == 'submitted_at_asc':
        complaint_list.sort(key=lambda x: x['submitted_at'] if x['submitted_at'] else timezone.datetime.min)
    elif sort_by == 'submitted_at_desc':
        complaint_list.sort(key=lambda x: x['submitted_at'] if x['submitted_at'] else timezone.datetime.min, reverse=True)
    elif sort_by == 'status_pending':
        complaint_list.sort(key=lambda x: x['status'] != 'pending')  # Pending first
    elif sort_by == 'status_responded':
        complaint_list.sort(key=lambda x: x['status'] != 'responded')  # Responded first
    elif sort_by == 'type_contact':
        complaint_list.sort(key=lambda x: x['type'] != 'Contact Query')  # Contact Query first
    elif sort_by == 'type_report':
        complaint_list.sort(key=lambda x: x['type'] != 'Report Issue')  # Report Issue first

    # Handle PDF download
    if 'download_pdf' in request.GET:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Payme Complaints Sorted by {sort_label}", styles['Heading1']))
        story.append(Spacer(1, 12))

        for complaint in complaint_list:
            story.append(Paragraph(f"ID: {complaint['id']}", styles['BodyText']))
            story.append(Paragraph(f"Name: {complaint['name']}", styles['BodyText']))
            story.append(Paragraph(f"Email: {complaint['email']}", styles['BodyText']))
            story.append(Paragraph(f"Message: {complaint['message']}", styles['BodyText']))
            story.append(Paragraph(f"Type: {complaint['type']}", styles['BodyText']))
            story.append(Paragraph(f"Submitted Time: {complaint['submitted_time']}", styles['BodyText']))
            story.append(Paragraph(f"Status: {complaint['status']}", styles['BodyText']))
            story.append(Paragraph(f"Answered Time: {complaint['answered_time']}", styles['BodyText']))
            story.append(Spacer(1, 12))

        doc.build(story)
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f"attachment; filename=\"sorted_complaints_{sort_by}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf\""
        return response

    return render(request, 'core/sort_complaints.html', {
        'complaints': complaint_list,
        'sort_by': sort_by,
        'sort_label': sort_label,
        'sort_options': sort_options,
    })


def backup_database(request):
    """Stream a full Postgres database backup as an SQL file."""
    if not request.session.get('is_admin', False):
        messages.error(request, "You’re not the boss! Log in first! 😬")
        return redirect('admin_login')

    if request.method == 'POST':
        try:
            # Get DB settings
            db_settings = settings.DATABASES['default']
            db_name = db_settings['NAME']
            db_user = db_settings.get('USER', '')
            db_password = db_settings.get('PASSWORD', '')
            db_host = db_settings.get('HOST', 'localhost')  # Local default
            db_port = str(db_settings.get('PORT', '5432'))

            # Filename with timestamp
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"payme_backup_{timestamp}.sql"

            # pg_dump command
            command = [
                'pg_dump',
                '-U', db_user,
                '-h', db_host,
                '-p', db_port,
                db_name
            ]

            # Set password in env
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password

            # Stream the backup
            def generate_backup():
                process = subprocess.Popen(
                    command,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=False
                )
                for chunk in iter(process.stdout.readline, b''):
                    yield chunk
                process.wait()
                if process.returncode != 0:
                    error = process.stderr.read().decode('utf-8', errors='replace')
                    raise Exception(f"pg_dump failed: {error}")

            # Send streaming response
            response = StreamingHttpResponse(
                generate_backup(),
                content_type='application/sql'
            )
            response['Content-Disposition'] = f'attachment; filename="{backup_file}"'
            messages.success(request, "Backup downloaded, bro! Check your files! 🚀")
            return response

        except Exception as e:
            messages.error(request, f"Backup crashed, dude! Error: {str(e)} 😬")
            return redirect('dashboard')

    return render(request, 'core/backup_database.html')

# Update admin_logout view (replace existing)
def admin_logout(request):
    if request.session.get('is_admin'):
        del request.session['is_admin']
        # No message on logout
    return redirect('home')