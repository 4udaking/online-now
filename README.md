# online-now

Every 15 minutes this repository reads the public "N members, M online" counter from the `t.me` pages of a fixed panel of public Telegram groups (`lists/panel.json`). The goal is to measure how presence on Telegram changes over the day.

- `collect_slot.py` handles one 15-minute slot. Requests are sequential and spread evenly across the slot.
- `data/<date>/<HHMM>.ndjson.gz.p7m` holds the raw observations, encrypted to `cert.pem` (CMS, AES-256). Only the key holder can read them.
- `data/health.ndjson` is plaintext and holds per-slot run health only: ok/stub counts, no online values.

Times are UTC.
