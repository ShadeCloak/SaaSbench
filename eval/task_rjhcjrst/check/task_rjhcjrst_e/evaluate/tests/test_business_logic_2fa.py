
from __future__ import annotations

from ..utils import NodeResult
from ._common import execute_primitive_chain


def test_BIZ_2FA_MFA_SECRET_PLAINTEXT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_2FA_MFA_SECRET_PLAINTEXT",
        "description": "FP-MFA-SECRET-PLAINTEXT / §5.6.3: PFM stores users.mfa_secret as PLAINTEXT base32 string (no application encryption cast — counter-intuitive!). After enable flow, P08 SELECT mfa_secret returns a 16-50 char string in [A-Z2-7]+ alphabet. Agents that wrap with 'encrypted' cast will fail this assertion.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "GET",
                    "path": "/api/v1/preferences/mfa-secret",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}",
                        "Accept": "application/json"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        201,
                        404
                    ]
                }
            },
            {
                "type": "P12",
                "inputs": {
                    "command": "php artisan tinker --execute=\"\\$u=\\\\App\\\\User::where('email','{{admin_email}}')->first(); \\$u->mfa_secret='JBSWY3DPEHPK3PXP'; \\$u->save();\"",
                    "container": "{{app_container}}",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT u.mfa_secret AS secret, CHAR_LENGTH(u.mfa_secret) AS secret_len, (u.mfa_secret REGEXP '^[A-Z2-7]+$') AS is_base32 FROM users u WHERE u.email = '{{admin_email}}'",
                    "expected_result": {
                        "secret": "JBSWY3DPEHPK3PXP",
                        "secret_len": 16,
                        "is_base32": 1
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_2FA",
            "subcategory": "MfaSecretPlaintext",
            "method": "binary",
            "maxScore": 12,
            "expected_reference_fail": "Seeds mfa_secret via `php artisan tinker --execute=...` but the deployed reference has NO tinker ('Command tinker is not defined' — Firefly's production image strips tinker; verified live). Also references `\\App\\User` whereas Firefly's model is `\\FireflyIII\\User`. There is no CLI path to set an MFA secret in the reference, so this node cannot be satisfied against the baseline."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-058"
        ],
        "_failure_point_refs": [
            "FP-MFA-SECRET-PLAINTEXT"
        ],
        "source_evidence": {
            "source_file": "Business Logic §5.6",
            "behavior_verified": "Static / source-derived; subcategory=MfaSecretPlaintext",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "DB_TABLE_USERS"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_2FA_RECOVERY_CODES_FORMAT(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_2FA_RECOVERY_CODES_FORMAT",
        "description": "§5.6.5 / KB-059: Recovery codes = 8 codes × 12 chars (2 blocks × 6 chars, lowercase alphanumeric, NO separator inside each code). Stored as JSON array in preferences row name='mfa_recovery'. Verify JSON_LENGTH = 8 AND each code matches ^[a-z0-9]{12}$.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "INSERT INTO preferences (user_id, name, data, created_at, updated_at) SELECT u.id, 'mfa_recovery', '\"[\\\"abc123def456\\\",\\\"ghi789jkl012\\\",\\\"mno345pqr678\\\",\\\"stu901vwx234\\\",\\\"yza567bcd890\\\",\\\"efg123hij456\\\",\\\"klm789nop012\\\",\\\"qrs345tuv678\\\"]\"', NOW(), NOW() FROM users u WHERE u.email = '{{admin_email}}' ON DUPLICATE KEY UPDATE data='\"[\\\"abc123def456\\\",\\\"ghi789jkl012\\\",\\\"mno345pqr678\\\",\\\"stu901vwx234\\\",\\\"yza567bcd890\\\",\\\"efg123hij456\\\",\\\"klm789nop012\\\",\\\"qrs345tuv678\\\"]\"', updated_at=NOW()",
                    "expect_success": True
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT JSON_LENGTH(JSON_UNQUOTE(p.data)) AS code_count, JSON_UNQUOTE(JSON_EXTRACT(JSON_UNQUOTE(p.data), '$[0]')) AS first_code FROM preferences p INNER JOIN users u ON p.user_id = u.id WHERE u.email = '{{admin_email}}' AND p.name = 'mfa_recovery'",
                    "expected_result": {
                        "code_count": 8,
                        "first_code": "abc123def456"
                    }
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT SUM(JSON_UNQUOTE(JSON_EXTRACT(JSON_UNQUOTE(p.data), CONCAT('$[', n.idx, ']'))) REGEXP '^[a-z0-9]{12}$') AS valid_codes FROM preferences p INNER JOIN users u ON p.user_id = u.id CROSS JOIN (SELECT 0 idx UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7) n WHERE u.email = '{{admin_email}}' AND p.name = 'mfa_recovery'",
                    "expected_result": {
                        "valid_codes": 8
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_2FA",
            "subcategory": "RecoveryCodesFormat",
            "method": "binary",
            "maxScore": 8,
            "expected_reference_fail": "Verified live against the reference: recovery codes are generated ONLY by the web MFA-enable flow (session-guarded /profile UI, which requires submitting a valid TOTP code); `php artisan route:list --path=api` exposes NO api route to enable MFA or read/generate recovery codes (same web-only limitation as BIZ_2FA_DISABLE_CLEARS_SECRET). The node therefore cannot exercise the reference's real recovery-code generation via API — it can only hand-seed an mfa_recovery preference row and re-read it, which validates the test's own fixture rather than the reference implementation. Rather than keep a self-referential (vacuous) assertion, the node is dropped from scoring; the §5.6.5 format spec (8 codes x 12 lowercase-alphanumeric chars) is not verifiable against this reference through any API surface."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.6",
            "behavior_verified": "Static / source-derived; subcategory=RecoveryCodesFormat",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_2FA_MFA_SECRET_PLAINTEXT"
        ]
    }
    return execute_primitive_chain(node, context)


def test_BIZ_2FA_DISABLE_CLEARS_SECRET(context: dict) -> NodeResult:
    node = {
        "id": "BIZ_2FA_DISABLE_CLEARS_SECRET",
        "description": "§5.6.6: Disable flow MUST set users.mfa_secret = NULL AND delete preferences row name='mfa_recovery'. Verify both side-effects via P08.",
        "primitive_chain": [
            {
                "type": "P13",
                "inputs": {
                    "role": "admin"
                }
            },
            {
                "type": "P04",
                "inputs": {
                    "method": "DELETE",
                    "path": "/api/v1/user/preferences/mfa",
                    "headers": {
                        "Authorization": "Bearer {{admin_token}}"
                    }
                }
            },
            {
                "type": "P15",
                "inputs": {
                    "acceptable_statuses": [
                        200,
                        204
                    ]
                }
            },
            {
                "type": "P08",
                "inputs": {
                    "sql": "SELECT (u.mfa_secret IS NULL) AS secret_null, (SELECT COUNT(*) FROM preferences p WHERE p.user_id = u.id AND p.name = 'mfa_recovery') AS recovery_pref_rows FROM users u WHERE u.email = '{{admin_email}}'",
                    "expected_result": {
                        "secret_null": 1,
                        "recovery_pref_rows": 0
                    }
                }
            }
        ],
        "scoring": {
            "category": "BusinessLogic_2FA",
            "subcategory": "DisableClearsSecret",
            "method": "binary",
            "maxScore": 6,
            "expected_reference_fail": "Verified live against the reference: DELETE /api/v1/user/preferences/mfa returns 404, and `php artisan route:list --path=api` shows NO api route for mfa/two-factor/preferences. Firefly manages MFA (enable/disable, secret, recovery codes) exclusively through the web /profile UI (session-guarded Blade/Twig controllers); there is no REST API surface to disable MFA or clear mfa_secret. The spec's API-driven 'disable clears secret' flow is not implemented in the reference, so the node is dropped from scoring."
        },
        "complexity_tier": "workflow_automator",
        "_kb_refs": [
            "KB-058"
        ],
        "_failure_point_refs": [],
        "source_evidence": {
            "source_file": "Business Logic §5.6",
            "behavior_verified": "Static / source-derived; subcategory=DisableClearsSecret",
            "needs_api_behavior_verification": True
        },
        "prereqs": [
            "BIZ_2FA_MFA_SECRET_PLAINTEXT"
        ]
    }
    return execute_primitive_chain(node, context)

