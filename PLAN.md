# SonyPoller implementation plan

## Goal
Create a ready-to-use Dockerized Sony/Android TV poller that updates Home Assistant with playback state.

## Scope

1. Replace hardcoded host script settings with environment variables.
2. Package the poller as a Docker image with `adb` included.
3. Persist ADB authorization keys via a mounted `./adb` volume.
4. Update Home Assistant only when state changes by default.
5. Add retry/reconnect behavior and configurable unknown-state handling.
6. Add liveness/readiness endpoints and Docker healthcheck.
7. Provide a compose file, `.env.example`, README, unit tests, and GitHub Actions CI.

## Out of scope for this first version

- Live TV/HA integration testing while away from home.
- Publishing a public Docker Hub/GHCR image.
- UI dashboard. Tiny daemon first; bells and whistles later.

## Verification performed locally

- Python unit tests with `python3 -m unittest discover -s tests`.
- Docker image build with `docker build -t sonypoller:local .`.
- Container ADB availability with `docker run --rm sonypoller:local adb version`.
