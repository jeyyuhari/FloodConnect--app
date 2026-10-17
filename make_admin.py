"""Create (or promote) an admin account. Usage: DB_URL=... ADMIN_NAME=.. ADMIN_EMAIL=.. ADMIN_PASSWORD=.. python make_admin.py"""
import os, sys
import store
eng = store.make_engine(os.environ["DB_URL"])
name, email, pw = os.environ["ADMIN_NAME"], os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"]
ok, res = store.create_user(eng, name, email, pw, role="admin")
if not ok and "already exists" in str(res):
    store.exe(eng, "UPDATE AppUser SET role='admin' WHERE lower(email)=:e", {"e": email})
    print("Existing account promoted to admin.")
elif ok:
    print("Admin account created.")
else:
    sys.exit(f"Failed: {res}")
