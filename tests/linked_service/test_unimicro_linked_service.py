"""
**File:** ``test_unimicro_linked_service.py``
**Region:** ``tests/linked_service/test_unimicro_linked_service``

Linked Service tests for Unimicro provider.
"""

import base64
import uuid
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePrivateKey,
)
from cryptography.hazmat.primitives.asymmetric.ec import (
    generate_private_key as generate_ec_private_key,
)
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, generate_private_key
from cryptography.hazmat.primitives.serialization import NoEncryption, pkcs12
from ds_protocol_http_py_lib.enums import AuthType
from ds_protocol_http_py_lib.utils.http import Http
from ds_resource_plugin_py_lib.common.resource.linked_service.errors import (
    AuthenticationError,
)

from ds_provider_unimicro_py_lib.enums import ResourceType
from ds_provider_unimicro_py_lib.linked_service.unimicro import (
    UnimicroLinkedService,
    UnimicroLinkedServiceSettings,
)


def make_certificate(
    private_key: RSAPrivateKey | EllipticCurvePrivateKey,
    quoted: bool = False,
) -> str:
    p12_data = pkcs12.serialize_key_and_certificates(
        name=b"unimicro-client",
        key=private_key,
        cert=None,
        cas=None,
        encryption_algorithm=NoEncryption(),
    )

    certificate = base64.b64encode(p12_data).decode("ascii")
    return f'"{certificate}"' if quoted else certificate


def make_settings(certificate: str) -> UnimicroLinkedServiceSettings:
    return UnimicroLinkedServiceSettings(
        certificate=certificate,
        certificate_password="",
        client_id="client-id",
    )


def make_service(settings: UnimicroLinkedServiceSettings) -> UnimicroLinkedService:
    with patch.object(
        UnimicroLinkedService,
        "_get_token_endpoint",
        return_value="https://login.unimicro.no/connect/token",
    ):
        return UnimicroLinkedService(
            id=uuid.uuid4(),
            name="unimicro",
            version="v1.0.0",
            settings=settings,
        )


def test_extracts_rsa_private_key() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    service = make_service(make_settings(make_certificate(private_key)))

    extracted_key = service._get_private_key()

    assert isinstance(extracted_key, RSAPrivateKey)
    assert extracted_key.private_numbers() == private_key.private_numbers()


def test_creates_valid_client_token() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    service = make_service(make_settings(make_certificate(private_key)))

    token = service._create_client_token("client-id", private_key, "https://login.unimicro.no/connect/token")

    claims = jwt.decode(
        token,
        private_key.public_key(),
        algorithms=["RS256"],
        audience="https://login.unimicro.no/connect/token",
        issuer="client-id",
    )

    assert claims["sub"] == "client-id"
    assert claims["iss"] == "client-id"
    assert claims["aud"] == "https://login.unimicro.no/connect/token"


def test_configures_company_key_and_custom_auth() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = make_settings(make_certificate(private_key))

    with (
        patch.object(
            UnimicroLinkedService,
            "_get_token_endpoint",
            return_value="https://login.unimicro.no/connect/token",
        ),
        patch.object(
            UnimicroLinkedService,
            "_get_private_key",
            return_value=private_key,
        ),
    ):
        service = make_service(settings)

    assert service.settings.auth_type == AuthType.CUSTOM
    assert service.settings.custom is not None
    assert service.settings.custom.token_endpoint == "https://login.unimicro.no/connect/token"
    assert service.settings.custom.data is not None
    assert service.settings.custom.data["client_id"] == "client-id"


def test_extracts_private_key_from_quoted_certificate() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    certificate = make_certificate(private_key, quoted=True)
    service = make_service(make_settings(certificate))

    extracted_key = service._get_private_key()

    assert extracted_key.private_numbers() == private_key.private_numbers()


def test_does_not_configure_custom_auth_for_no_auth() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = make_settings(make_certificate(private_key))
    settings.auth_type = AuthType.NO_AUTH

    with patch.object(
        UnimicroLinkedService,
        "_get_token_endpoint",
        return_value="https://login.unimicro.no/connect/token",
    ):
        service = make_service(settings)

    assert service.settings.custom is None


def test_raises_authentication_error_when_certificate_decoding_fails() -> None:
    settings = make_settings("certificate")
    settings_object = object.__new__(UnimicroLinkedService)
    settings_object.settings = settings

    with (
        patch.object(
            base64,
            "b64decode",
            side_effect=ValueError("invalid certificate"),
        ),
        pytest.raises(AuthenticationError, match="Failed to base64-decode certificate"),
    ):
        settings_object._get_private_key()


def test_raises_authentication_error_when_pkcs12_loading_fails() -> None:
    settings = make_settings("valid-looking-certificate")
    service = object.__new__(UnimicroLinkedService)
    service.settings = settings

    with (
        patch.object(base64, "b64decode", return_value=b"invalid-pkcs12"),
        patch.object(
            pkcs12,
            "load_key_and_certificates",
            side_effect=ValueError("invalid PKCS12 data"),
        ),
        pytest.raises(
            AuthenticationError,
            match=r"Failed to load private key from the certificate\.",
        ),
    ):
        service._get_private_key()


def test_configures_custom_auth() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = make_settings(make_certificate(private_key))

    with (
        patch.object(
            UnimicroLinkedService,
            "_get_token_endpoint",
            return_value="https://login.unimicro.no/connect/token",
        ),
        patch.object(
            UnimicroLinkedService,
            "_get_private_key",
            return_value=private_key,
        ),
    ):
        service = make_service(settings)

    assert service.settings.custom is not None


def test_rejects_non_rsa_private_key() -> None:
    private_key = generate_ec_private_key(SECP256R1())
    settings = make_settings(make_certificate(private_key))

    with pytest.raises(AuthenticationError):
        make_service(settings)


def test_gets_token_endpoint() -> None:
    settings = make_settings("unused")
    service = object.__new__(UnimicroLinkedService)
    service.settings = settings

    response = Mock()
    response.json.return_value = {
        "token_endpoint": "https://login.unimicro.no/connect/token",
    }

    with patch.object(Http, "get", return_value=response) as get:
        token_endpoint = service._get_token_endpoint()

    get.assert_called_once_with(url="https://login.unimicro.no/.well-known/openid-configuration")
    assert token_endpoint == "https://login.unimicro.no/connect/token"


def test_connect_sends_form_encoded_custom_auth_request() -> None:
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = make_settings(make_certificate(private_key))
    service = make_service(settings)

    response = Mock()
    response.json.return_value = {"access_token": "test-access-token"}

    with patch.object(Http, "post", return_value=response) as post:
        service.connect()

    assert service.type == ResourceType.UNIMICRO_LINKED_SERVICE
    post.assert_called_once_with(
        url="https://login.unimicro.no/connect/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
        data=service.settings.custom.data,
    )
    assert "Content-Type" not in service.connection.session.headers
