# WeMo Manager

Self-hosted web application for discovering, monitoring, and controlling Belkin WeMo
devices on a local network. Built with FastAPI, SQLAlchemy/SQLite, and `pywemo`.

The web UI has no external dependencies: all assets are served by the application, so it
works on networks without internet access.

## Features

- Discover devices by IP address or CIDR range, then save selected results.
- Control switches and dimmers from the device list or a device detail page.
- Track reachability and state through UPnP/GENA push subscriptions and periodic polling.
- Search, sort, filter by subnet, and choose visible columns; preferences persist per browser.
- Responsive tile layout on narrow screens.
- Live updates over server-sent events.
- Read-only weekly schedule calendar and consolidated rules summaries, cached per device.
- Inspect the raw on-device rules database.
- Reset a device, optionally clearing its Wi-Fi credentials.
- Connect factory-reset devices to Wi-Fi with the optional Android app.

## Requirements

| Component | Version |
| --- | --- |
| Python | 3.11 or later |
| Docker / Docker Compose | v2, for container deployment |
| Node.js, Android SDK, JDK | 20+, API 35, 21 — only to build the Android app |

The host must reach the WeMo devices directly on the LAN.

## Installation

```bash
make install
make run
```

Open `http://<host>:8000/`. Interactive API documentation is at `/docs`.

Without `make`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Usage

| Target | Action |
| --- | --- |
| `make help` | List available targets |
| `make install` | Create `.venv` and install the package with dev dependencies |
| `make run` | Foreground development server with autoreload |
| `make start` | Start the server in the background |
| `make stop` | Stop a running instance |
| `make restart` | Restart the background server |
| `make status` | Report whether an instance is running |
| `make test` | Run the test suite |
| `make logs` | Tail the application log |
| `make apk` | Build the Android app and stage it for download |
| `make deploy` | Build everything and update the Docker deployment |

Only one instance may run against a set of devices at a time. Startup takes an exclusive
lock on `WEMO_MANAGER_LOCK_FILE`; a second instance exits rather than corrupting device
subscription state.

## Docker deployment

Host networking is required so devices can deliver UPnP/GENA callbacks.

```bash
docker compose up -d --build wemo-manager
docker compose ps wemo-manager
```

`./data` is mounted at `/data`, holding the SQLite database, logs, process lock, and the
Android APK.

`deploy.sh` syncs a working tree into a deployment directory and rebuilds the container:

```bash
./deploy.sh                                   # defaults to /home/wemo-manager
WEMO_MANAGER_DEPLOY_DIR=/srv/wemo ./deploy.sh
```

It discards build outputs, runs the tests, builds the APK, syncs `app/` and the container
files, then rebuilds and waits for the health check.

Site-specific secrets belong in an untracked `.env.local` beside `docker-compose.yml`,
which Compose loads automatically when present.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `WEMO_MANAGER_DATABASE_URL` | `sqlite:///./wemo_manager.db` | SQLAlchemy database URL. |
| `WEMO_MANAGER_LOCK_FILE` | `wemo_manager.lock` | Single-instance lock file. |
| `WEMO_MANAGER_LOG_FILE` | `logs/wemo_manager.log` | Rotating log file. |
| `WEMO_MANAGER_FILE_LOG_LEVEL` | `INFO` | Minimum file log level. |
| `WEMO_MANAGER_CONSOLE_LOG_LEVEL` | `WARNING` | Minimum console log level. |
| `WEMO_MANAGER_LOG_MAX_BYTES` | `5242880` | Log rotation threshold in bytes. |
| `WEMO_MANAGER_LOG_BACKUP_COUNT` | `5` | Rotated log files retained. |
| `WEMO_MANAGER_APK_PATH` | `app/static/wemo-manager.apk` | APK served at `/api/setup/apk`. The Docker image sets `/data/wemo-manager.apk`. |
| `WEMO_MANAGER_WIFI_SSID` | unset | Seeds the Wi-Fi SSID when none is saved. |
| `WEMO_MANAGER_WIFI_PASSWORD` | unset | Seeds the Wi-Fi password when none is saved. |

Wi-Fi credentials are stored and returned in plaintext for use on the local network. The
application has no authentication; restrict access at the network level.

## Data

| Table | Contents | Recovery |
| --- | --- | --- |
| `devices` | Known devices and last-known state | Run a detect scan |
| `device_rules_cache` | Per-device schedule summaries | Refresh from devices |
| `settings` | Wi-Fi SSID and password | Re-enter, or seed from the environment |

At startup each table is compared against its model. If any columns differ, the database
is dropped and recreated.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Device list |
| `GET` | `/setup` | Setup page |
| `GET` | `/devices/{id}` | Device detail page |
| `GET` | `/api/devices` | List devices |
| `GET` | `/api/devices/events` | Server-sent event stream of table changes |
| `GET` | `/api/devices/default-network` | Active IPv4 CIDR and netmask of the host |
| `POST` | `/api/devices/detect` | Scan a CIDR or IP address |
| `POST` | `/api/devices/detect/commit` | Persist chosen results from the last scan |
| `POST` | `/api/devices/all-off` | Turn off all, or a given subset of, devices |
| `GET` | `/api/devices/{id}` | Device detail |
| `PATCH` | `/api/devices/{id}` | Update editable metadata |
| `DELETE` | `/api/devices/{id}` | Forget a device |
| `POST` | `/api/devices/{id}/state` | Set on/off state or brightness |
| `POST` | `/api/devices/{id}/reset` | Reset device data, optionally Wi-Fi |
| `GET` | `/api/devices/{id}/rules` | Raw on-device rules database |
| `GET` | `/api/devices/{id}/rules/summary` | Rules summary for one device |
| `GET` | `/api/devices/rules/summary` | Consolidated summary, refreshed from devices |
| `GET` | `/api/devices/rules/summary/cached` | Consolidated summary from cache |
| `GET` | `/api/devices/rules/calendar` | Weekly schedule events |
| `GET` | `/api/setup/config` | Wi-Fi settings, APK availability, server address |
| `PUT` | `/api/setup/config` | Store Wi-Fi settings |
| `GET` | `/api/setup/apk` | Download the Android app |
| `POST` | `/api/setup/logs` | Write a diagnostic log blob from the mobile app to the server log |

## Android app

A Capacitor application in `mobile/` connects a factory-reset device to Wi-Fi and
registers it. Build and stage it with `make apk`, then download it from the setup page.

In the app, enter the server's hostname or IP address; port 8000 is assumed. A hostname is
replaced with its IP address after the first successful connection, so setup continues to
work while the phone is joined to the device's access point. Wi-Fi credentials fetched
from the server are cached on the device.

See [mobile/README.md](mobile/README.md) for build details.

## Tests

```bash
make test
```

The suite substitutes a `pywemo` stub when the package is unavailable, so the logic is
testable without physical devices.

## Project layout

```text
app/
  main.py        Application entry point, lifespan, static mount
  database.py    Engine, session, schema creation
  models/        SQLAlchemy models
  schemas.py     Pydantic request and response models
  routers/       HTTP routes: devices, setup, UI pages
  services/      Discovery, device manager, repository, rules, settings, events
  templates/     Jinja2 templates
  static/        Stylesheet, scripts, staged APK
mobile/          Capacitor Android application
tests/           Test suite
deploy.sh        Build and deploy to a Docker host
```

## License

MIT. See [LICENSE](LICENSE).
