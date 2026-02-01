

from django import forms
from .models import User, Card, Contact
import phonenumbers
from django.contrib.auth import authenticate


class SignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")
    age = forms.IntegerField(required=True, label="Age")  

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'age', 'gender', 'username', 'phone_number', 'password']

    def clean_first_name(self):
        first_name = self.cleaned_data['first_name']
        if not first_name.isalpha():
            raise forms.ValidationError("First name must contain only letters!")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data['last_name']
        if not last_name.isalpha():
            raise forms.ValidationError("Last name must contain only letters!")
        return last_name

    def clean_age(self):
        age = self.cleaned_data['age']
        if age is None:  # Double-check for None
            raise forms.ValidationError("Age is required!")
        if age < 13 or age > 120:
            raise forms.ValidationError("Age must be between 13 and 120!")
        return age

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        try:
            parsed = phonenumbers.parse(phone_number)
            if not phonenumbers.is_valid_number(parsed):
                raise forms.ValidationError("Invalid phone number!")
        except phonenumbers.NumberParseException:
            raise forms.ValidationError("Invalid phone number format!")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        if password:
            password = password.strip()
            cleaned_data['password'] = password
            
        confirm_password = cleaned_data.get('confirm_password')
        if confirm_password:
            confirm_password = confirm_password.strip()
            cleaned_data['confirm_password'] = confirm_password
            
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match!")
        return cleaned_data
    
class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        
        if username: username = username.strip()
        if password: password = password.strip()
        
        user = authenticate(username=username, password=password)
        if user is None:
            raise forms.ValidationError("Invalid username or password!")
        return cleaned_data

class AddCardForm(forms.ModelForm):
    card_number = forms.CharField(max_length=19, min_length=13)
    password = forms.CharField(max_length=6, min_length=6, widget=forms.PasswordInput)

    class Meta:
        model = Card
        fields = ['card_number', 'password']

    def clean_card_number(self):
        card_number = self.cleaned_data['card_number']
        # Remove hyphens for validation
        cleaned_card = card_number.replace('-', '')
        if not cleaned_card.isdigit():
            raise forms.ValidationError("Card number must contain only digits!")
        digits = len(cleaned_card)
        if not (13 <= digits <= 19):
            raise forms.ValidationError("Card number must be 13-19 digits!")
        if Card.objects.filter(card_number=card_number).exists():
            raise forms.ValidationError("This card number already exists.")
        # Luhn check
        if not self.luhn_check(cleaned_card):
            raise forms.ValidationError("Invalid card number!")
        return card_number

    def clean_password(self):
        password = self.cleaned_data['password']
        if not password.isdigit():
            raise forms.ValidationError("Password must be a 6-digit number!")
        return password

    def luhn_check(self, card_number):
        digits = [int(d) for d in card_number]
        checksum = 0
        is_even = False
        for digit in digits[::-1]:  # Reverse order
            if is_even:
                doubled = digit * 2
                checksum += doubled if doubled <= 9 else doubled - 9
            else:
                checksum += digit
            is_even = not is_even
        return checksum % 10 == 0
    
class AddMoneyForm(forms.Form):
    card = forms.ModelChoiceField(queryset=None, empty_label=None)
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['card'].queryset = Card.objects.filter(user=user)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be a positive number!")
        return amount
    
class RemoveCardForm(forms.Form):
    card = forms.ModelChoiceField(queryset=None, empty_label=None)
    password = forms.CharField(max_length=6, min_length=6, widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['card'].queryset = Card.objects.filter(user=user)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not password.isdigit():
            raise forms.ValidationError("Password must be a 6-digit number!")
        return password

class SendMoneyToContactForm(forms.Form):
    receiver = forms.ModelChoiceField(queryset=Contact.objects.none(), label="Send to")
    sender_card = forms.ModelChoiceField(queryset=Card.objects.none(), label="From Card")
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01, label="Amount")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['receiver'].queryset = Contact.objects.filter(user=user)
        self.fields['sender_card'].queryset = Card.objects.filter(user=user)


class SendMoneyToCardForm(forms.Form):
    receiver_card_number = forms.CharField(max_length=19, min_length=13)
    sender_card = forms.ModelChoiceField(queryset=None, empty_label=None)
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sender_card'].queryset = Card.objects.filter(user=user)
    def clean_receiver_card_number(self):
        card_number = self.cleaned_data['receiver_card_number']
        if not card_number.replace('-', '').isdigit():
            raise forms.ValidationError("Card number must contain only digits!")
        digits = len(card_number.replace('-', ''))
        if not (13 <= digits <= 19):
            raise forms.ValidationError("Card number must be 13-19 digits!")
        return card_number
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        sender_card = self.cleaned_data['sender_card']
        if amount > sender_card.balance:
            raise forms.ValidationError("Amount exceeds card balance!")
        return amount