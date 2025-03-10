




'''

(.venv) D:\100 great python projects\PaymeBot Django\paymebot>curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzQxNDcyNjYzLCJpYXQiOjE3NDE0NzIzNjMsImp0aSI6IjBlYzQyN2FkZTBiZTRhMWQ4OGI0YWMyMzk5MjZmN2NjIiwidXNlcl9pZCI6MX0.aT3BAcNBJRgouIOOfU5oSSAZqkBV8siReofVqRQGdrE" http://localhost:8000/api/profile/
{"id":1,"username":"bahtiyorjon","first_name":"Admin","last_name":"Tolipov","email":null,"age":null,"gender":"male","phone_number":"","default_currency":"USD","two_factor_code":null,"is_blocked":false,"last_activity":"2025-02-27T06:26:20.105990Z"}
(.venv) D:\100 great python projects\PaymeBot Django\paymebot>


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'age', 'gender', 'phone_number',
            'default_currency', 'two_factor_code', 'password', 'is_blocked', 'last_activity'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'two_factor_code': {'read_only': True},
            'is_blocked': {'read_only': True},
            'last_attempt_time': {'read_only': True}
        }




i changed to last activity boy because it gave error for last attempt time because thats not in user class in models file idiot

'''