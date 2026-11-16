import hashlib
import hmac
import json
import logging
import re
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from web.models import CentreUserAccount

from .models import IntegrationSyncLog


logger = logging.getLogger(__name__)
User = get_user_model()
MAX_BODY_BYTES = 65536
TIMESTAMP_TOLERANCE_SECONDS = 300


class PayloadError(ValueError):
    pass


def _json_error(message, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _header(request, name):
    return request.META.get(f"HTTP_{name.upper().replace('-', '_')}", "").strip()


def _verify_request(request):
    if not request.is_secure():
        return "HTTPS is required", 400

    api_key = str(getattr(settings, "SSCEGOV_INTEGRATION_API_KEY", "")).strip()
    hmac_secret = str(getattr(settings, "SSCEGOV_INTEGRATION_HMAC_SECRET", "")).strip()
    if not api_key or not hmac_secret:
        return "Integration authentication is not configured", 503

    supplied_key = _header(request, "X-SSCEGOV-API-Key")
    timestamp = _header(request, "X-SSCEGOV-Timestamp")
    signature = _header(request, "X-SSCEGOV-Signature")
    if not supplied_key or not timestamp or not signature:
        return "Missing integration authentication headers", 401
    if not hmac.compare_digest(supplied_key, api_key):
        return "Invalid integration API key", 401
    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return "Invalid integration timestamp", 401
    if abs(int(timezone.now().timestamp()) - timestamp_int) > TIMESTAMP_TOLERANCE_SECONDS:
        return "Expired integration request", 401

    expected = hmac.new(
        hmac_secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return "Invalid integration signature", 401
    return None, None


def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise PayloadError("exam_completed_at must be a valid ISO-8601 timestamp") from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _mobile(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 10:
        raise PayloadError("mobile must contain exactly 10 digits")
    return int(digits)


def _state_value(value):
    raw = str(value or "").strip()
    choices = dict(CentreUserAccount.STATE_CHOICES)
    if raw in choices:
        return raw
    lowered = raw.lower()
    for choice, label in choices.items():
        if lowered in (label.lower(), choice.lower()):
            return choice
    return raw[:255]


def _rural_area(value):
    value = str(value or "").strip().lower()
    return {
        "panchayath": "panchayat",
        "panchayat": "panchayat",
        "muncipality": "municipality",
        "municipality": "municipality",
        "corporation": "corporation",
    }.get(value, value[:255] or None)


def _compatible_password_hash(password_hash):
    if not isinstance(password_hash, str) or not password_hash:
        return None
    try:
        identify_hasher(password_hash)
    except (ValueError, TypeError):
        return None
    return password_hash


def _validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PayloadError("Unsupported or missing schema_version")
    if payload.get("source_system") != "sscentrepreneur":
        raise PayloadError("Unsupported source_system")

    forbidden_password_fields = {
        "password",
        "plain_password",
        "raw_password",
        "password_plaintext",
    }
    if forbidden_password_fields.intersection(payload):
        raise PayloadError("Plaintext passwords are not accepted")

    for field in ("source_user_id", "source_candidate_id"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PayloadError(f"{field} must be a positive integer")

    full_name = str(payload.get("full_name") or "").strip()
    username = str(payload.get("username") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not full_name or len(full_name) > 255:
        raise PayloadError("full_name is required and must be at most 255 characters")
    if not username or len(username) > 100:
        raise PayloadError("username is required and must be at most 100 characters")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise PayloadError("email is invalid")

    mobile = _mobile(payload.get("mobile"))
    aadhaar = re.sub(r"\D", "", str(payload.get("aadhaar_number") or ""))
    if len(aadhaar) != 12:
        raise PayloadError("aadhaar_number must contain exactly 12 digits")
    if payload.get("exam_status") != "Passed":
        raise PayloadError("Only Passed exam_status can be synchronized")

    password_hash = _compatible_password_hash(payload.get("password_hash"))
    if not password_hash:
        raise PayloadError("A compatible Django password_hash is required for activation")
    completed_at = _parse_datetime(payload.get("exam_completed_at"))
    centre = payload.get("centre") or {}
    if not isinstance(centre, dict):
        raise PayloadError("centre must be an object")

    address = str(payload.get("address") or "")[:550]
    location = str(centre.get("location") or address or "")
    return {
        "source_system": payload["source_system"],
        "source_user_id": payload["source_user_id"],
        "source_candidate_id": payload["source_candidate_id"],
        "full_name": full_name,
        "username": username,
        "email": email,
        "mobile": mobile,
        "address": address,
        "aadhaar_number": int(aadhaar),
        "exam_status": "Passed",
        "exam_completed_at": completed_at,
        "centre": {
            "owner_centre": str(centre.get("owner_name") or full_name)[:100],
            "centre_name": str(centre.get("name") or "None")[:100],
            "state": _state_value(centre.get("state")),
            "district": str(centre.get("district") or "")[:255],
            "taluk": str(centre.get("taluk") or "")[:50],
            "rural_areas": _rural_area(centre.get("local_body")),
            "ward_number": str(centre.get("ward_number") or "")[:55],
            "centre_email": str(centre.get("centre_email") or email).strip().lower()[:254],
            "centre_phone_number": _mobile(centre.get("centre_phone_number") or mobile),
            "location": location,
        },
        "password_hash": password_hash,
    }


def _matching_accounts(data):
    source_matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(
            source_system=data["source_system"],
            source_candidate_id=data["source_candidate_id"],
        )
        .order_by("id")[:2]
    )
    if len(source_matches) > 1:
        raise PayloadError("Source candidate ID matches multiple destination accounts")
    if source_matches:
        return source_matches[0], "source_candidate_id"

    source_user_matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(
            source_system=data["source_system"],
            source_user_id=data["source_user_id"],
        )
        .order_by("id")[:2]
    )
    if len(source_user_matches) > 1:
        raise PayloadError("Source user ID matches multiple destination accounts")
    if source_user_matches:
        return source_user_matches[0], "source_user_id"

    email_matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(Q(email__iexact=data["email"]) | Q(user__email__iexact=data["email"]))
        .distinct()
        .order_by("id")[:2]
    )
    if len(email_matches) > 1:
        raise PayloadError("Email matches multiple destination accounts")
    if email_matches:
        return email_matches[0], "email"

    mobile_matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(mobile=data["mobile"])
        .order_by("id")[:2]
    )
    if len(mobile_matches) > 1:
        raise PayloadError("Mobile matches multiple destination accounts")
    if mobile_matches:
        return mobile_matches[0], "mobile"
    return None, ""


def _user_for_account(account, data):
    user = account.user if account else None
    if user is None:
        if User.objects.filter(username=data["username"]).exists():
            raise PayloadError("Username is already used by an unrelated destination user")
        user = User(username=data["username"])
    elif User.objects.exclude(pk=user.pk).filter(username=data["username"]).exists():
        raise PayloadError("Username is already used by another destination user")

    user.username = data["username"]
    user.email = data["email"]
    user.usertype = "centre"
    user.is_active = True
    user.password = data["password_hash"]
    user.save()
    return user


def _log_invalid_payload(idempotency_key, payload, digest, message):
    source_system = "unknown"
    source_user_id = None
    source_candidate_id = None
    if isinstance(payload, dict):
        source_system = str(payload.get("source_system", "unknown"))[:64]
        source_user_id = payload.get("source_user_id")
        source_candidate_id = payload.get("source_candidate_id")
        if not isinstance(source_user_id, int) or source_user_id <= 0:
            source_user_id = None
        if not isinstance(source_candidate_id, int) or source_candidate_id <= 0:
            source_candidate_id = None
    IntegrationSyncLog.objects.update_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "source_system": source_system,
            "source_user_id": source_user_id,
            "source_candidate_id": source_candidate_id,
            "payload_digest": digest,
            "status": IntegrationSyncLog.REJECTED,
            "http_status": 400,
            "error_message": message[:4000],
            "processed_at": timezone.now(),
        },
    )


@csrf_exempt
@require_POST
def exam_qualified_user(request):
    auth_error, auth_status = _verify_request(request)
    if auth_error:
        return _json_error(auth_error, auth_status)
    if len(request.body) > MAX_BODY_BYTES:
        return _json_error("Payload is too large", 413)

    idempotency_key = _header(request, "X-SSCEGOV-Idempotency-Key")
    if not idempotency_key or len(idempotency_key) > 255:
        return _json_error("Missing or invalid idempotency key", 400)
    digest = hashlib.sha256(request.body).hexdigest()
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_error("Request body must be valid JSON", 400)

    try:
        data = _validate_payload(payload)
    except PayloadError as exc:
        _log_invalid_payload(idempotency_key, payload, digest, str(exc))
        return _json_error(str(exc), 400)

    with transaction.atomic():
        log, created = IntegrationSyncLog.objects.select_for_update().get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "source_system": data["source_system"],
                "source_user_id": data["source_user_id"],
                "source_candidate_id": data["source_candidate_id"],
                "payload_digest": digest,
            },
        )
        if not created:
            log.request_count += 1
            if log.payload_digest != digest:
                log.status = IntegrationSyncLog.REJECTED
                log.error_message = "Idempotency key was reused with a different payload"
                log.http_status = 409
                log.processed_at = timezone.now()
                log.save()
                return _json_error(log.error_message, 409)
            if log.status in (IntegrationSyncLog.CREATED, IntegrationSyncLog.UPDATED):
                log.save(update_fields=["request_count", "updated_at"])
                return JsonResponse(
                    {
                        "ok": True,
                        "status": log.status,
                        "centre_user_id": log.centre_user_id,
                        "matched_by": log.matched_by,
                        "idempotent_replay": True,
                    }
                )

        try:
            account, matched_by = _matching_accounts(data)
            user = _user_for_account(account, data)
            values = {
                "user": user,
                "name": data["full_name"],
                "username": data["username"],
                "owner_centre": data["centre"]["owner_centre"],
                "mobile": data["mobile"],
                "aadhaar_number": data["aadhaar_number"],
                "email": data["email"],
                "centre_owner_address": data["address"][:255],
                "centre_name": data["centre"]["centre_name"],
                "centre_phone_number": data["centre"]["centre_phone_number"],
                "state": data["centre"]["state"],
                "district": data["centre"]["district"],
                "taluk": data["centre"]["taluk"],
                "rural_areas": data["centre"]["rural_areas"],
                "ward_number": data["centre"]["ward_number"],
                "centre_email": data["centre"]["centre_email"],
                "address": data["address"],
                "is_active": True,
                "location": data["centre"]["location"],
                "source_system": data["source_system"],
                "source_user_id": data["source_user_id"],
                "source_candidate_id": data["source_candidate_id"],
                "exam_status": data["exam_status"],
                "exam_completed_at": data["exam_completed_at"],
            }
            if account is None:
                account = CentreUserAccount.objects.create(**values)
                status = IntegrationSyncLog.CREATED
            else:
                for field, value in values.items():
                    setattr(account, field, value)
                account.save()
                status = IntegrationSyncLog.UPDATED

            log.status = status
            log.matched_by = matched_by or "new"
            log.centre_user_id = account.pk
            log.http_status = 200
            log.error_message = ""
            log.processed_at = timezone.now()
            log.save()
            return JsonResponse(
                {
                    "ok": True,
                    "status": status,
                    "centre_user_id": account.pk,
                    "matched_by": matched_by or "new",
                },
                status=201 if status == IntegrationSyncLog.CREATED else 200,
            )
        except PayloadError as exc:
            log.status = IntegrationSyncLog.REJECTED
            log.http_status = 400
            log.error_message = str(exc)
            log.processed_at = timezone.now()
            log.save()
            return _json_error(str(exc), 400)
        except Exception as exc:
            log.status = IntegrationSyncLog.FAILED
            log.http_status = 500
            log.error_message = f"{exc.__class__.__name__}: {exc}"[:4000]
            log.processed_at = timezone.now()
            log.save()
            logger.exception("sscentrepreneur qualified-user sync failed")
            return _json_error("Integration could not be processed", 500)
