# ARES Operator Manual & Deployment Guide

## 1. Deployment Guide
ARES is packaged as a Docker container.
**To Deploy**:
```bash
docker-compose --profile live up -d
```
For other modes, substitute `--profile live` with `dev`, `replay`, `paper`, or `shadow`.

## 2. Configuration Guide
Environment variables map to `AresConfig`.
* `BOT_MODE`: `DEV`, `REPLAY`, `SHADOW`, `PAPER`, `LIVE`
* `DELTA_API_KEY`: Mandatory for non-dev modes.
* `DELTA_API_SECRET`: Mandatory for non-dev modes.
* `SQLITE_DB_PATH`: Defaults to `/app/data/shadow_validation.db`
* `LOG_DIR`: Defaults to `/app/logs`

## 3. Disaster Recovery
If the server crashes, Docker Compose will automatically restart ARES (`restart: unless-stopped`).
The `RecoveryManager` guarantees idempotent recovery by:
1. Re-fetching Open Orders from Delta.
2. Synchronizing the Portfolio balances.
3. Resuming ExecutionStateMachine safely.

## 4. Upgrade & Rollback Procedures
**Upgrade**:
1. `git pull origin main`
2. `docker-compose build`
3. `docker-compose --profile shadow up -d` (Test in shadow first!)
4. `docker-compose --profile live up -d`

**Rollback**:
1. `git checkout <previous-tag>`
2. `docker-compose build`
3. `docker-compose --profile live up -d`

## 5. Troubleshooting
* **Database Locked**: Ensure no other process is reading SQLite without timeouts.
* **Network Failures**: `CircuitBreaker` will automatically trip and pause trading if WS/REST latency spikes.
