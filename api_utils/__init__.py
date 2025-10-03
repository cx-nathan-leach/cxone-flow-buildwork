from .signatures import signature
from .auth_factories import AuthFactory, StaticAuthFactory
from requests.auth import HTTPBasicAuth
from .bearer import HTTPBearerAuth
from typing import Tuple
import urllib


def auth_basic(username, password) -> AuthFactory:
    return StaticAuthFactory(HTTPBasicAuth(username, password))

def auth_bearer(token) -> AuthFactory:
    return StaticAuthFactory(HTTPBearerAuth(token))

def gen_signature_hash(algorithm : str, secret : str, body : str) -> str:
    import hashlib

    if not algorithm in hashlib.algorithms_available:
        raise NotImplementedError(algorithm)

    return signature.hmac(algorithm, secret, body)

def gen_signature_header(secret : str, body : str) -> Tuple[str, str]:
    return "sha256", gen_signature_hash("sha256", secret, body)

def verify_signature(signature_header, secret, body) -> bool:
    (algorithm, hash) = signature_header.split("=")
    return gen_signature_hash(algorithm, secret, body) == hash

def form_url(endpoint : str, url_path : str, anchor=None, **kwargs):
    base = endpoint.rstrip("/")
    suffix = urllib.parse.quote(url_path.lstrip("/"))
    args = [f"{x}={urllib.parse.quote(str(kwargs[x]))}" for x in kwargs.keys()]
    return f"{base}/{suffix}{"?" if len(args) > 0 else ""}{"&".join(args)}{f"#{anchor}" if anchor is not None else ""}"

