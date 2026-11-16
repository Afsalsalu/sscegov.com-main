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


def _mobile(value, field="mobile"):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 10:
        raise PayloadError(f"{field} must contain exactly 10 digits")
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
    raise PayloadError("centre.state must be a supported state")


def _rural_area(value):
    value = str(value or "").strip().lower()
    normalized = {
        "panchayath": "panchayat",
        "panchayat": "panchayat",
        "muncipality": "municipality",
        "municipality": "municipality",
        "corporation": "corporation",
    }.get(value)
    if value and not normalized:
        raise PayloadError("centre.local_body must be a supported local-body type")
    return normalized


def _compatible_password_hash(password_hash):
    if not isinstance(password_hash, str) or not password_hash:
        return None
    try:
        identify_hasher(password_hash)
    except (ValueError, TypeError):
        return None
    return password_hash


def _contains_plaintext_password_field(value):
    forbidden = {"password", "plain_password", "raw_password", "password_plaintext"}
    if isinstance(value, dict):
        if forbidden.intersection(value):
            return True
        return any(_contains_plaintext_password_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_plaintext_password_field(item) for item in value)
    return False


def _validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PayloadError("Unsupported or missing schema_version")
    if payload.get("source_system") != "sscentrepreneur":
        raise PayloadError("Unsupported source_system")

    if _contains_plaintext_password_field(payload):
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
    _parse_datetime(payload.get("exam_completed_at"))

    centre = payload.get("centre") or {}
    if not isinstance(centre, dict):
        raise PayloadError("centre must be an object")
    centre_email = str(centre.get("centre_email") or email).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", centre_email):
        raise PayloadError("centre.centre_email is invalid")

    password_hash = _compatible_password_hash(payload.get("password_hash"))
    address = str(payload.get("address") or "")[:550]
    return {
        "full_name": full_name,
        "username": username,
        "email": email,
        "mobile": mobile,
        "aadhaar_number": int(aadhaar),
        "address": address,
        "password_hash": password_hash,
        "centre": {
            "owner_centre": str(centre.get("owner_name") or full_name)[:100],
            "centre_name": str(centre.get("name") or "None")[:100],
            "centre_phone_number": _mobile(
                centre.get("centre_phone_number") or mobile,
                "centre.centre_phone_number",
            ),
            "state": _state_value(centre.get("state")),
            "district": str(centre.get("district") or "")[:255],
            "taluk": str(centre.get("taluk") or "")[:50],
            "rural_areas": _rural_area(centre.get("local_body")),
            "ward_number": str(centre.get("ward_number") or "")[:55],
            "centre_email": centre_email[:254],
            "location": str(centre.get("location") or address or ""),
        },
    }


def _matching_account(data):
    lookup = (
        Q(username__iexact=data["username"])
        | Q(user__username__iexact=data["username"])
    )
    matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(lookup)
        .distinct()
        .order_by("id")[:2]
    )
    if len(matches) > 1:
        raise PayloadError("Username matches multiple destination accounts")
    if matches:
        return matches[0], "username"

    matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(Q(email__iexact=data["email"]) | Q(user__email__iexact=data["email"]))
        .distinct()
        .order_by("id")[:2]
    )
    if len(matches) > 1:
        raise PayloadError("Email matches multiple destination accounts")
    if matches:
        return matches[0], "email"

    matches = list(
        CentreUserAccount.objects.select_related("user")
        .filter(mobile=data["mobile"])
        .order_by("id")[:2]
    )
    if len(matches) > 1:
        raise PayloadError("Mobile matches multiple destination accounts")
    if matches:
        return matches[0], "mobile"
    return None, ""


def _user_for_account(account, data):
    user = account.user if account else None
    if user is None:
        if User.objects.filter(username=data["username"]).exists():
            raise PayloadError("Username is already used by another destination user")
        if not data["password_hash"]:
            raise PayloadError("A compatible Django password_hash is required for a new account")
        user = User(username=data["username"])
    elif User.objects.exclude(pk=user.pk).filter(username=data["username"]).exists():
        raise PayloadError("Username is already used by another destination user")

    user.username = data["username"]
    user.email = data["email"]
    user.usertype = "centre"
    user.is_active = True
    if data["password_hash"]:
        user.password = data["password_hash"]
    user.save()
    return user


@csrf_exempt
@require_POST
def exam_qualified_user(request):
    auth_error, auth_status = _verify_request(request)
    if auth_error:
        return _json_error(auth_error, auth_status)
    if len(request.body) > MAX_BODY_BYTES:
        return _json_error("Payload is too large", 413)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_error("Request body must be valid JSON", 400)

    try:
        data = _validate_payload(payload)
        with transaction.atomic():
            account, matched_by = _matching_account(data)
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
            }
            if account is None:
                account = CentreUserAccount.objects.create(**values)
                status = "created"
            else:
                for field, value in values.items():
                    setattr(account, field, value)
                account.save()
                status = "updated"
    except PayloadError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        logger.exception("sscentrepreneur qualified-user sync failed")
        return _json_error("Integration could not be processed", 500)

    return JsonResponse(
        {
            "ok": True,
            "status": status,
            "centre_user_id": account.pk,
            "matched_by": matched_by or "new",
        },
        status=201 if status == "created" else 200,
    )
