"""Integration tests against a real PostgreSQL database. Set TEST_DB_URL to run (skipped otherwise)."""
import os
import pytest
from sqlalchemy.exc import IntegrityError, DBAPIError

TEST_DB_URL = os.environ.get("TEST_DB_URL")
pytestmark = pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DB_URL not set")

import core, store  # noqa: E402


@pytest.fixture(scope="module")
def eng():
    import migrate
    e = store.make_engine(TEST_DB_URL)
    with e.begin() as c:   # fresh slate for repeatable tests
        c.exec_driver_sql("DROP SCHEMA public CASCADE")
        c.exec_driver_sql("CREATE SCHEMA public")
    migrate.migrate(e, verbose=False)
    return e


def zid(eng, name):
    return int(store.df(eng, "SELECT zone_id FROM Zone WHERE name=:n", {"n": name})["zone_id"].iloc[0])


def test_migration_idempotent_and_seeded(eng):
    import migrate
    migrate.migrate(eng, verbose=False)
    assert len(store.df(eng, "SELECT * FROM Zone")) == 12
    assert len(store.df(eng, "SELECT * FROM Shelter")) == 6


def test_rls_enabled_on_all_tables(eng):
    d = store.df(eng, "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                      "WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity")
    assert d.empty, f"RLS missing on: {d['relname'].tolist()}"


def test_signup_login_flow(eng):
    ok, uid = store.create_user(eng, "Asha", "Asha@Example.com", "Passw0rdX")
    assert ok
    ok2, msg = store.create_user(eng, "Asha2", "asha@example.com", "Passw0rdX")
    assert not ok2 and "already exists" in msg                        # case-insensitive unique email
    assert not store.create_user(eng, "A", "bad", "x")[0]
    user, _ = store.authenticate(eng, "asha@example.com", "Passw0rdX")
    assert user and user["role"] == "resident"
    bad, msg = store.authenticate(eng, "asha@example.com", "wrong")
    assert bad is None
    stored = store.df(eng, "SELECT password_hash FROM AppUser WHERE user_id=:u", {"u": uid})["password_hash"].iloc[0]
    assert stored.startswith("pbkdf2_sha256$") and "Passw0rdX" not in stored


def test_login_lockout_after_5_failures(eng):
    store.create_user(eng, "Lock Me", "lock@example.com", "Passw0rdX")
    for _ in range(5):
        assert store.authenticate(eng, "lock@example.com", "nope")[0] is None
    user, msg = store.authenticate(eng, "lock@example.com", "Passw0rdX")   # even the right password is blocked
    assert user is None and "Too many" in msg


def test_sql_injection_is_inert(eng):
    user, _ = store.authenticate(eng, "' OR '1'='1' --", "x")
    assert user is None
    ok, uid = store.create_user(eng, "Bobby'); DROP TABLE Zone;--", "bobby@example.com", "Passw0rdX")
    assert ok
    assert len(store.df(eng, "SELECT * FROM Zone")) == 12              # table still there
    ok, rid = store.submit_report(eng, uid, zid(eng, "Chennai"), "Flooded road", 2, "x'); DELETE FROM Zone; -- long enough")
    assert ok
    assert len(store.df(eng, "SELECT * FROM Zone")) == 12


def test_deactivated_user_cannot_login(eng):
    ok, uid = store.create_user(eng, "Gone", "gone@example.com", "Passw0rdX")
    store.set_active(eng, uid, uid, False)
    user, msg = store.authenticate(eng, "gone@example.com", "Passw0rdX")
    assert user is None and "deactivated" in msg


def test_report_lifecycle_and_rate_limit(eng):
    ok, uid = store.create_user(eng, "Reporter", "rep@example.com", "Passw0rdX")
    ok, rid = store.submit_report(eng, uid, zid(eng, "Guwahati"), "Flooded road", 2, "Main road waterlogged near the bridge")
    assert ok
    row = store.df(eng, "SELECT status, verified FROM HazardReport WHERE report_id=:r", {"r": rid}).iloc[0]
    assert row["status"] == "pending" and not row["verified"]
    store.review_report(eng, rid, uid, "verified")
    row = store.df(eng, "SELECT status, verified FROM HazardReport WHERE report_id=:r", {"r": rid}).iloc[0]
    assert row["status"] == "verified" and row["verified"]
    assert not store.submit_report(eng, uid, zid(eng, "Guwahati"), "Other", 1, "short")[0]
    for i in range(9):
        assert store.submit_report(eng, uid, zid(eng, "Guwahati"), "Other", 1, f"Report number {i} with enough text")[0]
    ok, msg = store.submit_report(eng, uid, zid(eng, "Guwahati"), "Other", 1, "One too many reports in an hour")
    assert not ok and "limit" in msg


def test_shelter_update_trigger_and_constraints(eng):
    sid = int(store.df(eng, "SELECT shelter_id FROM Shelter WHERE name='Chennai Corp. School Shelter'")["shelter_id"].iloc[0])
    before = len(store.df(eng, "SELECT * FROM ShelterAlert WHERE shelter_id=:s", {"s": sid}))
    assert store.update_shelter(eng, None, sid, 200)[0]
    assert len(store.df(eng, "SELECT * FROM ShelterAlert WHERE shelter_id=:s", {"s": sid})) == before + 1
    assert store.update_shelter(eng, None, sid, 200)[0]               # still full -> no duplicate alert
    assert len(store.df(eng, "SELECT * FROM ShelterAlert WHERE shelter_id=:s", {"s": sid})) == before + 1
    assert not store.update_shelter(eng, None, sid, 201)[0]           # app-level guard
    with pytest.raises((IntegrityError, DBAPIError)):                  # DB-level guard
        store.exe(eng, "UPDATE Shelter SET current_occupancy = 999 WHERE shelter_id=:s", {"s": sid})
    with pytest.raises((IntegrityError, DBAPIError)):
        store.exe(eng, "INSERT INTO Shelter (name, zone_id, total_capacity) VALUES ('x', 99999, 10)")
    with pytest.raises((IntegrityError, DBAPIError)):
        store.exe(eng, "INSERT INTO Country (name) VALUES ('India')")


def test_alerts_manual_expiry_and_validation(eng):
    z = zid(eng, "Mumbai")
    aid = store.create_alert(eng, z, "warning", "Test alert", "msg", "manual", None, 24)
    assert aid in store.active_alerts(eng)["alert_id"].tolist()
    store.exe(eng, "UPDATE AlertNotice SET expires_at = now() - interval '1 hour' WHERE alert_id=:a", {"a": aid})
    assert aid not in store.active_alerts(eng)["alert_id"].tolist()   # auto-expired
    with pytest.raises(ValueError):
        store.create_alert(eng, z, "catastrophe", "bad")


def test_scan_creates_weather_and_quake_alerts_once(eng):
    store.exe(eng, "DELETE FROM AlertNotice")
    fake_fc = lambda lat, lon: {"dates": ["d1", "d2", "d3"], "rain_mm": [10, 130, 5], "wind_kmh": [20, 30, 25]}
    fake_q = lambda: [{"mag": 6.1, "place": "Test Sea", "lat": 32.8, "lon": 130.7, "time": 0}]
    made = store.scan_and_publish_alerts(eng, fake_fc, fake_q, notify=False)
    titles = [m["title"] for m in made]
    assert any(t.startswith("Weather warning") for t in titles)       # 130 mm -> level 2 -> warning
    assert any(t.startswith("Earthquake") for t in titles)
    n1 = len(store.active_alerts(eng))
    store.scan_and_publish_alerts(eng, fake_fc, fake_q, notify=False)
    assert len(store.active_alerts(eng)) == n1                         # de-duplicated


def test_scan_survives_api_failure(eng):
    store.exe(eng, "DELETE FROM AlertNotice")
    assert store.scan_and_publish_alerts(eng, lambda a, b: None, lambda: None, notify=False) == []


def test_tasks_and_watchlist(eng):
    ok, uid = store.create_user(eng, "Vol", "vol@example.com", "Passw0rdX")
    ok, msg = store.link_volunteer(eng, uid, uid, zid(eng, "Chennai"), "Rescue")
    assert ok
    assert store.link_volunteer(eng, uid, uid, zid(eng, "Chennai"), "Rescue")[0] is False
    assert store.df(eng, "SELECT role FROM AppUser WHERE user_id=:u", {"u": uid})["role"].iloc[0] == "volunteer"
    vid = int(store.df(eng, "SELECT volunteer_id FROM Volunteer WHERE user_id=:u", {"u": uid})["volunteer_id"].iloc[0])
    ok, tid = store.create_task(eng, uid, vid, zid(eng, "Chennai"), "Deliver food kits")
    assert ok and not store.create_task(eng, uid, vid, zid(eng, "Chennai"), "  ")[0]
    store.update_task(eng, uid, tid, "done")
    assert store.df(eng, "SELECT status FROM Task WHERE task_id=:t", {"t": tid})["status"].iloc[0] == "done"
    z = zid(eng, "Chennai")
    assert store.toggle_watch(eng, uid, z) is True
    assert store.watched_zone_ids(eng, uid) == [z]
    assert store.toggle_watch(eng, uid, z) is False


def test_feedback_sus_and_metrics(eng):
    ok, uid = store.create_user(eng, "Tester", "tester@example.com", "Passw0rdX")
    store.save_feedback(eng, uid, 5, True, "Plan a Trip", "Great")
    assert store.save_sus(eng, uid, [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100
    m = store.ops_metrics(eng)
    assert m["feedback_n"] >= 1 and m["avg_sus"] == 100 and m["avg_rating"] == 5
    assert m["users_total"] >= 1


def test_audit_trail_written(eng):
    acts = set(store.df(eng, "SELECT DISTINCT action FROM AuditLog")["action"])
    assert {"signup", "login", "login_failed", "report_submitted", "shelter_updated"} <= acts
