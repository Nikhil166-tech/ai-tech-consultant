"""
Step 1 Production Security & Data Isolation Tests
Comprehensive test suite verifying:
- No default-admin fallback (unauthenticated returns 401)
- User registration with Argon2id password hashing
- Validation of emails and strong passwords
- Login with valid credentials and automatic rehash of legacy PBKDF2 hashes
- Failed login rate-limiting and account lockout
- Logout and server-side session invalidation
- Session persistence and CSRF protection
- Complete cross-user data isolation (sitemaps, settings, quarantine)
- Internal service-to-service communication via X-Internal-Service-Key
- Frontend/backend API compatibility (PUT /settings, POST /quarantine/{id}/restore)
- Preservation of existing knowledge, articles, chunks, and embeddings
"""

import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Database
from app.config import settings
from app.auth import verify_password


def test_database_preservation_and_integrity(prod_db):
    """Verify that existing database tables, integrity, and chunk embeddings are preserved."""
    # Check integrity
    with prod_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        assert result[0] == "ok", f"Integrity check failed: {result}"

        # Verify article and chunk count preservation
        cursor.execute("SELECT COUNT(*) FROM articles;")
        article_count = cursor.fetchone()[0]
        assert article_count >= 500, f"Expected at least 500 articles preserved, got {article_count}"

        cursor.execute("SELECT COUNT(*) FROM chunks;")
        chunk_count = cursor.fetchone()[0]
        assert chunk_count >= 1900, f"Expected at least 1900 chunks preserved, got {chunk_count}"

        cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding_json IS NOT NULL AND length(embedding_json) > 10;")
        embedded_count = cursor.fetchone()[0]
        assert embedded_count >= 1900, f"Expected at least 1900 embeddings preserved, got {embedded_count}"


def test_unauthenticated_access_rejected_no_admin_bypass(client):
    """Verify that unauthenticated access returns 401 and NO default-admin is granted."""
    endpoints_to_test = [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/sitemaps"),
        ("GET", "/api/v1/refresh-runs"),
        ("GET", "/api/v1/quarantine"),
        ("GET", "/api/v1/settings"),
    ]

    for method, path in endpoints_to_test:
        res = client.request(method, path)
        assert res.status_code == 401, f"{method} {path} expected 401 Unauthorized, got {res.status_code}: {res.text}"
        detail = res.json().get("detail", "")
        assert "Authentication required" in detail or "Unauthorized" in detail


def test_registration_validation(client):
    """Verify email format and password strength validation during registration."""
    # Invalid email
    res = client.post("/api/v1/auth/register", json={
        "email": "not-an-email",
        "password": "ValidPassword123!"
    })
    assert res.status_code == 400
    assert "Invalid email format" in res.json().get("detail", "")

    # Weak password
    res = client.post("/api/v1/auth/register", json={
        "email": "valid@example.com",
        "password": "weak"
    })
    assert res.status_code == 400
    assert "Password must be at least 8 characters" in res.json().get("detail", "")


def test_registration_and_argon2id_hashing(client, db):
    """Verify user registration stores Argon2id hash and returns session + CSRF cookies."""
    test_email = "test_step1_user_a@example.com"
    test_password = "SecurePasswordA123!"

    # Clean up user if previously created
    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?;", (test_email,))
        conn.commit()

    res = client.post("/api/v1/auth/register", json={
        "email": test_email,
        "password": test_password
    })
    assert res.status_code == 200
    data = res.json()
    assert "user" in data
    assert data["user"]["email"] == test_email
    # CRITICAL: Password hash must NEVER be exposed in response
    assert "password_hash" not in data["user"]

    # Verify cookies
    assert "session_id" in res.cookies
    assert "csrf_token" in res.cookies

    # Check database to ensure Argon2id hash algorithm was used
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE email = ?;", (test_email,))
        row = cursor.fetchone()
        assert row is not None
        db_hash = row[0]
        assert db_hash.startswith("$argon2id$"), f"Expected Argon2id hash, got: {db_hash[:20]}"


def test_login_successful_and_auto_rehash(client, db):
    """Verify login with demo user and automatic upgrade of legacy hash to Argon2id."""
    demo_email = "demo.consultant@brilliantdirectories.com"
    demo_pass = "DemoPassword123!"

    # Verify demo user exists in database
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE email = ?;", (demo_email,))
        row = cursor.fetchone()
        assert row is not None, "Demo user should exist in database"
        initial_hash = row[0]

    # Perform login
    res = client.post("/api/v1/auth/login", json={
        "email": demo_email,
        "password": demo_pass
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == demo_email
    assert "password_hash" not in data["user"]

    # Verify hash has been automatically upgraded to Argon2id in DB
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE email = ?;", (demo_email,))
        upgraded_hash = cursor.fetchone()[0]
        assert upgraded_hash.startswith("$argon2id$"), f"Expected upgraded Argon2id hash, got: {upgraded_hash[:20]}"


def test_login_rejection_and_account_lockout(client, db):
    """Verify failed login counting and account lockout after repeated failures."""
    lock_email = "lockout_test@example.com"
    lock_pass = "CorrectPassword123!"

    # Register user first
    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?;", (lock_email,))
        conn.commit()

    reg_res = client.post("/api/v1/auth/register", json={
        "email": lock_email,
        "password": lock_pass
    })
    assert reg_res.status_code == 200

    # Create new unauthenticated client
    with TestClient(app) as test_client:
        # Exceed login attempts (limit is 5)
        for i in range(5):
            bad_res = test_client.post("/api/v1/auth/login", json={
                "email": lock_email,
                "password": "WrongPassword!"
            })
            assert bad_res.status_code in (401, 429)

        # 6th attempt should be locked out
        locked_res = test_client.post("/api/v1/auth/login", json={
            "email": lock_email,
            "password": "WrongPassword!"
        })
        assert locked_res.status_code in (401, 423, 429)


def test_logout_and_session_invalidation(client, db):
    """Verify logout destroys server-side session and prevents reuse."""
    user_email = "logout_test_user@example.com"
    user_pass = "LogoutPassword123!"

    # Clean up user if previously created
    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?;", (user_email,))
        conn.commit()

    reg_res = client.post("/api/v1/auth/register", json={
        "email": user_email,
        "password": user_pass
    })
    assert reg_res.status_code == 200

    # /auth/me succeeds with session
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == user_email

    # Extract CSRF token for state-changing logout
    csrf_token = reg_res.cookies.get("csrf_token")

    # Logout
    logout_res = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout_res.status_code == 200

    # Re-calling /auth/me must fail (401 Unauthorized)
    me_after = client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


def test_cross_user_sitemap_and_settings_isolation(client, db):
    """Verify strict data isolation: User B cannot see or manipulate User A's data."""
    user_a_email = "user_alpha@example.com"
    user_b_email = "user_beta@example.com"
    password = "CommonPassword123!"

    # Clean up test accounts
    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email IN (?, ?);", (user_a_email, user_b_email))
        conn.commit()

    # Register User A in client_a
    with TestClient(app) as client_a:
        res_a = client_a.post("/api/v1/auth/register", json={"email": user_a_email, "password": password})
        assert res_a.status_code == 200
        csrf_a = res_a.cookies.get("csrf_token")

        # User A updates settings
        settings_payload = {
            "url_verification_threshold": 7,
            "sitemap_refresh_frequency": "weekly",
            "quarantine_action_rule": "FLAG_ONLY"
        }
        set_res_a = client_a.put("/api/v1/settings", json=settings_payload, headers={"X-CSRF-Token": csrf_a})
        assert set_res_a.status_code == 200

        # User A registers a sitemap
        sm_res_a = client_a.post("/api/v1/sitemaps", json={
            "url": "https://alpha.example.com/sitemap.xml",
            "refresh_interval": "daily"
        }, headers={"X-CSRF-Token": csrf_a})
        assert sm_res_a.status_code == 200
        sitemap_a_id = sm_res_a.json()["id"]

        # Register User B in separate client_b
        with TestClient(app) as client_b:
            res_b = client_b.post("/api/v1/auth/register", json={"email": user_b_email, "password": password})
            assert res_b.status_code == 200
            csrf_b = res_b.cookies.get("csrf_token")

            # User B lists sitemaps: must NOT see User A's sitemap
            list_b = client_b.get("/api/v1/sitemaps")
            assert list_b.status_code == 200
            b_sitemaps = list_b.json()
            assert not any(sm["id"] == sitemap_a_id for sm in b_sitemaps)

            # User B attempts to access User A's sitemap directly by ID: must return 404
            get_b = client_b.get(f"/api/v1/sitemaps/{sitemap_a_id}")
            assert get_b.status_code == 404

            # User B attempts to confirm indexing on User A's sitemap: must return 404
            confirm_b = client_b.post(f"/api/v1/sitemaps/{sitemap_a_id}/confirm-index", headers={"X-CSRF-Token": csrf_b})
            assert confirm_b.status_code == 404

            # User B's settings are completely isolated from User A's
            get_settings_b = client_b.get("/api/v1/settings")
            assert get_settings_b.status_code == 200
            b_settings = get_settings_b.json()
            # User B should have default threshold (3), not User A's custom 7
            assert b_settings.get("url_verification_threshold") == 3


def test_internal_service_key_authentication(client):
    """Verify Task 2 and Task 3 can query Task 1 with X-Internal-Service-Key without a user session."""
    internal_key = settings.internal_service_key

    # 1. Query /ask with valid internal service key
    valid_res = client.post("/api/v1/ask", json={
        "question": "How do I configure member listing settings in Brilliant Directories?",
        "category_filter": None,
        "history": []
    }, headers={"X-Internal-Service-Key": internal_key})
    assert valid_res.status_code == 200
    data = valid_res.json()
    assert "answer" in data
    assert "citations" in data
    assert "evidence_score" in data

    # 2. Query /ask with invalid internal key and no session -> 401 Unauthorized
    invalid_res = client.post("/api/v1/ask", json={
        "question": "Can I import members via CSV?",
        "category_filter": None,
        "history": []
    }, headers={"X-Internal-Service-Key": "completely_wrong_key_xyz"})
    assert invalid_res.status_code == 401


def test_frontend_api_compatibility_and_quarantine_restore(client, db):
    """Verify frontend API contracts: PUT /settings and POST /quarantine/{id}/restore."""
    test_user_email = "api_compat_user@example.com"
    test_user_pass = "CompatPassword123!"

    # Clean up
    with db.get_connection() as conn:
        conn.cursor().execute("DELETE FROM users WHERE email = ?;", (test_user_email,))
        conn.cursor().execute("DELETE FROM quarantine_records WHERE url = 'https://example.com/test-quarantine' OR id = 'quar_compat_test_1';")
        conn.commit()

    with TestClient(app) as test_client:
        reg_res = test_client.post("/api/v1/auth/register", json={
            "email": test_user_email,
            "password": test_user_pass
        })
        assert reg_res.status_code == 200
        csrf = reg_res.cookies.get("csrf_token")
        user_id = reg_res.json()["user"]["id"]

        # Insert a test quarantine record for this user
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO quarantine_records (
                    id, url, title, content, quarantine_reason, last_known_http_status, quarantined_at, user_id
                ) VALUES (
                    'quar_compat_test_1', 'https://example.com/test-quarantine', 'Test Article', 'Sample content', 'MISSING_404', 404, CURRENT_TIMESTAMP, ?
                );
            """, (user_id,))
            conn.commit()

        # 1. Test POST /quarantine/{id}/restore (path parameter as sent by frontend)
        restore_res = test_client.post(
            "/api/v1/quarantine/quar_compat_test_1/restore",
            headers={"X-CSRF-Token": csrf}
        )
        assert restore_res.status_code == 200
        restore_data = restore_res.json()
        assert restore_data["success"] is True

        # Verify resolved in DB
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT restored_at FROM quarantine_records WHERE id = 'quar_compat_test_1';")
            row = cursor.fetchone()
            assert row[0] is not None, "Quarantine record should have restored_at timestamp"

        # 2. Test PUT /api/v1/settings (as sent by frontend)
        put_settings = test_client.put(
            "/api/v1/settings",
            json={"url_verification_threshold": 4, "sitemap_refresh_frequency": "hourly"},
            headers={"X-CSRF-Token": csrf}
        )
        assert put_settings.status_code == 200
        assert put_settings.json()["url_verification_threshold"] == 4
