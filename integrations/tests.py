import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import Client, TestCase, override_settings

from web.models import CentreUserAccount


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
            "username": "123456789012",
            "email": "candidate@example.com",
            "mobile": "9876543210",
            "full_name": "Qualified Candidate",
            "address": "Candidate address",
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

    def request(self, payload, api_key="test-api-key", secure=True):
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
        }
        if secure:
            headers["HTTP_X_FORWARDED_PROTO"] = "https"
        return Client().post(
            self.endpoint,
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_create_and_replay_never_duplicates(self):
        payload = self.payload()
        first = self.request(payload)
        second = self.request(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(CentreUserAccount.objects.count(), 1)
        self.assertEqual(get_user_model().objects.filter(username="123456789012").count(), 1)

    def test_matching_order_uses_username_then_email_then_mobile(self):
        self.assertEqual(self.request(self.payload()).status_code, 201)

        by_email = self.payload(
            username="123456789013",
            email="candidate@example.com",
            mobile="9876543211",
        )
        response = self.request(by_email)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "email")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

        by_mobile = self.payload(
            username="123456789014",
            email="new@example.com",
            mobile="9876543211",
        )
        response = self.request(by_mobile)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "mobile")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

        by_username = self.payload(
            username="123456789014",
            email="another@example.com",
            mobile="9876543212",
        )
        response = self.request(by_username)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matched_by"], "username")
        self.assertEqual(CentreUserAccount.objects.count(), 1)

    def test_failed_exam_and_plaintext_password_are_rejected(self):
        failed = self.request(self.payload(exam_status="Failed"))
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(CentreUserAccount.objects.count(), 0)

        plaintext = self.request(self.payload(password="9876543210"))
        self.assertEqual(plaintext.status_code, 400)
        self.assertEqual(CentreUserAccount.objects.count(), 0)

        nested_plaintext = self.payload()
        nested_plaintext["centre"]["password"] = "9876543210"
        self.assertEqual(self.request(nested_plaintext).status_code, 400)
        self.assertEqual(CentreUserAccount.objects.count(), 0)

    def test_api_authentication_requires_https_and_valid_key(self):
        self.assertEqual(self.request(self.payload(), api_key="wrong").status_code, 401)
        self.assertEqual(self.request(self.payload(), secure=False).status_code, 400)

    def test_compatible_hash_is_preserved_on_destination_user(self):
        self.assertEqual(self.request(self.payload()).status_code, 201)
        account = CentreUserAccount.objects.get()
        self.assertTrue(check_password("9876543210", account.user.password))

        update = self.payload(email="updated@example.com", password_hash=None)
        self.assertEqual(self.request(update).status_code, 200)
        account.refresh_from_db()
        self.assertTrue(check_password("9876543210", account.user.password))
