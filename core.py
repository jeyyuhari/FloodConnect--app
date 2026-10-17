"""
core.py - pure logic for FloodConnect (no database, no Streamlit, no network).
Everything here is unit-tested in tests/test_core.py.
"""
import math
import re
import hmac
import hashlib
import secrets

# --------------------------------------------------------------------------- geo
def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ risk levels
# 0 = Low, 1 = Moderate, 2 = High, 3 = Severe
LEVELS = ["Low", "Moderate", "High", "Severe"]
LEVEL_COLORS = {0: "#16A34A", 1: "#F59E0B", 2: "#EA580C", 3: "#DC2626"}
SEVERITY_TO_LEVEL = {"info": 0, "advisory": 1, "warning": 2, "severe": 3}
LEVEL_TO_SEVERITY = {v: k for k, v in SEVERITY_TO_LEVEL.items()}


def static_level(risk_level: str) -> int:
    return {"High": 2, "Medium": 1, "Low": 0}.get(risk_level, 0)


def classify_rain(mm_24h):
    """IMD-style 24h rainfall categories: heavy >=64.5, very heavy >=115.6, extremely heavy >=204.5 mm."""
    if mm_24h is None:
        return 0
    if mm_24h >= 204.5:
        return 3
    if mm_24h >= 115.6:
        return 2
    if mm_24h >= 64.5:
        return 1
    return 0


def classify_wind(kmh):
    """Beaufort-based: gale >=62 km/h (moderate), storm >=89 (high), violent storm >=118 (severe)."""
    if kmh is None:
        return 0
    if kmh >= 118:
        return 3
    if kmh >= 89:
        return 2
    if kmh >= 62:
        return 1
    return 0


def classify_quake(magnitude, distance_km):
    """Earthquake level from magnitude and distance to the traveller / zone."""
    if magnitude is None or distance_km is None:
        return 0
    if magnitude >= 6.5 and distance_km <= 300:
        return 3
    if magnitude >= 6.0 and distance_km <= 200:
        return 2
    if magnitude >= 5.0 and distance_km <= 150:
        return 2 if magnitude >= 5.5 else 1
    if magnitude >= 4.5 and distance_km <= 100:
        return 1
    return 0


def zone_component(risk_level, distance_km, radius_km=150):
    """Static zone risk, softened with distance. Nothing counts beyond the radius."""
    if distance_km is None or distance_km > radius_km:
        return 0
    base = static_level(risk_level)
    if distance_km > 50:
        base = max(0, base - 1)
    return base


def combine_risk(zone=0, weather=0, quake=0, alert=0):
    """
    Overall level = worst single component. If two or more components are High (>=2),
    the situation is compounded and is raised to Severe.
    """
    comps = [zone, weather, quake, alert]
    level = max(comps)
    if sum(1 for c in comps if c >= 2) >= 2:
        level = 3
    return level


# ---------------------------------------------------------------- precautions
PRECAUTIONS = {
    "Flood": [
        "Avoid low-lying roads, underpasses and riverbanks; never drive through flowing water.",
        "Keep an emergency kit ready: drinking water, torch, power bank, documents in a waterproof bag, essential medicines.",
        "Note the nearest shelter and two evacuation routes before you arrive.",
        "Follow official alerts; move to higher ground early rather than late.",
    ],
    "Cyclone": [
        "Check official cyclone warnings before and during travel; postpone coastal travel during a warning.",
        "Avoid beaches, ports and coastal roads; stay away from hoardings, trees and power lines.",
        "Keep phones charged and carry cash; know the nearest cyclone shelter.",
    ],
    "Landslide": [
        "Avoid hill and slope roads during and just after heavy rain.",
        "Watch for warning signs: cracked ground, leaning trees or poles, sudden muddy water, rumbling sounds.",
        "Travel in daylight and delay the trip if a landslide alert is active.",
    ],
    "Heavy Rain": [
        "Avoid non-essential travel during heavy-rain warnings.",
        "Expect waterlogged roads and delays; allow extra time and keep emergency contacts handy.",
    ],
}
WEATHER_PRECAUTION = "Heavy rain is forecast: carry rain protection, avoid underpasses, and re-check conditions before departing."
WIND_PRECAUTION = "Strong winds are forecast: avoid open coastal or hill roads, and secure loose belongings."
QUAKE_PRECAUTION = "A recent earthquake occurred nearby: expect aftershocks, avoid damaged structures and follow official guidance (Drop, Cover, Hold On)."

EMERGENCY = {
    "India": ["112 \u2013 National emergency number", "1078 \u2013 NDMA / disaster helpline"],
    "Japan": ["110 \u2013 Police", "119 \u2013 Fire and ambulance"],
}


def precautions_for(hazard_type, weather_level=0, wind_level=0, quake_level=0):
    items = list(PRECAUTIONS.get(hazard_type, ["Stay alert and follow local authority instructions."]))
    if weather_level >= 1:
        items.append(WEATHER_PRECAUTION)
    if wind_level >= 1:
        items.append(WIND_PRECAUTION)
    if quake_level >= 1:
        items.append(QUAKE_PRECAUTION)
    return items


# ------------------------------------------------------------------ shelters
def shelter_status(occupancy, capacity):
    if capacity <= 0:
        return "Unknown"
    pct = occupancy / capacity
    if pct >= 1:
        return "Full"
    if pct >= 0.8:
        return "Filling fast"
    return "Available"


# ------------------------------------------------------------ roles / access
ROLES = ["resident", "volunteer", "coordinator", "admin"]
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}

# permission -> minimum role
PERMISSIONS = {
    "view_public": "resident",
    "report_hazard": "resident",
    "give_feedback": "resident",
    "view_resources": "volunteer",
    "my_tasks": "volunteer",
    "manage_shelters": "coordinator",
    "moderate_reports": "coordinator",
    "assign_tasks": "coordinator",
    "publish_alerts": "coordinator",
    "manage_volunteers": "coordinator",
    "manage_users": "admin",
    "view_audit": "admin",
    "view_ops": "admin",
}


def can(role, permission):
    """Guests (role=None) can only use public pages; handled by the caller."""
    if role not in ROLE_RANK or permission not in PERMISSIONS:
        return False
    return ROLE_RANK[role] >= ROLE_RANK[PERMISSIONS[permission]]


# ------------------------------------------------------------------ passwords
_ITER = 200_000


def hash_password(password: str, salt: str = None, iterations: int = _ITER) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def valid_email(email: str) -> bool:
    return bool(email) and len(email) <= 254 and bool(EMAIL_RE.match(email.strip()))


def password_problems(pw: str):
    """Return a list of problems (empty list = acceptable password)."""
    problems = []
    if len(pw) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Za-z]", pw):
        problems.append("at least one letter")
    if not re.search(r"\d", pw):
        problems.append("at least one number")
    return problems


# ---------------------------------------------------------------------- SUS
SUS_QUESTIONS = [
    "I think that I would like to use this system frequently.",
    "I found the system unnecessarily complex.",
    "I thought the system was easy to use.",
    "I think that I would need the support of a technical person to be able to use this system.",
    "I found the various functions in this system were well integrated.",
    "I thought there was too much inconsistency in this system.",
    "I would imagine that most people would learn to use this system very quickly.",
    "I found the system very cumbersome to use.",
    "I felt very confident using the system.",
    "I needed to learn a lot of things before I could get going with this system.",
]


def sus_score(answers):
    """Standard System Usability Scale scoring. answers = 10 ints in 1..5. Returns 0..100."""
    if len(answers) != 10 or any(a < 1 or a > 5 for a in answers):
        raise ValueError("SUS needs 10 answers between 1 and 5")
    total = 0
    for i, a in enumerate(answers, start=1):
        total += (a - 1) if i % 2 == 1 else (5 - a)
    return total * 2.5


def sus_grade(score):
    if score >= 85:
        return "Excellent"
    if score >= 72:
        return "Good"
    if score >= 68:
        return "Above average"
    if score >= 51:
        return "OK / below average"
    return "Poor"
