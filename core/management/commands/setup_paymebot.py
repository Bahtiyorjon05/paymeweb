from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
import os

User = get_user_model()

class Command(BaseCommand):
    help = 'Setup initial configuration for PaymeBot'

    def handle(self, *args, **options):
        self.stdout.write('Setting up PaymeBot...')
        
        # Create superuser if doesn't exist
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        if not User.objects.filter(username=admin_username).exists():
            admin_password = os.environ.get('ADMIN_DEFAULT_PASSWORD', 'admin123')
            User.objects.create_superuser(admin_username, 'admin@example.com', admin_password)
            self.stdout.write(
                self.style.SUCCESS(f'Superuser "{admin_username}" created successfully!')
            )
        else:
            self.stdout.write(f'Superuser "{admin_username}" already exists.')
        
        # Create logs directory if it doesn't exist
        if hasattr(settings, 'BASE_DIR'):
            logs_dir = settings.BASE_DIR / 'logs'
            logs_dir.mkdir(exist_ok=True)
            self.stdout.write(
                self.style.SUCCESS('Logs directory created/verified successfully!')
            )
        
        self.stdout.write(
            self.style.SUCCESS('PaymeBot setup completed successfully!')
        )