"""
drf_spectacular auth scheme registrations for the camera API's custom
authenticators.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object


class CameraJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'camera.authentication.CameraJWTAuthentication'
    name = 'cameraJwtAuth'

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object(
            header_name='Authorization',
            token_prefix='Bearer',
            bearer_format='JWT',
        )


class CameraTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'camera.authentication.CameraTokenAuthentication'
    name = 'cameraDeviceAuth'

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object(
            header_name='Authorization',
            token_prefix='Device',
            bearer_format=None,
        )
