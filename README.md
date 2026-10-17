# FloodConnect v2
Multi-hazard travel safety and disaster-response platform for India and Japan.
Streamlit + Supabase PostgreSQL. Login with roles (resident, volunteer, coordinator, admin), live weather/earthquake alerts,
moderation, tasks, usability survey, automated tests (CI) and scheduled alert scans.

Setup: add `DB_URL` to Streamlit secrets, run `python migrate.py` once, create an admin (see notes), deploy `app.py`.
