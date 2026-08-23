from django.conf import settings


def application_version(request):
    return {"application_version": settings.APP_VERSION}
