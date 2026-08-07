from django.apps import AppConfig


class CameraConfig(AppConfig):
    name = 'camera'

    def ready(self):
        import camera.schema  # noqa: F401 - registers drf_spectacular auth extensions
