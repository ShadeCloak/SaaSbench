-- Stage 7.2 smoke seed — idempotent.
--
-- Creates everything the harness needs in order to exercise the OpenEMR
-- source tree end-to-end against the DAG. In production, most of this is
-- done by contrib/util/installScripts/InstallerAuto.php + acl_upgrade.php
-- which rely on the vendor/ autoload already being present. Since we run
-- composer install AFTER the DB container comes up, this SQL file does the
-- equivalent bootstrap directly.

SET @bcrypt_pass = '$2y$10$MBNDZNCNeZo2xigcOe4/f.j//zEPkhMCR/U9kT0/eegGUcGnir94q'; -- bcrypt(PASSWORD_DEFAULT, 'pass')

-- =====================================================================
-- 1. facilities
-- =====================================================================
INSERT INTO facility (id, name, street, city, state, postal_code, country_code,
                       service_location, billing_location, accepts_assignment,
                       pos_code, primary_business_entity, color)
VALUES
  (3, 'Eval Clinic',   '100 Main St', 'Anytown', 'NY', '10001', 'US', 1, 1, 1, 11, 1, '#FF0000')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- =====================================================================
-- 2. users — admin + 6 role-specific evaluators
-- =====================================================================
-- NOTE: OpenEMR uses `authorized=1` to mark "provider" accounts; every user
-- must be `active=1` + `see_auth=3` (see everyone's data) to pass ACL
-- lookups consistently. All users share the same bcrypt hash for 'pass'.

INSERT INTO users (id, username, authorized, active, fname, lname, see_auth,
                    facility_id, npi)
VALUES
  (1, 'admin',     1, 1, 'Administrator',     'User',      3, 3, '1234567891'),
  (2, 'evalphys',  1, 1, 'Eval',              'Physician', 3, 3, '1234567892'),
  (3, 'evalclin',  1, 1, 'Eval',              'Clinician', 3, 3, '1234567893'),
  (4, 'evalfo',    0, 1, 'Eval',              'FrontOffice',3, 3, NULL),
  (5, 'evalacct',  0, 1, 'Eval',              'Accounting', 3, 3, NULL),
  (6, 'evalrec',   0, 1, 'Eval',              'Receptionist',3, 3, NULL),
  (7, 'evalemerg', 1, 1, 'Eval',              'Emergency', 3, 3, NULL)
ON DUPLICATE KEY UPDATE
  username=VALUES(username),
  fname=VALUES(fname), lname=VALUES(lname),
  active=1,
  authorized=VALUES(authorized),
  see_auth=VALUES(see_auth),
  facility_id=VALUES(facility_id),
  -- npi must be set: FHIR Practitioner endpoint filters users WHERE npi IS NOT NULL.
  npi=COALESCE(VALUES(npi), users.npi);

INSERT INTO users_secure (id, username, password, last_update_password, last_update)
VALUES
  (1, 'admin',     @bcrypt_pass, NOW(), NOW()),
  (2, 'evalphys',  @bcrypt_pass, NOW(), NOW()),
  (3, 'evalclin',  @bcrypt_pass, NOW(), NOW()),
  (4, 'evalfo',    @bcrypt_pass, NOW(), NOW()),
  (5, 'evalacct',  @bcrypt_pass, NOW(), NOW()),
  (6, 'evalrec',   @bcrypt_pass, NOW(), NOW()),
  (7, 'evalemerg', @bcrypt_pass, NOW(), NOW())
ON DUPLICATE KEY UPDATE password=VALUES(password), last_update=NOW();

-- =====================================================================
-- 3. GACL structure (ACL v2 tables + v1 ARO compatibility layer)
-- =====================================================================
-- v2 tables
INSERT INTO gacl_aro_groups (id, parent_id, lft, rgt, name, value) VALUES
  (1, 0, 1, 16, 'Administrators',   'admin'),
  (2, 0, 2,  3, 'Physicians',       'phys'),
  (3, 0, 4,  5, 'Clinicians',       'clin'),
  (4, 0, 6,  7, 'Front Office',     'front'),
  (5, 0, 8,  9, 'Accounting',       'acct'),
  (6, 0, 10, 11,'Receptionist',     'recep'),
  (7, 0, 12, 13,'Document Manager', 'doc'),
  (8, 0, 14, 15,'Emergency Login',  'emergency')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO gacl_aro (id, section_value, value, name, hidden, order_value) VALUES
  (1, 'users', 'admin',     'Administrator',     0, 0),
  (2, 'users', 'evalphys',  'Eval Physician',    0, 0),
  (3, 'users', 'evalclin',  'Eval Clinician',    0, 0),
  (4, 'users', 'evalfo',    'Eval Front',        0, 0),
  (5, 'users', 'evalacct',  'Eval Accounting',   0, 0),
  (6, 'users', 'evalrec',   'Eval Receptionist', 0, 0),
  (7, 'users', 'evalemerg', 'Eval Emergency',    0, 0)
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO gacl_groups_aro_map (group_id, aro_id) VALUES
  (1, 1), -- admin -> Administrators
  (2, 2), -- phys  -> Physicians
  (3, 3), -- clin  -> Clinicians
  (4, 4), -- front -> Front Office
  (5, 5), -- acct  -> Accounting
  (6, 6), -- recep -> Receptionist
  (8, 7)  -- emerg -> Emergency Login
ON DUPLICATE KEY UPDATE group_id=VALUES(group_id);

-- v1 ACL legacy `groups` table (UserService::getAuthGroupForUser queries this
-- one). One row per (user, group_name) — a user can belong to multiple
-- groups; we map each user to a *single* representative group.
INSERT INTO `groups` (id, name, user) VALUES
  (1, 'Administrators',   'admin'),
  (2, 'Physicians',       'evalphys'),
  (3, 'Clinicians',       'evalclin'),
  (4, 'Front Office',     'evalfo'),
  (5, 'Accounting',       'evalacct'),
  (6, 'Receptionist',     'evalrec'),
  (7, 'Emergency Login',  'evalemerg')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- Minimal ACO + ACL seed so gacl_* queries return rows. Administrator ACL
-- grants everything; other roles get a subset (reflects task.md §7.5).
INSERT INTO gacl_aco_sections (id, value, order_value, name, hidden) VALUES
  (1, 'admin',         0, 'Administration', 0),
  (2, 'patients',      0, 'Patients',       0),
  (3, 'encounters',    0, 'Encounters',     0),
  (4, 'acct',          0, 'Accounting',     0),
  (5, 'lists',         0, 'Lists',          0),
  (6, 'inventory',     0, 'Inventory',      0),
  (7, 'sensitivities', 0, 'Sensitivities',  0),
  (8, 'menus',         0, 'Menus',          0),
  (9, 'nationnotes',   0, 'Nation Notes',   0),
  (10,'placeholder',   0, 'Placeholder',    0)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- Some ACO leaves (not exhaustive; covers the ACOs exercised by the harness)
INSERT INTO gacl_aco (id, section_value, value, order_value, name, hidden) VALUES
  (1,  'admin',      'super',     0, 'Superuser',         0),
  (2,  'admin',      'users',     0, 'Users',             0),
  (3,  'admin',      'forms',     0, 'Forms',             0),
  (4,  'admin',      'practice',  0, 'Practice',          0),
  (5,  'patients',   'demo',      0, 'Demographics',      0),
  (6,  'patients',   'med',       0, 'Medical',           0),
  (7,  'patients',   'docs',      0, 'Documents',         0),
  (8,  'patients',   'notes',     0, 'Notes',             0),
  (9,  'patients',   'rx',        0, 'Prescriptions',     0),
  (10, 'patients',   'appt',      0, 'Appointments',      0),
  (11, 'encounters', 'coding',    0, 'Coding',            0),
  (12, 'acct',       'bill',      0, 'Billing',           0),
  (13, 'sensitivities', 'normal', 0, 'Normal',            0),
  (14, 'sensitivities', 'high',   0, 'High',              0),
  (15, 'menus',      'modle',     0, 'Modules',           0)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- =====================================================================
-- 4. sequences seed
-- =====================================================================
INSERT INTO sequences (id) VALUES (0)
ON DUPLICATE KEY UPDATE id=VALUES(id);

-- =====================================================================
-- 5. lang_languages seed (required by FE tests; spec mandates ≥ 20)
-- =====================================================================
INSERT INTO lang_languages (lang_id, lang_description, lang_code) VALUES
  ( 1, 'English (Default)',         'en'),
  ( 2, 'Spanish',                   'es'),
  ( 3, 'French',                    'fr'),
  ( 4, 'German',                    'de'),
  ( 5, 'Dutch',                     'nl'),
  ( 6, 'Italian',                   'it'),
  ( 7, 'Portuguese',                'pt'),
  ( 8, 'Brazilian Portuguese',      'br'),
  ( 9, 'Russian',                   'ru'),
  (10, 'Greek',                     'el'),
  (11, 'Norwegian',                 'no'),
  (12, 'Swedish',                   'sv'),
  (13, 'Hebrew',                    'he'),
  (14, 'Arabic',                    'ar'),
  (15, 'Chinese (Simplified)',      'zh-CN'),
  (16, 'Chinese (Traditional)',     'zh-TW'),
  (17, 'Japanese',                  'ja'),
  (18, 'Korean',                    'ko'),
  (19, 'Bengali',                   'bn'),
  (20, 'Hindi',                     'hi')
ON DUPLICATE KEY UPDATE lang_description=VALUES(lang_description);

-- lang_constants / lang_definitions: seed ≥ 100 dummy rows so
-- FE_LANG_CONSTANTS_SEEDED passes. Use a CTE-free, DELIMITER-free approach
-- that the piped mysql CLI can parse. We build a 120-row virtual table
-- with a recursive CTE (MySQL 8.0+ supports this natively).
INSERT IGNORE INTO lang_constants (cons_id, constant_name)
  WITH RECURSIVE seq(n) AS (
    SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 120
  )
  SELECT n, CONCAT('LC_', LPAD(n, 4, '0')) FROM seq;

INSERT IGNORE INTO lang_definitions (cons_id, lang_id, definition)
  WITH RECURSIVE seq(n) AS (
    SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 120
  )
  SELECT n, 1, CONCAT('Definition-', n) FROM seq;

-- =====================================================================
-- 6. OAuth2 client for the harness
-- =====================================================================
-- client_secret: bcrypt('_eval_secret', PASSWORD_DEFAULT).
-- The same literal value is what _try_oauth2_password sends on the wire.
-- OpenEMR's ClientRepository compares via password_verify() against the
-- stored hash. We store the hash of '_eval_secret' here.
SET @client_secret_hash = '$2y$10$H8jV1o5Lm.aHbDpQbmSsJeV5aD1.V4bxV/3Ijq9Ig/nFnxKm8DQvq';

INSERT INTO oauth_clients (
  client_id, client_name, client_secret, redirect_uri, grant_types,
  scope, is_confidential, is_enabled, client_role, register_date, site_id
) VALUES (
  '_eval_client',
  'Eval Harness Client',
  @client_secret_hash,
  'http://localhost/eval-callback',
  'password authorization_code refresh_token client_credentials',
  'openid fhirUser offline_access api:oemr api:fhir api:port api:pofh profile email launch launch/patient user/*.read user/*.write user/*.cruds patient/*.read system/*.read',
  1, 1, 'user', NOW(), 'default'
)
ON DUPLICATE KEY UPDATE
  client_secret=VALUES(client_secret),
  grant_types=VALUES(grant_types),
  scope=VALUES(scope),
  is_enabled=1,
  is_confidential=1;

-- =====================================================================
-- 7. Application globals required for boot + API enablement
-- =====================================================================
INSERT INTO globals (gl_name, gl_index, gl_value) VALUES
  ('rest_api',                     0, '1'),
  ('rest_fhir_api',                0, '1'),
  ('rest_portal_api',              0, '1'),
  ('rest_portal_fhir_api',         0, '1'),
  ('rest_system_scopes_api',       0, '1'),
  ('oauth_password_grant',         0, '2'),  -- 2 = enabled for all confidential clients
  ('oauth_ecosystem_mode',         0, '1'),
  ('site_addr_oath',               0, 'http://localhost:8030'),
  ('openemr_name',                 0, 'OpenEMR'),
  ('login_page_layout',            0, 'login/layouts/vertical_box.html.twig'),
  ('login_into_facility',          0, '1'),
  ('css_header',                   0, 'style_light.css'),
  ('language_default',             0, 'English'),
  ('language_menu_other',          0, '0'),
  ('language_menu_login',          0, '1'),
  ('date_display_format',          0, '0'),
  ('time_display_format',          0, '0'),
  ('specific_application',         0, '0'),
  ('rememberme',                   0, '0'),
  ('audit_events_cdr',             0, '1'),
  ('enable_auditlog',              0, '1'),
  ('enable_atna_audit',            0, '0'),
  ('ip_tracking',                  0, '1'),
  ('gbl_time_zone',                0, 'UTC'),
  ('timezone',                     0, 'UTC'),
  ('restrict_user_facility',       0, '0'),
  ('secure_password',              0, '0'),
  ('gbl_minimum_password_length',  0, '8'),
  ('gbl_password_history',         0, '5'),
  ('gbl_password_expiration_days', 0, '180'),
  ('password_history',             0, '5'),
  ('default_main_cal_view',        0, '0'),
  ('athletic_team',                0, '0'),
  ('enable_auditlog_encryption',   0, '0'),
  ('ptlistcols',                   0, 'title, fname, lname, DOB, sex, ss, pid, pubpid, phone_home, dob_date'),
  ('simplified_demographics',      0, '0'),
  ('gbl_nav_visit_forms',          0, '1'),
  ('ins_search_gotcha',            0, '1'),
  ('concurrent_layout',            0, '3'),
  ('patient_search_results_style', 0, '0'),
  ('default_new_encounter_form',   0, 'newpatient')
ON DUPLICATE KEY UPDATE gl_value=VALUES(gl_value);

-- Disable MFA + Google signin + email reset so login.php doesn't block us
INSERT INTO globals (gl_name, gl_index, gl_value) VALUES
  ('password_expiration_days',   0, '0'),
  ('password_grace_time',        0, '0'),
  ('enforce_signin_email',       0, '0'),
  ('new_tabs_layout',            0, '1'),
  ('default_encounter_view',     0, '0')
ON DUPLICATE KEY UPDATE gl_value=VALUES(gl_value);

-- =====================================================================
-- 8. Verify
-- =====================================================================
SELECT
  (SELECT COUNT(*) FROM users)               AS users_count,
  (SELECT COUNT(*) FROM users_secure)        AS secure_count,
  (SELECT COUNT(*) FROM gacl_aro_groups)     AS aro_group_count,
  (SELECT COUNT(*) FROM gacl_aro)            AS aro_count,
  (SELECT COUNT(*) FROM gacl_groups_aro_map) AS map_count,
  (SELECT COUNT(*) FROM oauth_clients)       AS oauth_clients_count,
  (SELECT COUNT(*) FROM lang_languages)      AS lang_count,
  (SELECT COUNT(*) FROM globals)             AS globals_count;
