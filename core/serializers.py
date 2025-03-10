from rest_framework import serializers
from .models import User, Card, Contact, Transaction, Complaint

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'age', 'gender', 'phone_number',
            'default_currency', 'two_factor_code', 'is_blocked', 'is_superuser', 'is_staff',
            'joined_at', 'block_until', 'last_activity'
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': True},  # Password only for creation
            'two_factor_code': {'read_only': True},
            'is_blocked': {'read_only': True},
            'is_superuser': {'read_only': True},
            'is_staff': {'read_only': True},
            'joined_at': {'read_only': True},  # Auto-set by model
            'last_activity': {'read_only': True},  # Auto-managed
        }

    def create(self, validated_data):
        """
        Create a new user with hashed password and required fields.
        """
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email'),  # Optional
            phone_number=validated_data['phone_number'],  # Required by model
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            age=validated_data.get('age'),
            gender=validated_data.get('gender'),
            default_currency=validated_data.get('default_currency', 'USD')
        )
        return user

    def update(self, instance, validated_data):
        """
        Update user, restrict admin fields to superusers, hash password if provided.
        """
        if not self.context['request'].user.is_superuser:
            validated_data.pop('is_superuser', None)
            validated_data.pop('is_staff', None)
            validated_data.pop('is_blocked', None)  # Extra safety
            validated_data.pop('two_factor_code', None)
        if 'password' in validated_data:
            instance.set_password(validated_data.pop('password'))
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

class CardSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Card
        fields = ['id', 'user', 'card_number', 'balance', 'password', 'created_at', 'currency']
        extra_kwargs = {
            'password': {'write_only': True, 'required': True},
            'created_at': {'read_only': True},
            'balance': {'read_only': True},  # Shouldn’t be set directly
        }

    def validate_card_number(self, value):
        """Ensure card_number is unique and valid length."""
        if len(value) < 16 or len(value) > 19:
            raise serializers.ValidationError("Card number must be 16-19 digits.")
        return value

class ContactSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    contact_user = UserSerializer(source='contact_user', read_only=True)  # Match model field

    class Meta:
        model = Contact
        fields = ['id', 'user', 'contact_user', 'added_at']
        extra_kwargs = {
            'added_at': {'read_only': True},
        }

    def validate(self, data):
        """Prevent self-contact."""
        if self.context['request'].user == data['contact_user']:
            raise serializers.ValidationError("You cannot add yourself as a contact.")
        return data

class TransactionSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    sender_card = CardSerializer(read_only=True)
    receiver_card = CardSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            'id', 'sender', 'receiver', 'sender_card', 'receiver_card', 'amount', 'currency',
            'received_amount', 'received_currency', 'timestamp', 'status'
        ]
        extra_kwargs = {
            'timestamp': {'read_only': True},
            'status': {'read_only': True},  # Managed by logic, not client
        }

    def validate(self, data):
        """Ensure sender isn’t receiver and amount is positive."""
        if data['sender'] == data['receiver']:
            raise serializers.ValidationError("Sender and receiver cannot be the same.")
        if data['amount'] <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return data

class ComplaintSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Complaint
        fields = ['id', 'user', 'issue', 'submitted_at', 'status', 'response', 'responded_at']
        extra_kwargs = {
            'submitted_at': {'read_only': True},
            'status': {'read_only': True},  # Admin-managed
            'response': {'read_only': True},  # Admin-managed
            'responded_at': {'read_only': True},
        }

    def validate_issue(self, value):
        """Ensure issue isn’t empty or too short."""
        if not value or len(value.strip()) < 5:
            raise serializers.ValidationError("Complaint issue must be at least 5 characters.")
        return value