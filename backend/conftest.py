"""
Root test configuration.

Nothing lives here yet, deliberately. An earlier version tried to drop the test
database after each session; it could never succeed. Supabase's *session*
pooler (Supavisor) holds a client backend open on the test database and
re-establishes it immediately after any terminate, so `DROP DATABASE` always
fails with `ObjectInUse`. Django then reused the leftover database anyway.

pytest.ini therefore passes `--reuse-db`, which is the honest version of that
behaviour: keep one test database, reapply migrations only when the models
change. Deleting it is a manual operation, and `python manage.py flush` is the
supported way to reset it.
"""
