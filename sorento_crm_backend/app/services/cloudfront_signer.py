"""
CloudFront signed URL signer using key groups (custom policy).

Signs a JSON policy with the RSA private key (RSA-SHA1 as required by CloudFront),
then returns a signed URL with Policy, Signature, and Key-Pair-Id query parameters.
Private key is loaded once from PEM file; do not log the key or full signed URL.

CloudFront expects MIME base64 (RFC 2045), then character replacement for URL safety:
  + -> -,  = -> _,  / -> ~  (per AWS docs).
"""
import base64
import json
import logging
import time
from pathlib import Path
from urllib.parse import quote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


def _cloudfront_base64_encode(data: bytes) -> str:
    """MIME base64 encode then replace +/= per CloudFront URL requirements: + -> -, = -> _, / -> ~."""
    raw = base64.b64encode(data).decode("ascii")
    return raw.replace("+", "-").replace("=", "_").replace("/", "~")


def _load_private_key(pem_path: str) -> bytes:
    """Load PEM file from disk. Raises if file missing or invalid."""
    path = Path(pem_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"CloudFront private key file not found: {path}")
    return path.read_bytes()


class CloudFrontSigner:
    """
    Generates CloudFront signed URLs using a key group (custom policy).

    Usage:
        signer = CloudFrontSigner(
            key_pair_id="K2ABCD1234",
            private_key_path="./cloudfront_private_key.pem",
            dist_domain="d1234abcd.cloudfront.net",
        )
        url = signer.generate_url("videos/demo.mp4", expires_in=3600)
        # url is suitable to send to respond.io (WhatsApp links)
    """

    def __init__(
        self,
        key_pair_id: str,
        private_key_path: str,
        dist_domain: str,
    ) -> None:
        """
        Load the RSA private key from the PEM file once.

        Args:
            key_pair_id: CloudFront public key ID (from console, tied to key group).
            private_key_path: Filesystem path to RSA private key PEM file.
            dist_domain: CloudFront distribution domain (e.g. d1234abcd.cloudfront.net).

        Raises:
            ValueError: If key_pair_id or dist_domain is empty, or key file missing/invalid.
        """
        if not (key_pair_id and key_pair_id.strip()):
            raise ValueError("CLOUDFRONT_KEY_PAIR_ID must be set and non-empty")
        if not (dist_domain and dist_domain.strip()):
            raise ValueError("CLOUDFRONT_DOMAIN must be set and non-empty")
        if not (private_key_path and private_key_path.strip()):
            raise ValueError("CLOUDFRONT_PRIVATE_KEY_PATH must be set and non-empty")

        self.key_pair_id = key_pair_id.strip()
        self.dist_domain = dist_domain.strip().rstrip("/")

        pem_bytes = _load_private_key(private_key_path.strip())
        self._private_key = serialization.load_pem_private_key(
            pem_bytes,
            password=None,
            backend=default_backend(),
        )
        logger.info(
            "CloudFront signer initialized for domain=%s, key_pair_id=%s",
            self.dist_domain,
            self.key_pair_id[:8] + "..." if len(self.key_pair_id) > 8 else self.key_pair_id,
        )

    def generate_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Build a CloudFront signed URL for the given object key.

        Args:
            object_key: S3 key (path) of the object, e.g. "videos/demo.mp4".
            expires_in: URL validity in seconds (default 3600).

        Returns:
            Signed URL: https://{dist_domain}/{object_key}?Policy=...&Signature=...&Key-Pair-Id=...

        Raises:
            Exception: If signing fails (with error logged).
        """
        key = object_key.lstrip("/")
        # URL-encode the path so filenames with spaces/special chars work (CloudFront policy Resource must match request URL)
        encoded_path = quote(key, safe="/")
        resource_url = f"https://{self.dist_domain}/{encoded_path}"
        expiry_epoch = int(time.time()) + expires_in

        policy = {
            "Statement": [
                {
                    "Resource": resource_url,
                    "Condition": {
                        "DateLessThan": {"AWS:EpochTime": expiry_epoch},
                    },
                }
            ]
        }
        policy_str = json.dumps(policy, separators=(",", ":"), sort_keys=True)

        try:
            signature_bytes = self._private_key.sign(
                policy_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA1(),
            )
        except Exception as e:
            logger.error("CloudFront signing failed for key=%s: %s", key, e)
            raise Exception(f"Failed to sign CloudFront policy: {e}") from e

        policy_b64 = _cloudfront_base64_encode(policy_str.encode("utf-8"))
        signature_b64 = _cloudfront_base64_encode(signature_bytes)

        signed_url = (
            f"{resource_url}"
            f"?Policy={policy_b64}"
            f"&Signature={signature_b64}"
            f"&Key-Pair-Id={self.key_pair_id}"
        )
        logger.info("Generated CloudFront signed URL for key=%s, expires_in=%ds", key, expires_in)
        return signed_url
