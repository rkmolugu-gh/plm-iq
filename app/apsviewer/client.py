"""APS (Autodesk Platform Services) client built on `requests`.

Implements just enough of the APS REST surface to power the PLM-IQ viewer:
two-legged OAuth, OSS bucket/object upload from a local server file, Model
Derivative translation to SVF2, manifest status polling, and urn helpers.

No external SDK is required — `requests` is already a project dependency.
"""

import base64
import logging

import requests

from app.config import APS_BUCKET, APS_CLIENT_ID, APS_CLIENT_SECRET, APS_REGION

logger = logging.getLogger(__name__)

_BASE = "https://developer.api.autodesk.com"
_AUTH_HOST = "https://developer.api.autodesk.com"

# Region header used for OSS calls (US vs. EMEA).
_REGION_HEADER = {"Region": APS_REGION} if APS_REGION else {}

# Scopes for the internal token (upload + translate).
_INTERNAL_SCOPES = ["data:read", "data:write", "data:create", "bucket:create", "bucket:read"]
# Scopes for the token handed to the browser viewer.
_VIEWER_SCOPES = ["viewables:read"]


class APSError(Exception):
    """Raised for non-success APS API responses."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APSClient:
    """Thin client for the APS services used by the viewer."""

    def __init__(self, client_id: str = None, client_secret: str = None, bucket: str = None):
        self._client_id = client_id or APS_CLIENT_ID
        self._client_secret = client_secret or APS_CLIENT_SECRET
        self._bucket = bucket or APS_BUCKET or f"{self._client_id.lower()}-basic-app"

    # ── OAuth ──────────────────────────────────────────────────────────────
    def get_token(self, scopes: list[str]) -> str:
        """Return a two-legged access token for the given scopes."""
        resp = requests.post(
            f"{_AUTH_HOST}/authentication/v2/oauth/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
                "scope": " ".join(scopes),
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise APSError(f"APS token request failed: {resp.status_code} {resp.text[:300]}", resp.status_code)
        return resp.json()["access_token"]

    def get_viewer_token(self) -> dict:
        """Return {access_token, expires_in} for scopes the browser viewer needs."""
        resp = requests.post(
            f"{_AUTH_HOST}/authentication/v2/oauth/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
                "scope": " ".join(_VIEWER_SCOPES),
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise APSError(f"APS viewer token request failed: {resp.status_code} {resp.text[:300]}", resp.status_code)
        return {"access_token": resp.json()["access_token"], "expires_in": resp.json().get("expires_in", 3600)}

    # ── OSS (bucket/object storage) ─────────────────────────────────────────
    def _internal_token(self) -> str:
        return self.get_token(_INTERNAL_SCOPES)

    def ensure_bucket(self) -> None:
        """Create the APS bucket if it does not already exist."""
        token = self._internal_token()
        headers = {"Authorization": f"Bearer {token}", **{"Content-Type": "application/json"}, **_REGION_HEADER}
        resp = requests.get(f"{_BASE}/oss/v2/buckets/{self._bucket}/details", headers=headers, timeout=30)
        if resp.status_code == 200:
            return
        if resp.status_code == 404:
            create = requests.post(
                f"{_BASE}/oss/v2/buckets",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", **_REGION_HEADER},
                json={"bucketKey": self._bucket, "policyKey": "persistent"},
                timeout=30,
            )
            if create.status_code != 200:
                raise APSError(f"APS bucket creation failed: {create.status_code} {create.text[:300]}", create.status_code)
            return
        raise APSError(f"APS bucket lookup failed: {resp.status_code} {resp.text[:300]}", resp.status_code)

    def list_objects(self) -> list[dict]:
        """Return the list of objects in the bucket (objectKey + objectId)."""
        self.ensure_bucket()
        token = self._internal_token()
        headers = {"Authorization": f"Bearer {token}", **_REGION_HEADER}
        resp = requests.get(f"{_BASE}/oss/v2/buckets/{self._bucket}/objects", headers=headers, params={"limit": 100}, timeout=30)
        if resp.status_code != 200:
            raise APSError(f"APS list objects failed: {resp.status_code} {resp.text[:300]}", resp.status_code)
        return resp.json().get("items", [])

    def upload_file(self, object_name: str, local_path: str) -> dict:
        """Upload a local file to the APS bucket and return the object details."""
        self.ensure_bucket()
        token = self._internal_token()
        with open(local_path, "rb") as f:
            resp = requests.put(
                f"{_BASE}/oss/v2/buckets/{self._bucket}/objects/{object_name}",
                headers={"Authorization": f"Bearer {token}", **_REGION_HEADER},
                data=f,
                timeout=300,
            )
        if resp.status_code != 200:
            raise APSError(f"APS upload failed: {resp.status_code} {resp.text[:300]}", resp.status_code)
        return resp.json()

    # ── Model Derivative ─────────────────────────────────────────────────────
    def translate_object(self, urn: str, root_filename: str | None = None) -> str:
        """Start an SVF2 translation job for a base64 (url-safe) urn.

        Returns the job result status ("success" if the job was accepted).
        """
        token = self._internal_token()
        payload = {
            "input": {"urn": urn},
            "output": {"formats": [{"type": "svf2", "views": ["2d", "3d"]}]},
        }
        if root_filename:
            payload["input"]["compressedUrn"] = True
            payload["input"]["rootFilename"] = root_filename
        resp = requests.post(
            f"{_BASE}/modelderivative/v2/designdata/job",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if resp.status_code != 200:
            raise APSError(f"APS translation job failed: {resp.status_code} {resp.text[:400]}", resp.status_code)
        return resp.json().get("result", "success")

    def get_manifest(self, urn: str) -> dict | None:
        """Return the manifest for a translated urn, or None when not found."""
        token = self._internal_token()
        resp = requests.get(
            f"{_BASE}/modelderivative/v2/designdata/{urn}/manifest",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise APSError(f"APS manifest request failed: {resp.status_code} {resp.text[:300]}", resp.status_code)
        return resp.json()

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def urnify(value: str) -> str:
        """Turn an OSS objectId into the url-safe base64 urn the viewer expects."""
        return base64.b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")
