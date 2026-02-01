from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.conf import settings
import hashlib


class CacheMiddleware(MiddlewareMixin):
    """
    Custom caching middleware to improve performance
    """
    def process_request(self, request):
        # Skip caching for authenticated users and POST requests
        if request.user.is_authenticated or request.method == 'POST':
            return None
            
        # Create cache key based on path and query parameters
        cache_key = f"page_cache_{hashlib.md5(request.get_full_path().encode()).hexdigest()}"
        
        # Try to get cached response
        cached_response = cache.get(cache_key)
        if cached_response:
            return cached_response
            
        # Store cache key in request for later use
        request.cache_key = cache_key
        return None

    def process_response(self, request, response):
        # Cache response if cache key exists and response is OK
        if hasattr(request, 'cache_key') and response.status_code == 200:
            # Don't cache if user is authenticated
            if not request.user.is_authenticated:
                cache.set(request.cache_key, response, 60 * 15)  # Cache for 15 minutes
        
        return response


class PerformanceMonitoringMiddleware(MiddlewareMixin):
    """
    Middleware to monitor performance and log slow requests
    """
    def process_request(self, request):
        import time
        request.start_time = time.time()
        return None

    def process_response(self, request, response):
        import time
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            if duration > 1.0:  # Log requests taking more than 1 second
                import logging
                logger = logging.getLogger('performance')
                logger.warning(f'Slow request: {request.path} took {duration:.2f}s')
        
        return response