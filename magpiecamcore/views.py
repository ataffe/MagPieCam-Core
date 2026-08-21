from django.db import connection
from django.http import JsonResponse
import redis
from django.conf import settings

def health_check(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT).ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(checks, status=200 if healthy else 503)