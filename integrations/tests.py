import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import Client, TestCase, override_settings

from web.models import CentreUserAccount

from .models import IntegrationSyncLog


@override_settings(
    SSCEGOV_INTEGRATION_API_KEY="test-api-key",
    SSCEGOV_INTEGRATION_HMAC_SECRET="test-hmac-secret",
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
class ExamQualifiedUserApiTests(TestCase):
    endpoint = "/api/integrations/sscentrepreneur/exam-qualified-user/"

    def payload(self, **changes):
        data = {
            "schema_version": 1,
            "source_system": "sscentrepreneur",
            "source_user_id": 10,
            "source_candidate_id": 20,
            "full_name": "Qualified Candidate",
            "username": "123456789012",
            "email": "candidate@example.com",
            "mobile": "9876543210",
            "address": "Test address",
            "aadhaar_number": "123456789012",
            "exam_status": "Passed",
            "exam_completed_at": "2026-11-16T10:00:00+00:00",
            "centre": {
                "owner_name": "Qualified Candidate",
                "name": "Test Panchayat",
                "state": "Kerala",
                "district": "Kollam",
                "local_body": "Panchayath",
                "ward_number": "4",
                "centre_email": "candidate@example.com",
                "centre_phone_number": "9876543210",
                "location": "8.5,76.9",
            },
            "password_hash": make_password("9876543210"),
        }
        data.update(changes)
        return data

    def request(self, payload, key="sync-20", api_key="test-api-key", secure=True):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(datetime.now(dt_timezone.utc).timestamp()))
        signature = hmac.new(
            b"test-hmac-secret",
            timestamp.encode("utf-8") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "HTTP_X_SSCEGOV_API_KEY": api_key,
            "HTTP_X_SSCEGOV_TIMESTAMP": timestamp,
            "HTTP_X_SSCEGOV_SIGNATURE": signature,
            "HTTP_X_SSCEGOV_IDEMPOTENCY_KEY": key,
        }
        if secure:
            headers["HTTP_X_FORWARDED_PROTO"] = "https"
        return Client().post(
            self.endpoint,
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_create_and_idempotent_replay_never_duplicates(self):
        payload = self.payload()
        first = self.request(payload)
        second = self.request(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(CentreUserAccount.objects.count(), 1)
        self.assertEqual(get_user_model().objects.filter(username="123456789012").count(), 1)
        self.assertEqual(IntegrationSyncLog.objects.get().request_count, 2)

    def test_matching_order_uses_source_ids_then_email_then_mobile(self):
        self.assertEqual(self.request(self.payload()).status_code, 201)

        by_source_user = self.payload(
            source_candidate_id=21,
            email="changed@example.com",
            mobile="9876543211",
            username="123456789013",
        )
        response = self.request(by_source_user, key="sync-source-user")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "source_user_id")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

        by_email = self.payload(
            source_user_id=11,
            source_candidate_id=22,
            email="changed@example.com",
            mobile="9876543212",
            username="123456789014",
        )
        response = self.request(by_email, key="sync-email")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "email")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

        by_mobile = self.payload(
            source_user_id=12,
            source_candidate_id=23,
            email="new@example.com",
            mobile="9876543212",
            username="123456789015",
        )
        response = self.request(by_mobile, key="sync-mobile")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "mobile")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

    def test_failed_exam_and_plaintext_password_are_rejected(self):
        failed = self.request(self.payload(exam_status="Failed"), key="sync-failed")
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(CentreUserAccount.objects.count(), 0)
        self.assertEqual(IntegrationSyncLog.objects.get().status, IntegrationSyncLog.REJECTED)

        plaintext = self.request(
            self.payload(password="9876543210"),
            key="sync-plaintext",
        )
        self.assertEqual(plaintext.status_code, 400)
        self.assertEqual(CentreUserAccount.objects.count(), 0)
        self.assertNotIn("9876543210", IntegrationSyncLog.objects.get(idempotency_key="sync-plaintext").error_message)

    def test_api_authentication_https_and_idempotency_conflict(self):
        self.assertEqual(self.request(self.payload(), api_key="wrong").status_code, 401)
        self.assertEqual(self.request(self.payload(), key="sync-http", secure=False).status_code, 400)

        self.assertEqual(self.request(self.payload(), key="sync-conflict").status_code, 201)
        conflict = self.request(
            self.payload(full_name="Different Payload"),
            key="sync-conflict",
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(CentreUserAccount.objects.count(), 1)

    def test_compatible_hash_is_preserved_on_destination_user(self):
        self.assertEqual(self.request(self.payload()).status_code, 201)
        account = CentreUserAccount.objects.get()
        self.assertTrue(check_password("9876543210", account.user.password))
        self.assertEqual(account.exam_status, "Passed")
        self.assertEqual(account.source_candidate_id, 20)
