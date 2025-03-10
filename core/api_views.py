



from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.db import models
from .models import User, Card, Contact, Transaction, Complaint
from .serializers import UserSerializer, CardSerializer, ContactSerializer, TransactionSerializer, ComplaintSerializer

def get_object_or_404(queryset, **kwargs):
    try:
        return queryset.get(**kwargs)
    except queryset.model.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserSignupAPIView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CardListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cards = Card.objects.filter(user=request.user)
        serializer = CardSerializer(cards, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = CardSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CardDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, card_id):
        card = get_object_or_404(Card.objects.filter(user=request.user), id=card_id)
        if isinstance(card, Response):
            return card
        card.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class ContactListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contacts = Contact.objects.filter(user=request.user)
        serializer = ContactSerializer(contacts, many=True)
        return Response(serializer.data)

    def post(self, request):
        contact_username = request.data.get('contact_username')
        try:
            contact_user = User.objects.get(username=contact_username)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        data = {'user': request.user.id, 'contact': contact_user.id}
        serializer = ContactSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ContactDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, contact_id):
        contact = get_object_or_404(Contact.objects.filter(user=request.user), id=contact_id)
        if isinstance(contact, Response):
            return contact
        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class TransactionListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = Transaction.objects.filter(models.Q(sender=request.user) | models.Q(receiver=request.user))
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['sender'] = request.user.id
        serializer = TransactionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ComplaintListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_staff:
            complaints = Complaint.objects.all()
        else:
            complaints = Complaint.objects.filter(user=request.user)
        serializer = ComplaintSerializer(complaints, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['user'] = request.user.id
        serializer = ComplaintSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ComplaintDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def put(self, request, complaint_id):
        complaint = get_object_or_404(Complaint.objects.all(), id=complaint_id)
        if isinstance(complaint, Response):
            return complaint
        serializer = ComplaintSerializer(complaint, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)