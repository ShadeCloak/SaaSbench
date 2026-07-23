<?php

/**
 * Stage 7.2 smoke-test helper — issue a valid OAuth2 access_token for a given
 * username/client without going through OpenEMR's OAuth2 password grant.
 *
 * USAGE (inside the app container):
 *   php /var/www/html/_smoke_issue_token.php <username> <client_id> [scope...]
 *
 * OUTPUT (to stdout, single line):
 *   {"access_token": "<jwt>", "expires_in": 3600, "user_uuid": "<uuid-string>"}
 *
 * The script:
 *   1. Loads OpenEMR's autoloader + globals (so AccessTokenRepository works)
 *   2. Looks up the user UUID for the given username
 *   3. Constructs a JWT signed with the same private key OpenEMR uses
 *      (sites/default/documents/oauth2/private.key)
 *   4. Persists the token in `api_token` so isAccessTokenRevokedInDatabase()
 *      will return false (i.e. the token is valid)
 *
 * Why this exists: production OpenEMR validates tokens via the league/oauth2
 * library which does signature verification + DB-revocation check. Inserting
 * a raw random string into api_token doesn't satisfy the JWT verification.
 * This helper produces a properly-signed JWT that mimics what would have
 * been issued by the password grant flow.
 */

declare(strict_types=1);

if ($argc < 3) {
    fwrite(STDERR, "Usage: php _smoke_issue_token.php <username> <client_id> [scope...]\n");
    exit(2);
}

$username = $argv[1];
$clientId = $argv[2];
$scopes = array_slice($argv, 3);
if (empty($scopes)) {
    // OpenEMR uses two parallel scope notations (FHIR R4 CamelCase
    // vs standard REST lowercase). Grant the cartesian product. Token
    // size will exceed 14 KB — set Apache LimitRequestFieldSize to compensate.
    $smartScopes = [
        'Patient','Practitioner','PractitionerRole','Organization',
        'Encounter','Appointment','AllergyIntolerance','Observation',
        'Condition','Immunization','Procedure','Medication',
        'MedicationRequest','MedicationDispense','DocumentReference',
        'Coverage','Location','Provenance','CarePlan','CareTeam',
        'Goal','Group','Person','Specimen','Device','DiagnosticReport',
        'ServiceRequest','RelatedPerson','Questionnaire',
        'QuestionnaireResponse','ValueSet','OperationDefinition',
        'Binary','Media',
    ];
    $standardScopes = [
        'patient','practitioner','facility','encounter','appointment',
        'allergy','immunization','medication','prescription','medical_problem',
        'document','drug','employer','insurance','insurance_company',
        'insurance_type','list','message','soap_note','surgery',
        'transaction','user','version','vital','dental_issue','product',
        'procedure',
    ];
    // Role-aware scope subsets — receptionist / front office / accounting
    // get only their job-appropriate FHIR resources, mirroring what a
    // proper consent-screen / OAuth2 grant flow would issue. This makes
    // the smoke harness honour the same RBAC contract as the spec.
    $roleAllowed = [
        'evalrec'    => ['Appointment','Practitioner','PractitionerRole','Location'],
        'evalfo'     => ['Appointment','Practitioner','PractitionerRole','Location','Organization','Coverage'],
        'evalacct'   => ['Coverage','Organization','Practitioner','Location'],
        'evalemerg'  => $smartScopes, // break-glass — full clinical access
        'evalclin'   => $smartScopes,
        'evalphys'   => $smartScopes,
        'admin'      => $smartScopes,
        'oe-system'  => $smartScopes,
    ];
    $roleStdAllowed = [
        'evalrec'    => ['appointment','practitioner','facility','user','version'],
        'evalfo'     => ['appointment','practitioner','facility','insurance','insurance_company','user','version'],
        'evalacct'   => ['transaction','insurance','insurance_company','insurance_type','user','version'],
        'evalemerg'  => $standardScopes,
        'evalclin'   => $standardScopes,
        'evalphys'   => $standardScopes,
        'admin'      => $standardScopes,
        'oe-system'  => $standardScopes,
    ];
    $effSmart = $roleAllowed[$username]    ?? $smartScopes;
    $effStd   = $roleStdAllowed[$username] ?? $standardScopes;

    $scopes = ['openid','fhirUser','profile','email','offline_access',
               'launch','launch/patient',
               'api:oemr','api:fhir','api:port','api:pofh'];
    // System-level scopes for SMART Bulk Data — only granted to roles
    // that legitimately need cross-patient export (admin / clinical /
    // emergency). Receptionist / front office / accounting do not.
    $bulkAllowed = ['admin','oe-system','evalemerg','evalclin','evalphys'];
    if (in_array($username, $bulkAllowed, true)) {
        foreach ($effSmart as $r) {
            $scopes[] = "system/{$r}.read";
        }
        // Bulk export operation scope (SMART v2)
        $scopes[] = 'system/*.read';
    }
    foreach ($effSmart as $r) {
        $scopes[] = "user/{$r}.read";
        $scopes[] = "user/{$r}.write";
        $scopes[] = "patient/{$r}.read";
    }
    foreach ($effStd as $r) {
        $scopes[] = "user/{$r}.read";
        $scopes[] = "user/{$r}.write";
        $scopes[] = "user/{$r}.s";
        $scopes[] = "user/{$r}.r";
        $scopes[] = "user/{$r}.cruds";
        $scopes[] = "user/{$r}.crus";
        $scopes[] = "user/{$r}.crds";
        $scopes[] = "user/{$r}.cuds";
        $scopes[] = "user/{$r}.cud";
        $scopes[] = "user/{$r}.crs";
    }
}

// 1. Bootstrap OpenEMR runtime (mirrors what apis/dispatch.php does).
$_SERVER['HTTP_HOST'] = 'localhost:8030';
$_SERVER['REQUEST_URI'] = '/_smoke_issue_token';
$_SERVER['REQUEST_METHOD'] = 'GET';
$_SERVER['SERVER_NAME'] = 'localhost';
$_SERVER['SERVER_PORT'] = '8030';
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
$_SERVER['DOCUMENT_ROOT'] = '/var/www/html';

chdir('/var/www/html');
require_once '/var/www/html/vendor/autoload.php';

// Set up a minimal OpenEMR runtime so CryptoGen + ADODB work.
\OpenEMR\Core\OEGlobalsBag::getInstance()->set('OE_SITE_DIR', '/var/www/html/sites/default');
\OpenEMR\Core\OEGlobalsBag::getInstance()->set('OE_SITE', 'default');
\OpenEMR\Core\OEGlobalsBag::getInstance()->set('SITE', 'default');

// Establish a raw mysqli for the bits we control directly.
$mysqli = new mysqli('db', 'applgzivily', 'app123lgzivily', 'app_lgzivily', 3306);
if ($mysqli->connect_errno) {
    fwrite(STDERR, "DB connect failed: " . $mysqli->connect_error . "\n");
    exit(5);
}
$mysqli->set_charset('utf8mb4');

// Establish OpenEMR's ADODB connection so CryptoGen (which calls
// sqlQueryNoLog -> ADOdb) can read the encrypted oauth2passphrase.
$_GET['site'] = 'default';
require_once '/var/www/html/sites/default/sqlconf.php';
require_once '/var/www/html/library/sql.inc.php';
// sql.inc.php line ~61 calls DatabaseConnectionFactory::createAdodb($cfg)
// and stashes it on $GLOBALS['adodb']['db']. Verify:
if (empty($GLOBALS['adodb']['db'])) {
    fwrite(STDERR, "ADODB connection not initialised by sql.inc.php\n");
    exit(5);
}

// 2. Look up the user UUID — generate one if missing
$stmt = $mysqli->prepare("SELECT id, uuid FROM users WHERE username = ?");
$stmt->bind_param("s", $username);
$stmt->execute();
$row = $stmt->get_result()->fetch_assoc();
if (empty($row)) {
    fwrite(STDERR, "User '$username' not found\n");
    exit(3);
}
$userId = (int) $row['id'];

if (empty($row['uuid'])) {
    // Generate a UUID v4 + binary form, store
    $uuidStr = sprintf('%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
        mt_rand(0, 0xffff), mt_rand(0, 0xffff),
        mt_rand(0, 0xffff),
        mt_rand(0, 0x0fff) | 0x4000,
        mt_rand(0, 0x3fff) | 0x8000,
        mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
    );
    $uuidBin = hex2bin(str_replace('-', '', $uuidStr));
    $up = $mysqli->prepare("UPDATE users SET uuid = ? WHERE id = ?");
    $up->bind_param("si", $uuidBin, $userId);
    $up->execute();
    // Insert into uuid_registry too
    $up2 = $mysqli->prepare("INSERT IGNORE INTO uuid_registry (uuid, table_name, table_id) VALUES (?, 'users', ?)");
    $tableId = (string)$userId;
    $up2->bind_param("ss", $uuidBin, $tableId);
    $up2->execute();
    $userUuid = $uuidStr;
} else {
    $userUuid = bin2hex($row['uuid']);
    $userUuid = substr($userUuid, 0, 8) . '-' . substr($userUuid, 8, 4) . '-'
        . substr($userUuid, 12, 4) . '-' . substr($userUuid, 16, 4) . '-' . substr($userUuid, 20, 12);
}

// 3. Generate JTI + bearer JWT
$jti = bin2hex(random_bytes(16));
$now = time();
$expiresIn = 3600;
$expiry = $now + $expiresIn;

$payload = [
    'aud' => $clientId,
    'jti' => $jti,
    'iat' => $now,
    'nbf' => $now,
    'exp' => $expiry,
    'sub' => $userUuid,
    'scopes' => $scopes,
    'site_id' => 'default',
    'api' => 'oemr fhir port',
    'user_role' => \OpenEMR\Common\Auth\UuidUserAccount::USER_ROLE_USERS,
    'iss' => 'http://localhost:8030/oauth2/default',
];

// OpenEMR validates FHIR tokens with sites/{site}/documents/certificates/oapublic.key
// (auto-generated by SiteSetupListener). Sign with the matching oaprivate.key.
// The PEM is OpenSSL-encrypted with a passphrase stored encrypted in the
// `keys` table. We have to fetch + decrypt the passphrase first.
$privateKeyPem = file_get_contents('/var/www/html/sites/default/documents/certificates/oaprivate.key');
if ($privateKeyPem === false) {
    fwrite(STDERR, "Cannot read OAuth2 REST private key (certificates/oaprivate.key)\n");
    exit(4);
}

$res = $mysqli->query("SELECT `value` FROM `keys` WHERE `name`='oauth2passphrase'");
$row2 = $res ? $res->fetch_assoc() : null;
if (empty($row2['value'])) {
    fwrite(STDERR, "Cannot find oauth2passphrase in keys table\n");
    exit(4);
}
$crypto = new \OpenEMR\Common\Crypto\CryptoGen();
$passphrase = $crypto->decryptStandard($row2['value']);
if (empty($passphrase)) {
    fwrite(STDERR, "Failed to decrypt oauth2passphrase\n");
    exit(4);
}

$pkey = openssl_pkey_get_private($privateKeyPem, $passphrase);
if ($pkey === false) {
    fwrite(STDERR, "openssl_pkey_get_private failed: " . openssl_error_string() . "\n");
    exit(4);
}
// Re-export PEM without passphrase so the JWT signer can use it
openssl_pkey_export($pkey, $privateKey);
if (empty($privateKey)) {
    fwrite(STDERR, "openssl_pkey_export failed\n");
    exit(4);
}

$jwt = encode_jwt_rs256($payload, $privateKey);

// 4. Persist into api_token so OpenEMR's isAccessTokenRevokedInDatabase() OK
$expiryDate = date('Y-m-d H:i:s', $expiry);
$scopeJson = json_encode($scopes);
$context = json_encode(['user_id' => $userUuid, 'site_id' => 'default']);

// Persist directly via mysqli. Do NOT delete prior tokens for this user —
// the harness caches token strings and reuses them across nodes; deleting
// them would invalidate cached entries from earlier P13 invocations.
$ins = $mysqli->prepare(
    "INSERT INTO api_token (user_id, token, expiry, client_id, scope, context, revoked)
     VALUES (?, ?, ?, ?, ?, ?, 0)");
$ins->bind_param("ssssss", $userUuid, $jti, $expiryDate, $clientId, $scopeJson, $context);
$ins->execute();

// Mark the (client, user) pair as trusted so isTrustedUser() returns true.
// session_cache must be non-empty for the check to pass. Use INSERT ...
// ON DUPLICATE KEY UPDATE to keep this idempotent.
$check = $mysqli->prepare(
    "SELECT id FROM oauth_trusted_user WHERE client_id = ? AND user_id = ? LIMIT 1");
$check->bind_param("ss", $clientId, $userUuid);
$check->execute();
$existing = $check->get_result()->fetch_assoc();

$sessionCache = json_encode(['user_id' => $userUuid, 'site_id' => 'default',
                              'session_id' => $jti, 'persist' => 1]);
$grantType = 'password';
if (empty($existing)) {
    $insTrust = $mysqli->prepare(
        "INSERT INTO oauth_trusted_user (user_id, client_id, scope, persist_login, time, code, session_cache, grant_type)
         VALUES (?, ?, ?, 1, NOW(), ?, ?, ?)");
    if ($insTrust === false) {
        fwrite(STDERR, "insTrust prepare failed: " . $mysqli->error . "\n");
    } else {
        $insTrust->bind_param("ssssss", $userUuid, $clientId, $scopeJson, $jti, $sessionCache, $grantType);
        if (!$insTrust->execute()) {
            fwrite(STDERR, "insTrust execute failed: " . $insTrust->error . "\n");
        }
    }
}

echo json_encode([
    'access_token' => $jwt,
    'expires_in' => $expiresIn,
    'user_uuid' => $userUuid,
    'jti' => $jti,
]) . "\n";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function encode_jwt_rs256(array $payload, string $privateKeyPem): string {
    $header = ['typ' => 'JWT', 'alg' => 'RS256'];
    $segments = [
        b64url_encode(json_encode($header)),
        b64url_encode(json_encode($payload)),
    ];
    $signing_input = implode('.', $segments);

    $pkey = openssl_pkey_get_private($privateKeyPem);
    if ($pkey === false) {
        throw new RuntimeException('Cannot parse private key: ' . openssl_error_string());
    }
    openssl_sign($signing_input, $signature, $pkey, OPENSSL_ALGO_SHA256);
    return $signing_input . '.' . b64url_encode($signature);
}

function b64url_encode(string $s): string {
    return rtrim(strtr(base64_encode($s), '+/', '-_'), '=');
}
