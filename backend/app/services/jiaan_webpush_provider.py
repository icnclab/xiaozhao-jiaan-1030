"""Real Web Push Provider adapter for the Transactional Outbox.

Wires the same pywebpush call shape already proven in jiaan_webpush.py's
_send_one() into the PushProvider protocol that jiaan_emergency_outbox.py's
dispatch_one() expects -- reusing that proven pattern, not the poll-based
sweep()/dispatch_due() loop it lives in (that loop is not restored, extended,
or otherwise reused by this module).

No production code path constructs this class. app/worker.py's
_emergency_webpush_outbox handler calls dispatch_one() with provider=None
(unchanged); nothing in this batch wires a PywebpushProvider into it.
JIAAN_WEBPUSH_DISPATCH stays off everywhere it matters regardless.

Key isolation: this module never reads, hardcodes, or defaults to
deploy/fieldtest/.local_webpush_secrets/ (the production VAPID PEM
directory). The PEM location is always an explicit constructor argument, or
an explicit isolated-only environment variable read by from_isolated_env().
Missing or unreadable -> fails closed at construction time, before any
decrypt or network call.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.services.jiaan_emergency_outbox import PushMessage, PushResult

# Isolated-QA-only env vars. Never shared with, or defaulted from, the
# production JIAAN_VAPID_PRIVATE_KEY/JIAAN_VAPID_PUBLIC_KEY/JIAAN_VAPID_SUBJECT
# settings that app/services/jiaan_webpush.py's poll path reads.
ISOLATED_PEM_PATH_ENV = "JIAAN_WEBPUSH_ISOLATED_VAPID_PEM_PATH"
ISOLATED_SUBJECT_ENV = "JIAAN_WEBPUSH_ISOLATED_VAPID_SUBJECT"


class ProviderNotConfigured(RuntimeError):
    """Fail-closed: no key material was supplied, or it could not be found."""


class PywebpushProvider:
    """Real pywebpush adapter, constructed only with explicit key material.

    Never falls back to a default path, never reads any other environment
    variable than the two passed in here or via from_isolated_env().
    """

    def __init__(self, *, vapid_pem_path: str, vapid_subject: str):
        if not vapid_subject:
            raise ProviderNotConfigured("WEBPUSH_PROVIDER_SUBJECT_NOT_CONFIGURED")
        path = Path(vapid_pem_path)
        if not path.is_file():
            raise ProviderNotConfigured(f"WEBPUSH_PROVIDER_KEY_NOT_FOUND: {vapid_pem_path}")
        self._pem_path = str(path)
        self._subject = vapid_subject

    @classmethod
    def from_isolated_env(cls) -> "PywebpushProvider":
        """Builds from the two isolated-only env vars above.

        Raises ProviderNotConfigured (fail closed) when either is unset or
        unreadable -- never silently constructs a provider pointed at
        nothing, and never consults any production setting as a fallback.
        """
        pem_path = os.environ.get(ISOLATED_PEM_PATH_ENV, "").strip()
        subject = os.environ.get(ISOLATED_SUBJECT_ENV, "").strip()
        if not pem_path:
            raise ProviderNotConfigured("WEBPUSH_PROVIDER_KEY_PATH_NOT_CONFIGURED")
        return cls(vapid_pem_path=pem_path, vapid_subject=subject)

    def send(self, message: PushMessage) -> PushResult:
        """Real network call. Only ever invoked by a test that explicitly
        constructed this class and explicitly passed it to dispatch_one();
        no production code path does either.
        """
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={
                    "endpoint": message.endpoint,
                    "keys": {"p256dh": message.p256dh, "auth": message.auth},
                },
                data=json.dumps(message.payload, ensure_ascii=False),
                vapid_private_key=self._pem_path,
                vapid_claims={"sub": self._subject},
                headers={"Urgency": "high"},
                ttl=300,
                timeout=8,
            )
            return PushResult(accepted=True)
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", None)
            return PushResult(accepted=False, error_class=str(code or type(exc).__name__))
