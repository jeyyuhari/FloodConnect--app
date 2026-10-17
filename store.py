"""
store.py - all database operations for FloodConnect v2 (no Streamlit imports, so the
scheduled scripts and the tests can use it too). Every write uses bound parameters.
"""
import os
import smtplib
from email.message import EmailMessage
import pandas as pd
from sqlalchemy import create_engine, text

import core
import services


# ------------------------------------------------------------------ plumbing
def make_engine(url):
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=300,
                         connect_args={"connect_timeout": 10})


def df(engine, sql, params=None):
    with engine.connect() as conn:
        out = pd.read_sql(text(sql), conn, params=params or {})
    for c in out.columns:  # NUMERIC -> float for easy maths / maps
        if out[c].dtype == object and len(out) and out[c].map(lambda v: v.__class__.__name__ == "Decimal").all():
            out[c] = out[c].astype(float)
    return out


def exe(engine, sql, params=None):
    """Run a write. Returns the first column of the first row if the SQL has RETURNING, else rowcount."""
    with engine.begin() as conn:
        res = conn.execute(text(sql), params or {})
        if res.returns_rows:
            row = res.fetchone()
            return row[0] if row else None
        return res.rowcount


def audit(engine, action, detail="", user_id=None, email=None):
    try:
        exe(engine, "INSERT INTO AuditLog (user_id, email, action, detail) VALUES (:u,:e,:a,:d)",
            dict(u=user_id, e=email, a=action, d=detail[:500]))
    except Exception:
        pass


# ------------------------------------------------------------------- accounts
def create_user(engine, name, email, password, role="resident", contact=None):
    name, email = (name or "").strip(), (email or "").strip().lower()
    if len(name) < 2:
        return False, "Please enter your name."
    if not core.valid_email(email):
        return False, "Please enter a valid email address."
    probs = core.password_problems(password or "")
    if probs:
        return False, "Password needs: " + ", ".join(probs) + "."
    if role not in core.ROLES:
        return False, "Invalid role."
    if exe(engine, "SELECT 1 FROM AppUser WHERE lower(email) = :e", dict(e=email)):
        return False, "An account with this email already exists."
    uid = exe(engine, "INSERT INTO AppUser (role, name, contact, email, password_hash) "
                      "VALUES (:r,:n,:c,:e,:p) RETURNING user_id",
              dict(r=role, n=name, c=contact, e=email, p=core.hash_password(password)))
    audit(engine, "signup", f"role={role}", uid, email)
    return True, uid


def authenticate(engine, email, password):
    """Returns (user_dict | None, message). Locks an email for 15 min after 5 failed attempts."""
    email = (email or "").strip().lower()
    failed = df(engine, "SELECT COUNT(*) AS n FROM AuditLog WHERE email = :e AND action = 'login_failed' "
                        "AND created_at > now() - interval '15 minutes'", dict(e=email))["n"].iloc[0]
    if failed >= 5:
        return None, "Too many failed attempts. Please try again in 15 minutes."
    u = df(engine, "SELECT user_id, name, email, role, password_hash, is_active FROM AppUser WHERE lower(email) = :e",
           dict(e=email))
    if u.empty or not u.iloc[0]["password_hash"] or not core.verify_password(password or "", u.iloc[0]["password_hash"]):
        audit(engine, "login_failed", "", None, email)
        return None, "Incorrect email or password."
    row = u.iloc[0]
    if not row["is_active"]:
        return None, "This account has been deactivated. Contact an administrator."
    audit(engine, "login", "", int(row["user_id"]), email)
    return {"user_id": int(row["user_id"]), "name": row["name"], "email": row["email"], "role": row["role"]}, "ok"


def set_role(engine, admin_id, user_id, role):
    if role not in core.ROLES:
        raise ValueError("bad role")
    exe(engine, "UPDATE AppUser SET role = :r WHERE user_id = :u", dict(r=role, u=user_id))
    audit(engine, "role_changed", f"user={user_id} role={role}", admin_id)


def set_active(engine, admin_id, user_id, active):
    exe(engine, "UPDATE AppUser SET is_active = :a WHERE user_id = :u", dict(a=bool(active), u=user_id))
    audit(engine, "user_active_changed", f"user={user_id} active={active}", admin_id)


# --------------------------------------------------------------------- reports
def submit_report(engine, user_id, zone_id, category, severity, description, contact=None):
    description = (description or "").strip()
    if len(description) < 10:
        return False, "Please describe what you saw in at least 10 characters."
    if len(description) > 1000:
        return False, "Description is too long (max 1000 characters)."
    recent = df(engine, "SELECT COUNT(*) AS n FROM HazardReport WHERE user_id = :u AND reported_at > now() - interval '1 hour'",
                dict(u=user_id))["n"].iloc[0]
    if recent >= 10:
        return False, "You have reached the limit of 10 reports per hour. Please try again later."
    z = df(engine, "SELECT latitude, longitude FROM Zone WHERE zone_id = :z", dict(z=zone_id))
    if z.empty:
        return False, "Unknown zone."
    rid = exe(engine, "INSERT INTO HazardReport (user_id, reporter_contact, zone_id, category, severity, description, latitude, longitude, status, verified) "
                      "VALUES (:u,:c,:z,:cat,:sev,:d,:la,:lo,'pending',false) RETURNING report_id",
              dict(u=user_id, c=contact, z=zone_id, cat=category, sev=int(severity), d=description,
                   la=float(z.iloc[0]["latitude"]), lo=float(z.iloc[0]["longitude"])))
    audit(engine, "report_submitted", f"report={rid} zone={zone_id}", user_id)
    return True, rid


def review_report(engine, report_id, reviewer_id, status):
    if status not in ("verified", "rejected", "pending"):
        raise ValueError("bad status")
    exe(engine, "UPDATE HazardReport SET status=:s, verified=:v, reviewed_by=:r, reviewed_at=now() WHERE report_id=:i",
        dict(s=status, v=(status == "verified"), r=reviewer_id, i=report_id))
    audit(engine, "report_reviewed", f"report={report_id} status={status}", reviewer_id)


# -------------------------------------------------------------------- shelters
def update_shelter(engine, user_id, shelter_id, occupancy):
    row = df(engine, "SELECT total_capacity, name FROM Shelter WHERE shelter_id = :s", dict(s=shelter_id))
    if row.empty:
        return False, "Unknown shelter."
    cap = int(row.iloc[0]["total_capacity"])
    if occupancy < 0 or occupancy > cap:
        return False, f"Occupancy must be between 0 and {cap}."
    exe(engine, "UPDATE Shelter SET current_occupancy = :o WHERE shelter_id = :s", dict(o=int(occupancy), s=shelter_id))
    audit(engine, "shelter_updated", f"shelter={shelter_id} occupancy={occupancy}", user_id)
    return True, "Updated."


# ---------------------------------------------------------------------- alerts
def create_alert(engine, zone_id, severity, title, message="", source="manual", created_by=None, expires_hours=24):
    if severity not in core.SEVERITY_TO_LEVEL:
        raise ValueError("bad severity")
    aid = exe(engine, "INSERT INTO AlertNotice (zone_id, severity, title, message, source, created_by, expires_at) "
                      "VALUES (:z,:s,:t,:m,:src,:cb, now() + (:h * interval '1 hour')) RETURNING alert_id",
              dict(z=zone_id, s=severity, t=title[:200], m=message[:1000], src=source, cb=created_by, h=int(expires_hours)))
    audit(engine, "alert_created", f"alert={aid} source={source} sev={severity}", created_by)
    return aid


def deactivate_alert(engine, user_id, alert_id):
    exe(engine, "UPDATE AlertNotice SET is_active = false WHERE alert_id = :a", dict(a=alert_id))
    audit(engine, "alert_deactivated", f"alert={alert_id}", user_id)


def active_alerts(engine, zone_ids=None):
    exe(engine, "UPDATE AlertNotice SET is_active = false WHERE is_active AND expires_at IS NOT NULL AND expires_at < now()")
    out = df(engine, "SELECT a.alert_id, a.zone_id, z.name AS zone, a.severity, a.title, a.message, a.source, a.created_at, a.expires_at "
                     "FROM AlertNotice a LEFT JOIN Zone z ON z.zone_id = a.zone_id WHERE a.is_active ORDER BY "
                     "CASE a.severity WHEN 'severe' THEN 0 WHEN 'warning' THEN 1 WHEN 'advisory' THEN 2 ELSE 3 END, a.created_at DESC")
    if zone_ids is not None:
        out = out[out["zone_id"].isin(zone_ids) | out["zone_id"].isna()]
    return out


def scan_and_publish_alerts(engine, get_forecast=None, get_quakes=None, notify=True):
    """
    Pull live forecast + earthquake data for every zone and publish AlertNotice rows
    for Moderate-or-worse conditions. De-duplicated: one live alert per zone+source per 12 h.
    Returns a list of dicts describing the alerts created. Used by the app (coordinator button)
    and by the scheduled GitHub Action (ops/scan_alerts.py).
    """
    get_forecast = get_forecast or services.forecast
    get_quakes = get_quakes or services.recent_quakes
    zones = df(engine, "SELECT zone_id, name, latitude, longitude FROM Zone")
    created, quakes = [], get_quakes()
    for _, z in zones.iterrows():
        zid, lat, lon = int(z["zone_id"]), float(z["latitude"]), float(z["longitude"])
        fc = get_forecast(lat, lon)
        if fc:
            rain = max([x for x in fc["rain_mm"] if x is not None] or [0])
            wind = max([x for x in fc["wind_kmh"] if x is not None] or [0])
            lvl = max(core.classify_rain(rain), core.classify_wind(wind))
            if lvl >= 1 and not _recent_alert(engine, zid, "weather"):
                what = []
                if core.classify_rain(rain) >= 1:
                    what.append(f"up to {rain:.0f} mm rain/day")
                if core.classify_wind(wind) >= 1:
                    what.append(f"winds up to {wind:.0f} km/h")
                sev = core.LEVEL_TO_SEVERITY[lvl]
                title = f"Weather {sev}: {z['name']}"
                msg = "Forecast for the next 3 days: " + " and ".join(what) + "."
                aid = create_alert(engine, zid, sev, title, msg, "weather", None, 24)
                created.append({"alert_id": aid, "zone_id": zid, "severity": sev, "title": title})
                if notify:
                    notify_watchers(engine, zid, title, msg)
        near = services.quakes_near(quakes, lat, lon, 300)
        if near:
            top = max(near, key=lambda q: core.classify_quake(q["mag"], q["distance_km"]) * 100 + q["mag"])
            lvl = core.classify_quake(top["mag"], top["distance_km"])
            if lvl >= 1 and not _recent_alert(engine, zid, "earthquake"):
                sev = core.LEVEL_TO_SEVERITY[lvl]
                title = f"Earthquake M{top['mag']:.1f} near {z['name']}"
                msg = f"{top['place']} ({top['distance_km']:.0f} km from the monitored zone). Expect possible aftershocks."
                aid = create_alert(engine, zid, sev, title, msg, "earthquake", None, 24)
                created.append({"alert_id": aid, "zone_id": zid, "severity": sev, "title": title})
                if notify:
                    notify_watchers(engine, zid, title, msg)
    return created


def _recent_alert(engine, zone_id, source):
    return bool(exe(engine, "SELECT 1 FROM AlertNotice WHERE zone_id=:z AND source=:s AND is_active "
                            "AND created_at > now() - interval '12 hours' LIMIT 1", dict(z=zone_id, s=source)))


# ------------------------------------------------------------------ notifying
def smtp_configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"))


def send_email(to_addrs, subject, body):
    """Optional email delivery (Gmail / any SMTP). Returns number sent; 0 if SMTP is not configured."""
    if not smtp_configured() or not to_addrs:
        return 0
    sent = 0
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            for to in to_addrs:
                m = EmailMessage()
                m["Subject"] = f"[FloodConnect] {subject}"
                m["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
                m["To"] = to
                m.set_content(body + "\n\n-- FloodConnect alerts. You receive this because you watch this zone.")
                s.send_message(m)
                sent += 1
    except Exception:
        pass
    return sent


def notify_watchers(engine, zone_id, subject, body):
    w = df(engine, "SELECT u.email FROM ZoneWatch w JOIN AppUser u ON u.user_id = w.user_id "
                   "WHERE w.zone_id = :z AND u.is_active AND u.email IS NOT NULL", dict(z=zone_id))
    return send_email(w["email"].tolist(), subject, body)


# ------------------------------------------------------------------ watchlist
def watched_zone_ids(engine, user_id):
    return df(engine, "SELECT zone_id FROM ZoneWatch WHERE user_id=:u", dict(u=user_id))["zone_id"].astype(int).tolist()


def toggle_watch(engine, user_id, zone_id):
    if zone_id in watched_zone_ids(engine, user_id):
        exe(engine, "DELETE FROM ZoneWatch WHERE user_id=:u AND zone_id=:z", dict(u=user_id, z=zone_id))
        return False
    exe(engine, "INSERT INTO ZoneWatch (user_id, zone_id) VALUES (:u,:z) ON CONFLICT DO NOTHING", dict(u=user_id, z=zone_id))
    return True


# ----------------------------------------------------------------------- tasks
def create_task(engine, creator_id, volunteer_id, zone_id, title, description="", resource_id=None):
    if not (title or "").strip():
        return False, "Task title is required."
    tid = exe(engine, "INSERT INTO Task (volunteer_id, resource_id, zone_id, status, title, description, created_by) "
                      "VALUES (:v,:r,:z,'assigned',:t,:d,:c) RETURNING task_id",
              dict(v=volunteer_id, r=resource_id, z=zone_id, t=title.strip()[:200], d=description[:1000], c=creator_id))
    audit(engine, "task_created", f"task={tid} volunteer={volunteer_id}", creator_id)
    return True, tid


def update_task(engine, user_id, task_id, status):
    if status not in ("assigned", "in_progress", "done", "cancelled"):
        raise ValueError("bad status")
    exe(engine, "UPDATE Task SET status=:s, updated_at=now() WHERE task_id=:t", dict(s=status, t=task_id))
    audit(engine, "task_updated", f"task={task_id} status={status}", user_id)


def link_volunteer(engine, coordinator_id, user_id, zone_id, skill):
    u = df(engine, "SELECT name, email FROM AppUser WHERE user_id=:u", dict(u=user_id))
    if u.empty:
        return False, "Unknown user."
    if exe(engine, "SELECT 1 FROM Volunteer WHERE user_id=:u", dict(u=user_id)):
        return False, "This user is already registered as a volunteer."
    exe(engine, "INSERT INTO Volunteer (name, contact, skill, assigned_zone_id, user_id) VALUES (:n,:c,:s,:z,:u)",
        dict(n=u.iloc[0]["name"], c=u.iloc[0]["email"], s=skill, z=zone_id, u=user_id))
    exe(engine, "UPDATE AppUser SET role = 'volunteer' WHERE user_id=:u AND role = 'resident'", dict(u=user_id))
    audit(engine, "volunteer_linked", f"user={user_id} zone={zone_id}", coordinator_id)
    return True, "Volunteer registered."


# -------------------------------------------------------------- advisory / feedback
def log_advisory(engine, user_id, lat, lon, zone_id, overall_label, message):
    exe(engine, "INSERT INTO TravelAdvisoryLog (queried_lat, queried_lon, matched_zone_id, risk_level, overall_level, message, user_id) "
                "VALUES (:la,:lo,:z,:r,:r,:m,:u)",
        dict(la=lat, lo=lon, z=zone_id, r=overall_label, m=message[:1000], u=user_id))


def save_feedback(engine, user_id, rating, task_completed, page, comment):
    exe(engine, "INSERT INTO Feedback (user_id, rating, task_completed, page, comment) VALUES (:u,:r,:t,:p,:c)",
        dict(u=user_id, r=int(rating), t=bool(task_completed), p=page, c=(comment or "")[:1000]))


def save_sus(engine, user_id, answers):
    score = core.sus_score(answers)
    cols = ",".join(f"q{i}" for i in range(1, 11))
    vals = ",".join(f":q{i}" for i in range(1, 11))
    params = {f"q{i}": int(a) for i, a in enumerate(answers, start=1)}
    params.update(u=user_id, s=score)
    exe(engine, f"INSERT INTO SusResponse (user_id, {cols}, score) VALUES (:u, {vals}, :s)", params)
    return score


# -------------------------------------------------------------------- metrics
def ops_metrics(engine):
    q = lambda sql: int(df(engine, sql)["n"].iloc[0])
    m = {
        "users_total": q("SELECT COUNT(*) AS n FROM AppUser"),
        "users_7d": q("SELECT COUNT(*) AS n FROM AppUser WHERE created_at > now() - interval '7 days'"),
        "logins_7d": q("SELECT COUNT(*) AS n FROM AuditLog WHERE action='login' AND created_at > now() - interval '7 days'"),
        "advisories_total": q("SELECT COUNT(*) AS n FROM TravelAdvisoryLog"),
        "advisories_7d": q("SELECT COUNT(*) AS n FROM TravelAdvisoryLog WHERE checked_at > now() - interval '7 days'"),
        "reports_total": q("SELECT COUNT(*) AS n FROM HazardReport"),
        "reports_verified": q("SELECT COUNT(*) AS n FROM HazardReport WHERE status='verified'"),
        "alerts_total": q("SELECT COUNT(*) AS n FROM AlertNotice"),
        "alerts_auto": q("SELECT COUNT(*) AS n FROM AlertNotice WHERE source <> 'manual'"),
        "tasks_done": q("SELECT COUNT(*) AS n FROM Task WHERE status='done'"),
        "feedback_n": q("SELECT COUNT(*) AS n FROM Feedback"),
        "sus_n": q("SELECT COUNT(*) AS n FROM SusResponse"),
    }
    fb = df(engine, "SELECT AVG(rating) AS a, AVG(CASE WHEN task_completed THEN 1.0 ELSE 0.0 END) AS c FROM Feedback")
    m["avg_rating"] = None if fb["a"].isna().iloc[0] else float(fb["a"].iloc[0])
    m["task_success_rate"] = None if fb["c"].isna().iloc[0] else float(fb["c"].iloc[0])
    s = df(engine, "SELECT AVG(score) AS a FROM SusResponse")
    m["avg_sus"] = None if s["a"].isna().iloc[0] else float(s["a"].iloc[0])
    return m
