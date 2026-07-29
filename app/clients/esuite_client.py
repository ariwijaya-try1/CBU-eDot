import base64
import hashlib
import hmac
import json
import time
import uuid

import requests

from app.core.config import settings
from app.core.exceptions import (
    EsuiteAuthError,
    EsuiteDuplicateRequestError,
    EsuiteRPCError,
)


class EsuiteClient:
    """
    Client generik untuk push/pull ke eSuite webhook API.
    Semua entity service (branch, product, dst) manggil lewat sini —
    jadi logic signing & retry cukup ditulis 1x di sini.
    """

    def __init__(self):
        self.base_url = settings.ESUITE_BASE_URL.rstrip("/")
        self.client_id = settings.ESUITE_CLIENT_ID
        self.client_secret = settings.ESUITE_CLIENT_SECRET
        self.session = requests.Session()

    def _sign(self, raw_body: bytes) -> str:
        """
        HMAC-SHA256 atas raw bytes body, key = client_secret.
        PENTING: raw_body ini harus PERSIS bytes yang akan dikirim.
        Kalau di-serialize ulang (misal json.dumps dipanggil 2x dengan
        urutan key beda), signature ini nggak akan match lagi -> 401.
        """
        mac = hmac.new(self.client_secret.encode(), raw_body, hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _headers(self, raw_body: bytes, request_id: str) -> dict:
        return {
            "Authorization": self._auth_header(),
            "X-Signature": self._sign(raw_body),
            "X-Timestamp": str(int(time.time())),
            "X-Request-ID": request_id,
            "Content-Type": "application/json",
        }

    def push(self, entity_path: str, event: str, data: list, request_id: str | None = None) -> dict:
        """
        Push (POST) ke eSuite.
        entity_path: contoh "branches", "product", "customers"
        event: "init" | "upsert" | "delete"
        request_id: kalau None, di-generate baru. Kalau ini retry dari
                     request yang gagal/timeout sebelumnya, KIRIM ULANG
                     request_id yang sama supaya nggak diproses dobel.
        """
        request_id = request_id or uuid.uuid4().hex  # 32 char, masuk rentang 16-64

        payload = {"event": event, "data": data}
        # json.dumps DIPANGGIL SEKALI di sini. raw_body ini yang dipakai
        # untuk sign DAN untuk dikirim -> single-serialization discipline.
        raw_body = json.dumps(payload, separators=(",", ":")).encode()

        url = f"{self.base_url}/{entity_path}"
        headers = self._headers(raw_body, request_id)

        response = self.session.post(url, data=raw_body, headers=headers, timeout=30)
        return self._handle_response(response, request_id)

    def pull(self, entity_path: str, page: int = 1, limit: int = 100) -> dict:
        """GET (pull) reference/master data dari eSuite. Body kosong -> sign string kosong."""
        raw_body = b""
        request_id = uuid.uuid4().hex
        headers = self._headers(raw_body, request_id)

        url = f"{self.base_url}/{entity_path}"
        response = self.session.get(
            url, headers=headers, params={"page": page, "limit": limit}, timeout=30
        )
        return self._handle_response(response, request_id)

    def _handle_response(self, response: requests.Response, request_id: str) -> dict:
        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text}

        if response.status_code == 401:
            raise EsuiteAuthError(message=body.get("message", "eSuite auth failed"), details=body)

        if response.status_code == 400 and "already exists" in body.get("message", "").lower():
            # request_id sudah pernah dipakai -> dianggap bukan error fatal,
            # biar caller yang putuskan mau treat sebagai sukses atau bukan
            raise EsuiteDuplicateRequestError(
                message=body.get("message"), details={"request_id": request_id}
            )

        if response.status_code >= 400:
            raise EsuiteRPCError(message=body.get("message", "eSuite error"), details=body)

        return body
