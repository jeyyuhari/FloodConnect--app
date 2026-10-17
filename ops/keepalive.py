"""Scheduled job: touch the database so a free Supabase project is never paused for inactivity."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store
eng = store.make_engine(os.environ["DB_URL"])
print("zones:", int(store.df(eng, "SELECT COUNT(*) AS n FROM Zone")["n"].iloc[0]))
