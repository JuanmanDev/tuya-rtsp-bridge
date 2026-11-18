# Docker

Headless: web UI `:8787` + RTSP `:8554`. No desktop GUI, no VLC inside the image.

Session files stay in `./data` and `./config` next to the compose file — never in the image.

## Linux / Home Assistant host (recommended)

Host networking lets the engine talk to cameras on the LAN (WebRTC/UDP + PTZ on TCP 6668).

Prebuilt multi-arch image (`linux/amd64`, `linux/arm64`): **`ghcr.io/juanmandev/tuya-rtsp-bridge`**

```bash
mkdir tuya-rtsp-bridge && cd tuya-rtsp-bridge
curl -fsSLO https://raw.githubusercontent.com/JuanmanDev/tuya-rtsp-bridge/main/docker-compose.yml
docker compose up -d
```

Or build from a checkout:

```bash
git clone https://github.com/JuanmanDev/tuya-rtsp-bridge.git
cd tuya-rtsp-bridge
docker compose up -d --build
```

| Tag | Meaning |
|---|---|
| `latest` | current `main` |
| `1.3.0`, `1.3` | release tags `v1.3.0` … |
| `sha-<commit>` | exact commit |

The container starts as root only to `chown` `/data` and `/config`, then drops to uid/gid **1000**. Override with `PUID` / `PGID` environment variables if your host user differs.

Open `http://<this-host>:8787` → same region as the phone app → **Create QR** → scan and **confirm** in Smart Life / Tuya Smart.

Or the **Email** tab: email + password + country code, with **Auto-renew session** ticked so the bridge logs in again by itself when Tuya ends the web session (~72 h).

Then in Frigate / go2rtc / Agent DVR:

```
rtsp://<this-host>:8554/<CameraName>/hd
```

## Home Assistant OS add-on

Supervisor add-on: [`homeassistant/tuya_rtsp_bridge/`](../homeassistant/tuya_rtsp_bridge/).

1. Add `https://github.com/JuanmanDev/tuya-rtsp-bridge` as a custom add-on repository (prebuilt images for `amd64` / `aarch64` are pulled from GHCR — no on-device build)
2. **Settings → Add-ons → Add-on store → ⋮ → Repositories** if needed
3. Install **Tuya RTSP Bridge** → Start
4. Open `http://<ha-host>:8787` for QR login

Details: [homeassistant/tuya_rtsp_bridge/README.md](../homeassistant/tuya_rtsp_bridge/README.md).

`host_network: true` is required. Do **not** also run the official Tuya cloud integration for the same cameras.

## Windows / macOS Docker Desktop

`network_mode: host` does not work there:

```bash
docker compose -f docker-compose.ports.yml up -d --build
```

If PTZ or live video is flaky, run the native Windows app instead of the container.

## Frigate on the same machine

Use `127.0.0.1` as the bridge IP (see [nvr.md](nvr.md) and `examples/frigate.yml`). Do **not** also add the official Tuya / `tuya://` integration for the same cameras — it steals the live session.

## Updates

```bash
docker compose pull && docker compose up -d      # prebuilt image
# or, from a checkout:
git pull && docker compose up -d --build
```

Login session survives in `./data`.

## What is not in the image

- Desktop GUI / python-vlc
- Your Tuya account, device IDs, or LAN IPs
