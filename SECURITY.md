# Security Policy

Filemindr processes personal documents, so security reports get priority.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead, use
GitHub's private vulnerability reporting on this repository ("Report a
vulnerability" under the Security tab). You'll get an acknowledgement within a
few days.

## Scope notes for self-hosters

- The bundled auth is **single-user dev-grade** (the bearer token is the
  seeded user's UUID). Do not expose a Filemindr instance to the public
  internet without putting real authentication in front of it — the intended
  seam is `app/core/auth.py::get_current_user`.
- Uploaded documents, OCR text, and extracted facts are stored unencrypted in
  Postgres and on the local filesystem (`STORAGE_DIR`). Disk/database
  encryption is your deployment's responsibility.
- API keys in `.env` are read at process start; never commit `.env` or
  anything under `secrets/`.
