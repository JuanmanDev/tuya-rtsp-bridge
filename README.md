# Tuya RTSP Bridge

<p align="center">
  <img src="docs/images/logo.png" width="128" alt="Tuya RTSP Bridge">
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/JuanmanDev/tuya-rtsp-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/JuanmanDev/tuya-rtsp-bridge/actions/workflows/ci.yml)
[![Docker](https://github.com/JuanmanDev/tuya-rtsp-bridge/actions/workflows/docker.yml/badge.svg)](https://github.com/JuanmanDev/tuya-rtsp-bridge/pkgs/container/tuya-rtsp-bridge)
[![Fork of DanEng1982/tuya-rtsp-bridge](https://img.shields.io/badge/fork%20of-DanEng1982%2Ftuya--rtsp--bridge-blue)](https://github.com/DanEng1982/tuya-rtsp-bridge)
[![GitHub stars](https://img.shields.io/github/stars/JuanmanDev/tuya-rtsp-bridge?style=social)](https://github.com/JuanmanDev/tuya-rtsp-bridge/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/JuanmanDev/tuya-rtsp-bridge)](https://github.com/JuanmanDev/tuya-rtsp-bridge/issues)
[![English](README.md)](README.md) [![Deutsch](README.de.md)](README.de.md) [![Nederlands](README.nl.md)](README.nl.md) [![Français](README.fr.md)](README.fr.md) [![Español](README.es.md)](README.es.md) [![Português](README.pt.md)](README.pt.md) [![Italiano](README.it.md)](README.it.md) [![Polski](README.pl.md)](README.pl.md) [![Čeština](README.cs.md)](README.cs.md) [![Русский](README.ru.md)](README.ru.md) [![Українська](README.uk.md)](README.uk.md) [![Bahasa Indonesia](README.id.md)](README.id.md) [![简体中文](README.zh.md)](README.zh.md) [![हिन्दी](README.hi.md)](README.hi.md) [![日本語](README.ja.md)](README.ja.md) [![한국어](README.ko.md)](README.ko.md) [![עברית](README.he.md)](README.he.md) [![ייִדיש](README.yi.md)](README.yi.md)

> [!NOTE]
> **This is a maintained fork** of **[DanEng1982/tuya-rtsp-bridge](https://github.com/DanEng1982/tuya-rtsp-bridge)** by **[@DanEng1982](https://github.com/DanEng1982)**, who created this project — the original design, UI, docs and packaging are theirs.
> The fork exists because [PR #4](https://github.com/DanEng1982/tuya-rtsp-bridge/pull/4) (email/password login + session auto-renew, fixing the **72-hour stream dropout**) has not been merged upstream.
> If upstream becomes active again, these changes are offered back there first.

**Turn any Tuya / Smart Life / iSmartLife camera into a normal RTSP camera** — so Frigate, Agent DVR, go2rtc, Home Assistant, or VLC can use it.

No firmware flash. No ONVIF (stock Tuya does not offer it). Scan a QR code once, then copy an RTSP URL.

| You are… | Start here |
|---|---|
| Just want it to work | [5-minute setup](#5-minute-setup) |
| Home-lab / NVR tinkerer | [docs/nvr.md](docs/nvr.md) |
| Developer | [docs/architecture.md](docs/architecture.md) · [CONTRIBUTING.md](CONTRIBUTING.md) |

This repository ships **no** accounts, device IDs, or home IPs.

## Why cheap Tuya cameras need this

Those €20–40 “Smart Life” cams look like IP cameras. They are not. Stock firmware has **no ONVIF** and **no RTSP checkbox**. Live view is the vendor app and a cloud path you do not control. A second phone or a “cloud NVR” often means a subscription — or it steals the only live session.

You paid for a sensor on your wall. Recording should land on **your** disk.

This app is a small local bridge: scan a QR code in the app you already have, then every camera is a normal URL for Frigate, Agent DVR, go2rtc, Home Assistant, or VLC:

```
rtsp://<this-pc>:8554/<CameraName>/hd
```

Signaling still uses Tuya. When you watch from this PC, video typically stays on the LAN. Full story: [docs/why.md](docs/why.md) · [docs/warum.md](docs/warum.md).

## What’s new in this fork (1.3.0)

- **Email / password login** next to the QR flow (`POST /api/login/password`, Tuya RSA + MD5 password protocol)
- **Session auto-renew** — re-logs in automatically on `USER_SESSION_LOSS` / `USER_SESSION_INVALID`, so streams no longer die after Tuya’s **72-hour** web session limit
- **Prebuilt Docker images** on GHCR for `amd64` and `arm64`: `ghcr.io/juanmandev/tuya-rtsp-bridge` — no local build needed
- **Prebuilt Home Assistant add-on images** — installing / updating the add-on is a pull, not a long on-device Go build
- Docker: bind-mounted `./data` / `./config` are chowned on start (fixes `PermissionError` on fresh Linux hosts); `PUID` / `PGID` supported
- More robust startup: falls back to the cached camera list if cloud discovery fails; native `/proc` fallback when `pgrep` / `pkill` are missing
- Updated stack: Go 1.27, pion/webrtc 4.2, Python 3.14, Debian trixie, requests 2.34, pillow 13, cryptography 50, tinytuya 1.21
- UI strings for the new login form in all 18 languages

## What’s new in 1.2.4+ (upstream)

- QR login: fixed **320×320** canvas (Windows slit-QR bug fixed) — [issue #2](https://github.com/DanEng1982/tuya-rtsp-bridge/issues/2)
- **Home Assistant OS add-on:** [homeassistant/tuya_rtsp_bridge/](homeassistant/tuya_rtsp_bridge/) (host network) — [issue #1](https://github.com/DanEng1982/tuya-rtsp-bridge/issues/1)
- Docker / HA guide: [docs/docker.md](docs/docker.md)
- PTZ: LAN first (TCP 6668), optional **cloud PTZ** after one email/password — no IoT Platform keys
- Protect session auto-relogin when cookies expire

### The app

Email / password sign-in with **Auto-renew session**, running headless in Docker (web UI on `:8787`, PTZ arrows per camera):

![Tuya RTSP Bridge web UI in Docker: Email tab with email, password, country code and auto-renew session, cameras with RTSP HD URLs and PTZ controls.](docs/images/ui-email-login.png)

Fresh container, web UI before sign-in (QR tab; the Email tab is one click away):

![Tuya RTSP Bridge web UI first run in Docker: QR Code / Email tabs, Create QR button, empty camera list, switches and restart buttons.](docs/images/ui-web-first-run.png)

Desktop app (Windows / Linux GUI):

First run — language, region, QR, then confirm in Smart Life. No cameras yet:

![Tuya RTSP Bridge welcome screen. Empty list, no QR, localhost only.](docs/images/ui-welcome.png)

After login — demo names only (`Front yard`, `Driveway`). Preview panes stay black here on purpose (no live video in the docs):

![Tuya RTSP Bridge with two placeholder cameras and HD RTSP URLs on 127.0.0.1.](docs/images/ui-ready.png)

## Credits

**Original author:** [@DanEng1982](https://github.com/DanEng1982) — [DanEng1982/tuya-rtsp-bridge](https://github.com/DanEng1982/tuya-rtsp-bridge). This fork only adds the changes listed above; please star the original too.

The RTSP engine is **[tuya-ipc-terminal](https://github.com/seydx/tuya-ipc-terminal)** by **[seydx](https://github.com/seydx)** (MIT), vendored at commit `d65b3e9` with three documented local patches. See [CREDITS.md](CREDITS.md) and [NOTICE.md](NOTICE.md).

---

## What you get

```
Phone (Smart Life) ──QR──► this PC ──RTSP :8554──► Frigate / Agent DVR / VLC
                              │
                              ├── LAN PTZ (TCP 6668) when on the same network
                              └── Cloud PTZ fallback (optional email/password, no IoT keys)
```

- HD: `rtsp://<this-pc>:8554/<CameraName>/hd` (usually HEVC 1080p)
- SD: `rtsp://<this-pc>:8554/<CameraName>/sd` (H.264, smaller)
- All cameras share **one** bridge IP; only the path changes
- Live preview: bundled VLC on Windows Setup; Linux GUI uses an ffmpeg MJPEG pipe
- QR login draws a fixed **320×320** scannable square (Windows slit-QR bug fixed in 1.2.4+)
- English, Deutsch, Nederlands, Français, Español, Português, Italiano, Polski, Čeština, Русский, Українська, Bahasa Indonesia, 简体中文, हिन्दी, 日本語, 한국어, עברית, ייִדיש

Signaling still uses Tuya cloud. When you watch from this PC, video typically stays on your LAN.

## Honest limits

- Stock firmware has **no ONVIF** and **no camera-native RTSP**
- Many models output about **10 fps** in the HD bitstream — that is the camera, not this app
- VLC 3 sometimes shows a black window on HEVC/RTSP; Agent DVR / Frigate are the intended viewers
- Preview is optional; recording should happen in your NVR, not on the bridge
- Cloud PTZ needs your app email/password once if you are off the camera LAN

Supported login regions: Western Europe, Eastern Europe, USA West, USA East, China, India.

---

## 5-minute setup

### 0. You need

1. Windows 10/11 **or Arch Linux** (other Linux: use `./launch.sh` or Docker)
2. A Tuya Smart or Smart Life account that already sees the cameras

Windows users do **not** install Python, VLC, or ffmpeg. That is all inside the Setup.

### 1. Install

- **Docker (Linux / HA host):** prebuilt image — see [Docker quick start](#docker-quick-start) · [docs/docker.md](docs/docker.md)
- **Home Assistant OS add-on:** add `https://github.com/JuanmanDev/tuya-rtsp-bridge` as add-on repository — [homeassistant/tuya_rtsp_bridge/](homeassistant/tuya_rtsp_bridge/) (host network)
- **Windows:** `TuyaRtspBridge-Setup.exe` from the [upstream Releases](https://github.com/DanEng1982/tuya-rtsp-bridge/releases) (1.2.x, without this fork’s email login / auto-renew) — or run this fork [from source](#install-from-source) with `launch.bat`. Details: [docs/windows.md](docs/windows.md)
- **Arch Linux:** [docs/arch-linux.md](docs/arch-linux.md) — `./launch.sh` or `packaging/arch/PKGBUILD`
- **From source:** see [Install from source](#install-from-source)

Windows install dir: `%LOCALAPPDATA%\Programs\TuyaRtspBridge`.  
Logins: `%APPDATA%\TuyaRtspBridge\` (Windows) or `~/.local/share/tuya-rtsp-bridge/` (Linux). Never in git.

### Docker quick start

```bash
mkdir tuya-rtsp-bridge && cd tuya-rtsp-bridge
curl -fsSLO https://raw.githubusercontent.com/JuanmanDev/tuya-rtsp-bridge/main/docker-compose.yml
docker compose up -d
```

or without compose:

```bash
docker run -d --name tuya-rtsp-bridge --restart unless-stopped --network host   -v ./data:/data -v ./config:/config   ghcr.io/juanmandev/tuya-rtsp-bridge:latest
```

Then open `http://<this-host>:8787`. Tags: `latest` (main), `1.3.0` / `1.3` (releases), `sha-<commit>`. Platforms: `linux/amd64`, `linux/arm64`.

### 2. Log in

1. Start **Tuya RTSP Bridge**
2. Pick the same region as in the phone app (Germany “Western Europe” → **EU**)
3. Click **Create QR** (fixed 320×320 square — scannable on phones)
4. In Smart Life / Tuya Smart: scan, then **confirm**
5. Cameras appear with copy-paste HD URLs

**Or** use the **Email** tab: app email, password, country code (phone prefix, e.g. `34` Spain, `49` Germany, `1` USA) and tick **Auto-renew session** so the bridge signs itself in again when Tuya expires the session (~72 h). The password is stored only in your local data folder.

If the QR “does nothing”, wait — the app polls until you confirm. Wrong region = empty camera list; try the other EU/US cluster. If Windows shows a connection error once, wait a second and retry — the UI starts the local API automatically.

### 3. Watch

Paste into Agent DVR / Frigate / go2rtc:

```
rtsp://127.0.0.1:8554/<CameraName>/hd
```

From another machine on the LAN, replace `127.0.0.1` with this PC’s IP. Prefer **RTP over TCP**.

Ready-made snippets: [docs/nvr.md](docs/nvr.md).

---

## Install from source

```bat
git clone https://github.com/JuanmanDev/tuya-rtsp-bridge.git
cd tuya-rtsp-bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd vendor\tuya-ipc-terminal
go build -o ..\..\bin\tuya-ipc-terminal.exe .
cd ..\..
launch.bat
```

Linux / Arch:

```bash
sudo pacman -S --needed python python-pip tk go vlc ffmpeg   # Arch
chmod +x launch.sh
./launch.sh
```

Need Go **1.26+** only to build the engine. Release builds on Windows already include the `.exe`.

## Docs

| Doc | Audience |
|---|---|
| [docs/why.md](docs/why.md) / [warum.md](docs/warum.md) | Why this exists (plain language) |
| [docs/getting-started.md](docs/getting-started.md) | First run, Wi‑Fi move, PTZ |
| [docs/faq.md](docs/faq.md) | Black VLC, empty list, “only 10 fps” |
| [docs/nvr.md](docs/nvr.md) | Frigate, Agent DVR, go2rtc |
| [docs/architecture.md](docs/architecture.md) | How the pieces fit |
| [docs/api.md](docs/api.md) | Local HTTP API `:8787` |
| [docs/windows.md](docs/windows.md) | Foolproof Windows Setup.exe (Python + VLC + ffmpeg) |
| [docs/brand.md](docs/brand.md) | Logo, icon, social preview |
| [docs/legal.md](docs/legal.md) · [docs/rechtliches.md](docs/rechtliches.md) | Names, ToS, what we store, bundled licenses |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each Setup |
| [docs/docker.md](docs/docker.md) | Docker Compose + Home Assistant OS add-on |
| [docs/arch-linux.md](docs/arch-linux.md) | Arch: launch.sh + PKGBUILD |
| [homeassistant/tuya_rtsp_bridge/](homeassistant/tuya_rtsp_bridge/) | HA Supervisor add-on |
| [DEPENDENCIES.md](DEPENDENCIES.md) | Licenses (all redistributable or not shipped) |
| [docs/de](docs/de/) · [docs/nl](docs/nl/) · [docs/fr](docs/fr/) · [docs/es](docs/es/) · [docs/pt](docs/pt/) · [docs/it](docs/it/) · [docs/pl](docs/pl/) · [docs/cs](docs/cs/) · [docs/ru](docs/ru/) · [docs/uk](docs/uk/) · [docs/id](docs/id/) · [docs/zh](docs/zh/) · [docs/hi](docs/hi/) · [docs/ja](docs/ja/) · [docs/ko](docs/ko/) · [docs/he](docs/he/) · [docs/yi](docs/yi/) | Per locale: `faq` · `getting-started` · `why` · `windows` · `api` · `docker` · `nvr` |
| [SECURITY.md](SECURITY.md) | What not to commit |

## Join in

If this un-clouded a camera you already own, **star the repo** so the next person finds it.

Then pick one:

- [Report a camera model](https://github.com/JuanmanDev/tuya-rtsp-bridge/issues/new?template=camera.yml) (Smart Life / Tuya Smart + region)
- [Suggest a feature](https://github.com/JuanmanDev/tuya-rtsp-bridge/issues/new?template=feature.yml)
- Add a language or fix a string in `src/i18n.py` — see [CONTRIBUTING.md](CONTRIBUTING.md)

PRs from anywhere are welcome. English in code comments; UI already speaks eighteen languages.

## License

Our code: MIT ([LICENSE](LICENSE)).  
Vendored engine: MIT, Copyright (c) 2025 seydx — full text in [NOTICE.md](NOTICE.md) and `vendor/tuya-ipc-terminal/LICENSE`.

Tuya, Smart Life, and iSmartLife are trademarks of their owners. This project is not affiliated with Tuya Inc. or with seydx beyond using their MIT-licensed engine with credit.

Names, local data, bundled licenses: [docs/legal.md](docs/legal.md).
