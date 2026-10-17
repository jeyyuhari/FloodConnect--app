"""Scheduled job: pull live weather + earthquake data and publish alerts. Needs env DB_URL."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store
eng = store.make_engine(os.environ["DB_URL"])
made = store.scan_and_publish_alerts(eng)
print(f"alerts created: {len(made)}")
for m in made:
    print(" -", m["severity"], m["title"])
