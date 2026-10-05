"""
**File:** ``unimicro.py``
**Region:** ``ds_provider_unimicro_py_lib/linked_service/unimicro``

Unimicro Linked Service.

This module defines the Unimicro linked service, which is used to connect
to the Unimicro API. It includes the necessary configuration and
authentication details required to establish a connection with the Unimicro service.

Example:
    >>> from uuid import UUID
    >>> linked_service = UnimicroLinkedService(
    ...     id=UUID("52fa4cf5-c1c6-45b1-aaca-3b02206302de"),
    ...     name="unimicro-linked-service",
    ...     version="v1.0.0",
    ...     settings=UnimicroLinkedServiceSettings(
    ...
    ...     ),
    ... )
    >>> linked_service.connect()
"""

import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar, cast

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import pkcs12
from ds_common_logger_py_lib import Logger
from ds_protocol_http_py_lib import HttpLinkedService, HttpLinkedServiceSettings
from ds_protocol_http_py_lib.enums import AuthType
from ds_protocol_http_py_lib.linked_service import CustomAuthSettings
from ds_protocol_http_py_lib.utils.http import Http
from ds_resource_plugin_py_lib.common.resource.linked_service.errors import (
    AuthenticationError,
)

from ..enums import ResourceType

logger = Logger.get_logger(__name__, package=True)


@dataclass(kw_only=True)
class UnimicroLinkedServiceSettings(HttpLinkedServiceSettings):
    """
    Unimicro linked service settings.

    This class extends the HttpLinkedServiceSettings and includes the necessary
    configuration for connecting to the Unimicro API.
    """

    certificate: str = field(metadata={"mask": True})
    """Base64-encoded PKCS#12 certificate used for authentication."""

    certificate_password: str = field(metadata={"mask": True})
    """The password for the certificate used for authenticating with the Unimicro API."""

    client_id: str
    """The client ID for the Unimicro API."""

    company_key: str | None = None
    """The company key used for fetching data from Unimicro."""

    scope: str = "AppFramework"
    """The scope for the Unimicro API authentication."""

    auth_url: str = "https://login.unimicro.no"
    """The URL for the Unimicro authentication service used for authentication."""

    host: str = "https://app.unimicro.no"
    """The URL for the Unimicro API host."""

    auth_type: AuthType = AuthType.CUSTOM
    """Authentication type for Unimicro API."""

    custom: CustomAuthSettings | None = None
    """Custom authentication settings for Unimicro API."""


UnimicroLinkedServiceSettingsType = TypeVar("UnimicroLinkedServiceSettingsType", bound=UnimicroLinkedServiceSettings)


@dataclass(kw_only=True)
class UnimicroLinkedService(HttpLinkedService[UnimicroLinkedServiceSettingsType], Generic[UnimicroLinkedServiceSettingsType]):
    """
    Unimicro linked service.

    This class represents the Unimicro linked service, which is used to connect
    to the Unimicro API. It extends the HttpLinkedService and uses the
    UnimicroLinkedServiceSettings for its configuration.
    """

    settings: UnimicroLinkedServiceSettingsType
    """The settings for the Unimicro linked service."""

    @property
    def type(self) -> ResourceType:  # type: ignore[override]
        """
        Get the resource type for Unimicro linked service.

        Returns:
            ResourceType: The resource type for Unimicro linked service.
        """
        return ResourceType.UNIMICRO_LINKED_SERVICE

    def __post_init__(self) -> None:
        """
        Post-initialization for the Unimicro linked service.

        This method is called after the dataclass is initialized. It can be used
        to perform any additional setup or validation for the Unimicro linked service.
        """
        self.settings.headers = {
            **(self.settings.headers or {}),
        }
        if self.settings.auth_type == AuthType.CUSTOM:
            token_endpoint = self._get_token_endpoint()
            client_token = self._create_client_token(
                client_id=self.settings.client_id, private_key=self._get_private_key(), token_endpoint=token_endpoint
            )
            data = {
                "grant_type": "client_credentials",
                "scope": self.settings.scope,
                "client_id": self.settings.client_id,
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": client_token,
            }
            self.settings.custom = CustomAuthSettings(token_endpoint=token_endpoint, data=data)
        super().__post_init__()

    def _configure_custom_auth(self, http: Http) -> None:
        original_headers = self.settings.headers
        self.settings.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            super()._configure_custom_auth(http)
        finally:
            self.settings.headers = original_headers

        if self.settings.company_key:
            company_header = {"CompanyKey": self.settings.company_key}
            self.settings.headers = {**(original_headers or {}), **company_header}
            http.session.headers.update(company_header)

    def _get_private_key(self) -> RSAPrivateKey:
        """
        Get the private key used for authenticating with the Unimicro API.
        The certificate and certificate password are used to generate the private key for authentication.

        Returns:
            RSAPrivateKey: The private key used for authentication.
        """
        try:
            certificate = self.settings.certificate.strip('"')
            decoded_certificate = base64.b64decode(certificate)
        except Exception as exc:
            logger.error("Failed to base64-decode certificate: %s", exc)
            raise AuthenticationError(
                message="Failed to base64-decode certificate.",
                details={"company_key": self.settings.company_key},
            ) from exc

        certificate_password = self.settings.certificate_password
        password_bytes = certificate_password.encode("utf-8") if certificate_password else None

        try:
            private_key, _cert, _chain = pkcs12.load_key_and_certificates(decoded_certificate, password_bytes)
        except (ValueError, TypeError) as exc:
            logger.error("Failed to load private key from the certificate: %s", exc)
            raise AuthenticationError(
                message="Failed to load private key from the certificate.",
                details={"company_key": self.settings.company_key},
            ) from exc

        if not isinstance(private_key, RSAPrivateKey):
            logger.error("No RSA private key found in the certificate.")
            raise AuthenticationError(
                message="The certificate does not contain an RSA private key.",
                details={
                    "company_key": self.settings.company_key,
                },
            )

        return private_key

    def _create_client_token(self, client_id: str, private_key: RSAPrivateKey, token_endpoint: str) -> str:
        """
        Create a client token for the Unimicro API using the provided client ID and private key.

        Args:
            client_id (str): The client ID for the Unimicro API.
            private_key (RSAPrivateKey): The private key used for authentication.
            token_endpoint (str): The token endpoint URL for the Unimicro API.

        Returns:
            str: The generated client token.
        """
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=1)

        payload = {
            "jti": str(uuid.uuid4()),
            "sub": client_id,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "iss": client_id,
            "aud": token_endpoint,
        }

        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token

    def _get_token_endpoint(self) -> str:
        """
        Get the token endpoint URL for the Unimicro API.

        Returns:
            str: The token endpoint URL.
        """
        with Http() as http:
            response = http.get(url=f"{self.settings.auth_url}/.well-known/openid-configuration")
        discovery = response.json()
        return cast("str", discovery["token_endpoint"])
