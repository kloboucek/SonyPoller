# SonyPoller

Dockerized Sony/Android TV playback-state poller for Home Assistant.

It connects to a Sony Android TV over ADB, reads the current Android media-session playback state, and updates a Home Assistant sensor such as `sensor.sony_tv_playback_state`.

## What is improved vs the old host script

- Dockerized app with `adb` included.
- Secrets and settings via `.env` instead of hardcoded Python.
- Persistent ADB key volume at `./adb`.
- Home Assistant updates only when state changes by default.
- Reconnect attempts after failures.
- Configurable poll interval and ADB timeout.
- `/healthz` liveness endpoint and Docker healthcheck.
- `/readyz` readiness endpoint for successful TV/HA polling.
- Unit tests and GitHub Actions CI.

## Install procedure

### 1. Prerequisites

Install on any always-on Docker host that can reach both Home Assistant and the TV over the LAN.

Required:

- Docker Engine
- Docker Compose v2
- A Sony/Android TV with ADB/network debugging enabled
- A Home Assistant long-lived access token

### 2. Clone and configure

```bash
git clone https://github.com/kloboucek/SonyPoller.git
cd SonyPoller
cp .env.example .env
nano .env
mkdir -p adb/.android
```

Set at least these values in `.env`:

```env
TV_ADB_HOST=TV_IP_ADDRESS:5555
HA_URL=http://HOME_ASSISTANT_HOST:8123
HA_TOKEN=your_home_assistant_long_lived_access_token
HA_ENTITY_ID=sensor.sony_tv_playback_state
```

### 3. Start SonyPoller

```bash
docker compose up -d --build
```

Check it:

```bash
docker compose ps
docker logs -f sonypoller
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/readyz
```

`/healthz` shows whether the container process is alive. `/readyz` shows whether polling has recently succeeded.

## Home Assistant setup

### 1. Create a long-lived access token

In Home Assistant:

1. Open your user profile.
2. Scroll to **Long-lived access tokens**.
3. Click **Create Token**.
4. Name it something like `SonyPoller`.
5. Copy the token immediately.
6. Paste it into `.env` as `HA_TOKEN`.

Example:

```env
HA_URL=http://HOME_ASSISTANT_HOST:8123
HA_TOKEN=your_home_assistant_long_lived_access_token
HA_ENTITY_ID=sensor.sony_tv_playback_state
```

Do not commit `.env`; it is ignored by git.

### 2. Sensor behavior

SonyPoller writes directly to Home Assistant's state API:

```text
POST /api/states/sensor.sony_tv_playback_state
```

Home Assistant will create the entity automatically after the first successful update.

States are:

- `playing`
- `paused`
- `unknown`

You can then use `sensor.sony_tv_playback_state` in dashboards, automations, templates, and history.

## Sony/Android TV setup

### 1. Enable Developer Options

On the TV:

1. Open **Settings**.
2. Go to **System** / **Device Preferences** / **About**. The exact menu varies by Android TV version.
3. Select **Build** repeatedly until Developer Options are enabled.

### 2. Enable ADB/network debugging

In **Developer Options**:

1. Enable **USB debugging** or **ADB debugging**.
2. Enable **Network debugging** / **Wireless debugging** if available.
3. Confirm the TV is reachable on TCP port `5555`.

Recommended: give the TV a DHCP reservation/static IP, then use that address in `TV_ADB_HOST`, for example `TV_IP_ADDRESS:5555`.

### 3. Authorize the container's ADB key

The TV must trust the ADB key used by the container.

#### Option A: copy existing trusted keys

If the old poller already has a trusted key:

```bash
mkdir -p adb/.android
cp ~/.android/adbkey* adb/.android/
chmod 600 adb/.android/adbkey
```

Then start/restart the container:

```bash
docker compose up -d --build
```

#### Option B: authorize fresh

Start the container, then request authorization:

```bash
docker compose up -d --build
docker exec -it sonypoller adb connect TV_IP_ADDRESS:5555
```

Accept the ADB authorization prompt on the TV.

Test ADB from inside the container:

```bash
docker exec -it sonypoller adb devices
docker exec -it sonypoller adb -s TV_IP_ADDRESS:5555 shell dumpsys media_session
```

## Configuration

`.env` values:

- `TV_ADB_HOST`: Android TV ADB endpoint, e.g. `TV_IP_ADDRESS:5555`.
- `HA_URL`: Home Assistant URL, e.g. `http://HOME_ASSISTANT_HOST:8123`.
- `HA_TOKEN`: Home Assistant long-lived access token. Never commit this.
- `HA_ENTITY_ID`: Sensor to create/update. Default: `sensor.sony_tv_playback_state`.
- `POLL_INTERVAL`: Seconds between polls. Default: `1`.
- `ADB_TIMEOUT`: ADB command timeout in seconds. Default: `5`.
- `UPDATE_ON_CHANGE_ONLY`: Post to HA only when the state changes. Default: `true`.
- `UNKNOWN_AFTER_FAILURES`: Number of failed polls before publishing `unknown`. Default: `3`.
- `HEALTH_PORT`: Container health endpoint port. Default: `8080`.

## Local development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
```

Run manually:

```bash
export TV_ADB_HOST=TV_IP_ADDRESS:5555
export HA_URL=http://HOME_ASSISTANT_HOST:8123
export HA_TOKEN=your_token
python app.py
```

## Notes

- Keep `.env` and `adb/.android/adbkey*` private.
- If the TV changes IP, update `TV_ADB_HOST`.
- If healthcheck is unhealthy right after first boot, check whether the TV has accepted the ADB prompt. Classic Android TV ceremony: press OK, appease the prompt, profit.
