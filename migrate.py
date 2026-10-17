"""
migrate.py - idempotent database migration to FloodConnect v2.
Safe to run many times. Never drops data.
Usage (Colab or terminal):   DB_URL="postgresql://..." python migrate.py
"""
import os
import sys
from sqlalchemy import create_engine, text

V1_TABLES = """
CREATE TABLE IF NOT EXISTS Country (country_id SERIAL PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS DisasterEvent (event_id SERIAL PRIMARY KEY, name TEXT, event_type TEXT, start_date DATE, status TEXT);
CREATE TABLE IF NOT EXISTS Zone (
  zone_id SERIAL PRIMARY KEY, name TEXT, country_id INT REFERENCES Country(country_id),
  region TEXT, hazard_type TEXT, risk_level TEXT, latitude NUMERIC, longitude NUMERIC, notes TEXT);
CREATE TABLE IF NOT EXISTS Shelter (
  shelter_id SERIAL PRIMARY KEY, name TEXT, zone_id INT REFERENCES Zone(zone_id),
  total_capacity INT, current_occupancy INT DEFAULT 0, contact TEXT,
  CHECK (current_occupancy <= total_capacity));
CREATE TABLE IF NOT EXISTS Resource (resource_id SERIAL PRIMARY KEY, type TEXT, quantity INT, location TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS AppUser (user_id SERIAL PRIMARY KEY, role TEXT, name TEXT, contact TEXT);
CREATE TABLE IF NOT EXISTS Volunteer (
  volunteer_id SERIAL PRIMARY KEY, name TEXT, contact TEXT, skill TEXT,
  assigned_zone_id INT REFERENCES Zone(zone_id));
CREATE TABLE IF NOT EXISTS Task (
  task_id SERIAL PRIMARY KEY, volunteer_id INT REFERENCES Volunteer(volunteer_id),
  resource_id INT REFERENCES Resource(resource_id), zone_id INT REFERENCES Zone(zone_id),
  status TEXT, created_at TIMESTAMP DEFAULT now());
CREATE TABLE IF NOT EXISTS HazardReport (
  report_id SERIAL PRIMARY KEY, reporter_contact TEXT, zone_id INT REFERENCES Zone(zone_id),
  description TEXT, latitude NUMERIC, longitude NUMERIC, verified BOOLEAN DEFAULT false,
  reported_at TIMESTAMP DEFAULT now());
CREATE TABLE IF NOT EXISTS ShelterAlert (
  alert_id SERIAL PRIMARY KEY, shelter_id INT REFERENCES Shelter(shelter_id),
  message TEXT, triggered_at TIMESTAMP DEFAULT now());
CREATE TABLE IF NOT EXISTS TravelAdvisoryLog (
  advisory_id SERIAL PRIMARY KEY, queried_lat NUMERIC, queried_lon NUMERIC,
  matched_zone_id INT REFERENCES Zone(zone_id), risk_level TEXT, message TEXT,
  checked_at TIMESTAMP DEFAULT now());
"""

V2_ALTERS = """
ALTER TABLE AppUser ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE AppUser ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE AppUser ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE AppUser ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS ux_appuser_email ON AppUser (lower(email));
ALTER TABLE Volunteer ADD COLUMN IF NOT EXISTS user_id INT REFERENCES AppUser(user_id);
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS user_id INT REFERENCES AppUser(user_id);
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS severity INT DEFAULT 1;
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS reviewed_by INT REFERENCES AppUser(user_id);
ALTER TABLE HazardReport ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;
UPDATE HazardReport SET status = 'verified' WHERE verified = true AND (status IS NULL OR status = 'pending');
ALTER TABLE Task ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE Task ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE Task ADD COLUMN IF NOT EXISTS created_by INT REFERENCES AppUser(user_id);
ALTER TABLE Task ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();
ALTER TABLE Shelter ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP DEFAULT now();
ALTER TABLE TravelAdvisoryLog ADD COLUMN IF NOT EXISTS user_id INT REFERENCES AppUser(user_id);
ALTER TABLE TravelAdvisoryLog ADD COLUMN IF NOT EXISTS overall_level TEXT;
"""

V2_NEW_TABLES = """
CREATE TABLE IF NOT EXISTS AlertNotice (
  alert_id SERIAL PRIMARY KEY,
  zone_id INT REFERENCES Zone(zone_id),
  severity TEXT NOT NULL CHECK (severity IN ('info','advisory','warning','severe')),
  title TEXT NOT NULL, message TEXT,
  source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','weather','earthquake')),
  created_by INT REFERENCES AppUser(user_id),
  created_at TIMESTAMP DEFAULT now(), expires_at TIMESTAMP,
  is_active BOOLEAN DEFAULT true);
CREATE TABLE IF NOT EXISTS ZoneWatch (
  user_id INT REFERENCES AppUser(user_id) ON DELETE CASCADE,
  zone_id INT REFERENCES Zone(zone_id) ON DELETE CASCADE,
  created_at TIMESTAMP DEFAULT now(),
  PRIMARY KEY (user_id, zone_id));
CREATE TABLE IF NOT EXISTS AuditLog (
  log_id SERIAL PRIMARY KEY, user_id INT, email TEXT, action TEXT NOT NULL,
  detail TEXT, created_at TIMESTAMP DEFAULT now());
CREATE TABLE IF NOT EXISTS Feedback (
  feedback_id SERIAL PRIMARY KEY, user_id INT REFERENCES AppUser(user_id),
  rating INT CHECK (rating BETWEEN 1 AND 5), task_completed BOOLEAN,
  page TEXT, comment TEXT, created_at TIMESTAMP DEFAULT now());
CREATE TABLE IF NOT EXISTS SusResponse (
  sus_id SERIAL PRIMARY KEY, user_id INT REFERENCES AppUser(user_id),
  q1 INT, q2 INT, q3 INT, q4 INT, q5 INT, q6 INT, q7 INT, q8 INT, q9 INT, q10 INT,
  score NUMERIC, created_at TIMESTAMP DEFAULT now());
"""

# constraints that need an existence check (Postgres has no ADD CONSTRAINT IF NOT EXISTS)
GUARDED = {
    "chk_appuser_role": "ALTER TABLE AppUser ADD CONSTRAINT chk_appuser_role CHECK (role IN ('resident','volunteer','coordinator','admin'))",
    "chk_report_status": "ALTER TABLE HazardReport ADD CONSTRAINT chk_report_status CHECK (status IN ('pending','verified','rejected'))",
    "chk_report_severity": "ALTER TABLE HazardReport ADD CONSTRAINT chk_report_severity CHECK (severity BETWEEN 1 AND 3)",
    "chk_task_status": "ALTER TABLE Task ADD CONSTRAINT chk_task_status CHECK (status IN ('assigned','in_progress','done','cancelled'))",
    "chk_shelter_nonneg": "ALTER TABLE Shelter ADD CONSTRAINT chk_shelter_nonneg CHECK (current_occupancy >= 0 AND total_capacity > 0)",
}

TRIGGERS = """
CREATE OR REPLACE FUNCTION flag_shelter_full() RETURNS TRIGGER AS $$
BEGIN
  IF NEW.current_occupancy >= NEW.total_capacity AND OLD.current_occupancy < NEW.total_capacity THEN
    INSERT INTO ShelterAlert (shelter_id, message)
    VALUES (NEW.shelter_id, NEW.name || ' has reached full capacity');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_flag_shelter_full ON Shelter;
CREATE TRIGGER trg_flag_shelter_full AFTER UPDATE OF current_occupancy ON Shelter
  FOR EACH ROW EXECUTE FUNCTION flag_shelter_full();

CREATE OR REPLACE FUNCTION touch_shelter() RETURNS TRIGGER AS $$
BEGIN
  NEW.last_updated = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_touch_shelter ON Shelter;
CREATE TRIGGER trg_touch_shelter BEFORE UPDATE OF current_occupancy, total_capacity ON Shelter
  FOR EACH ROW EXECUTE FUNCTION touch_shelter();
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS ix_zone_country ON Zone (country_id);
CREATE INDEX IF NOT EXISTS ix_shelter_zone ON Shelter (zone_id);
CREATE INDEX IF NOT EXISTS ix_report_zone_status ON HazardReport (zone_id, status);
CREATE INDEX IF NOT EXISTS ix_report_user ON HazardReport (user_id, reported_at);
CREATE INDEX IF NOT EXISTS ix_alert_active ON AlertNotice (is_active, zone_id);
CREATE INDEX IF NOT EXISTS ix_audit_email ON AuditLog (email, action, created_at);
CREATE INDEX IF NOT EXISTS ix_task_volunteer ON Task (volunteer_id, status);
"""

ALL_TABLES = ["country", "disasterevent", "zone", "shelter", "resource", "appuser", "volunteer", "task",
              "hazardreport", "shelteralert", "traveladvisorylog", "alertnotice", "zonewatch", "auditlog",
              "feedback", "susresponse"]


def _run_script(conn, script):
    for stmt in [s.strip() for s in script.split(";\n") if s.strip()]:
        conn.exec_driver_sql(stmt if stmt.endswith(";") else stmt + ";")


def seed_if_empty(conn):
    n = conn.exec_driver_sql("SELECT COUNT(*) FROM Zone").scalar()
    if n:
        return False
    conn.exec_driver_sql("INSERT INTO Country (name) VALUES ('India'), ('Japan') ON CONFLICT (name) DO NOTHING")
    cid = {r[1]: r[0] for r in conn.exec_driver_sql("SELECT country_id, name FROM Country").fetchall()}
    zones = [
        ("Chennai", "India", "Tamil Nadu", "Flood", "High", 13.0827, 80.2707, "Low-lying coastal city, recurring monsoon flooding"),
        ("Mumbai", "India", "Maharashtra", "Flood", "High", 19.0760, 72.8777, "Severe monsoon waterlogging, coastal low-lying areas"),
        ("Alappuzha", "India", "Kerala", "Flood", "High", 9.4981, 76.3388, "Backwater region, major 2018 Kerala floods"),
        ("Guwahati", "India", "Assam", "Flood", "High", 26.1445, 91.7362, "Brahmaputra basin, annual monsoon flooding"),
        ("Patna", "India", "Bihar", "Flood", "Medium", 25.5941, 85.1376, "Ganga basin flood-prone region"),
        ("Puri", "India", "Odisha", "Cyclone", "High", 19.8135, 85.8312, "Bay of Bengal coast, frequent cyclone landfall"),
        ("Kumamoto", "Japan", "Kyushu", "Flood", "High", 32.8031, 130.7079, "2020 Kyushu floods along Kuma River"),
        ("Hiroshima", "Japan", "Chugoku", "Landslide", "High", 34.3853, 132.4553, "Steep terrain, 2018 Japan floods landslides"),
        ("Nagano", "Japan", "Chubu", "Flood", "Medium", 36.6513, 138.1810, "2019 Typhoon Hagibis river flooding"),
        ("Edogawa", "Japan", "Tokyo", "Flood", "High", 35.7066, 139.8683, "Below sea-level ward, designated high flood-risk zone"),
        ("Fukuoka", "Japan", "Kyushu", "Heavy Rain", "Medium", 33.5904, 130.4017, "2017 Northern Kyushu heavy rain disaster"),
        ("Wakayama", "Japan", "Kansai", "Landslide", "Medium", 34.2261, 135.1675, "Mountainous terrain, heavy-rain landslide risk"),
    ]
    for n_, c, reg, hz, rk, la, lo, nt in zones:
        conn.execute(text("INSERT INTO Zone (name,country_id,region,hazard_type,risk_level,latitude,longitude,notes) "
                          "VALUES (:n,:c,:r,:h,:k,:la,:lo,:nt)"),
                     dict(n=n_, c=cid[c], r=reg, h=hz, k=rk, la=la, lo=lo, nt=nt))
    zid = {r[1]: r[0] for r in conn.exec_driver_sql("SELECT zone_id, name FROM Zone").fetchall()}
    for n_, z, cap, occ, ct in [
        ("Chennai Corp. School Shelter", "Chennai", 200, 80, "+91-9000000001"),
        ("Mumbai BMC Relief Center", "Mumbai", 300, 150, "+91-9000000002"),
        ("Alappuzha Community Hall", "Alappuzha", 120, 120, "+91-9000000003"),
        ("Guwahati Relief Camp", "Guwahati", 150, 60, "+91-9000000004"),
        ("Kumamoto Evacuation Center", "Kumamoto", 180, 90, "+81-9000000005"),
        ("Edogawa Ward Shelter", "Edogawa", 250, 100, "+81-9000000006")]:
        conn.execute(text("INSERT INTO Shelter (name,zone_id,total_capacity,current_occupancy,contact) VALUES (:n,:z,:c,:o,:t)"),
                     dict(n=n_, z=zid[z], c=cap, o=occ, t=ct))
    for t_, q, l, s in [("Boat", 10, "Chennai depot", "available"), ("Food Kit", 500, "Mumbai depot", "available"),
                        ("Medical Kit", 80, "Alappuzha depot", "available"), ("Food Kit", 300, "Kumamoto depot", "available")]:
        conn.execute(text("INSERT INTO Resource (type,quantity,location,status) VALUES (:t,:q,:l,:s)"), dict(t=t_, q=q, l=l, s=s))
    for n_, c, sk, z in [("A. Kumar", "+91-9111111111", "Rescue", "Chennai"), ("S. Nair", "+91-9222222222", "Medical", "Alappuzha"),
                         ("Y. Tanaka", "+81-9333333333", "Rescue", "Kumamoto"), ("M. Sato", "+81-9444444444", "Logistics", "Edogawa")]:
        conn.execute(text("INSERT INTO Volunteer (name,contact,skill,assigned_zone_id) VALUES (:n,:c,:s,:z)"),
                     dict(n=n_, c=c, s=sk, z=zid[z]))
    return True


def migrate(engine, verbose=True):
    log = (lambda m: print(m)) if verbose else (lambda m: None)
    with engine.begin() as conn:
        _run_script(conn, V1_TABLES);       log("v1 tables ensured")
        _run_script(conn, V2_ALTERS);       log("v2 columns added")
        _run_script(conn, V2_NEW_TABLES);   log("v2 tables ensured")
        for name, ddl in GUARDED.items():
            exists = conn.execute(text("SELECT 1 FROM pg_constraint WHERE conname = :n"), dict(n=name)).scalar()
            if not exists:
                conn.exec_driver_sql(ddl)
        log("constraints ensured")
        # triggers contain $$ blocks -> executed as whole statements
        for stmt in _split_triggers(TRIGGERS):
            conn.exec_driver_sql(stmt)
        log("triggers ensured")
        _run_script(conn, INDEXES);         log("indexes ensured")
        for t in ALL_TABLES:                 # lock down Supabase's public REST API
            conn.exec_driver_sql(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        log("row level security enabled on all tables")
        if seed_if_empty(conn):
            log("seeded demo dataset (12 zones, 6 shelters, 4 resources, 4 volunteers)")
        else:
            log("existing zone data kept (no re-seed)")
    return True


def _split_triggers(script):
    """Split the TRIGGERS script into whole statements, keeping $$...$$ bodies intact."""
    stmts, cur, in_body = [], [], False
    for line in script.splitlines():
        cur.append(line)
        if "$$" in line:
            in_body = not in_body if line.count("$$") == 1 else in_body
        if not in_body and line.strip().endswith(";"):
            s = "\n".join(cur).strip()
            if s:
                stmts.append(s)
            cur = []
    return stmts


if __name__ == "__main__":
    url = os.environ.get("DB_URL")
    if not url:
        sys.exit("Set the DB_URL environment variable first.")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    migrate(create_engine(url))
    print("Migration complete.")
