import pytest
import core


def test_haversine_zero_and_known():
    assert core.haversine(13.0827, 80.2707, 13.0827, 80.2707) == pytest.approx(0, abs=1e-6)
    # Chennai -> Mumbai is about 1,030 km
    assert 1000 < core.haversine(13.0827, 80.2707, 19.0760, 72.8777) < 1060


def test_haversine_symmetry():
    a = core.haversine(35.68, 139.65, 34.69, 135.50)
    b = core.haversine(34.69, 135.50, 35.68, 139.65)
    assert a == pytest.approx(b)


@pytest.mark.parametrize("mm,expected", [(None, 0), (0, 0), (64.4, 0), (64.5, 1), (115.6, 2), (204.5, 3), (400, 3)])
def test_rain_classes(mm, expected):
    assert core.classify_rain(mm) == expected


@pytest.mark.parametrize("kmh,expected", [(None, 0), (30, 0), (62, 1), (89, 2), (118, 3)])
def test_wind_classes(kmh, expected):
    assert core.classify_wind(kmh) == expected


@pytest.mark.parametrize("mag,d,expected", [
    (None, 10, 0), (7.0, 250, 3), (6.2, 150, 2), (5.6, 100, 2), (5.1, 100, 1), (4.6, 50, 1), (4.6, 200, 0), (3.0, 10, 0)])
def test_quake_classes(mag, d, expected):
    assert core.classify_quake(mag, d) == expected


def test_zone_component_distance_softening():
    assert core.zone_component("High", 10) == 2
    assert core.zone_component("High", 80) == 1
    assert core.zone_component("Medium", 80) == 0
    assert core.zone_component("High", 200) == 0
    assert core.zone_component("High", None) == 0


def test_combine_risk():
    assert core.combine_risk(0, 0, 0, 0) == 0
    assert core.combine_risk(2, 0, 0, 0) == 2
    assert core.combine_risk(1, 1, 0, 0) == 1
    assert core.combine_risk(2, 2, 0, 0) == 3   # compounded
    assert core.combine_risk(0, 3, 0, 0) == 3


def test_precautions_include_live_conditions():
    base = core.precautions_for("Flood")
    more = core.precautions_for("Flood", weather_level=2, wind_level=1, quake_level=1)
    assert len(more) == len(base) + 3
    assert core.precautions_for("Unknown")  # never empty


def test_shelter_status():
    assert core.shelter_status(10, 100) == "Available"
    assert core.shelter_status(80, 100) == "Filling fast"
    assert core.shelter_status(100, 100) == "Full"
    assert core.shelter_status(1, 0) == "Unknown"


def test_role_permissions():
    assert core.can("resident", "report_hazard")
    assert not core.can("resident", "manage_shelters")
    assert not core.can("volunteer", "moderate_reports")
    assert core.can("coordinator", "moderate_reports")
    assert not core.can("coordinator", "manage_users")
    assert core.can("admin", "manage_users")
    assert not core.can(None, "view_public")
    assert not core.can("admin", "does_not_exist")
    assert not core.can("hacker", "manage_users")


def test_password_hash_roundtrip_and_uniqueness():
    h1, h2 = core.hash_password("Secret123"), core.hash_password("Secret123")
    assert h1 != h2                      # random salt
    assert core.verify_password("Secret123", h1)
    assert not core.verify_password("secret123", h1)
    assert not core.verify_password("x", "garbage")
    assert "Secret123" not in h1


def test_password_policy_and_email():
    assert core.password_problems("abc") != []
    assert core.password_problems("abcdefgh") == ["at least one number"]
    assert core.password_problems("abcdefg1") == []
    assert core.valid_email("a.b@c.co")
    assert not core.valid_email("nope")
    assert not core.valid_email("a@b")
    assert not core.valid_email("")


def test_sus_scoring():
    best = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
    worst = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]
    neutral = [3] * 10
    assert core.sus_score(best) == 100
    assert core.sus_score(worst) == 0
    assert core.sus_score(neutral) == 50
    with pytest.raises(ValueError):
        core.sus_score([3] * 9)
    with pytest.raises(ValueError):
        core.sus_score([6] + [3] * 9)
    assert core.sus_grade(80) == "Good"
