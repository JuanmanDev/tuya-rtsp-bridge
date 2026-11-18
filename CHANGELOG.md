# Changelog

## 1.3.1

- Readable login errors: Tuya error codes (e.g. `USER_PASSWD_WRONG`) mapped to English instead of the raw Chinese `errorMsg`, also for cloud PTZ login
- Status and error messages from the server are English everywhere (were a German/English mix next to the localized UI)
- `POST /api/login/password` returns 400 for empty email / password
- One shared post-login path (start RTSP, services, PTZ warmup) for QR, password and startup
- Dependabot: weekly pip + Go, monthly Actions + Docker base images

## 1.3.0 (fork: JuanmanDev/tuya-rtsp-bridge)

Fork of [DanEng1982/tuya-rtsp-bridge](https://github.com/DanEng1982/tuya-rtsp-bridge) — upstream [PR #4](https://github.com/DanEng1982/tuya-rtsp-bridge/pull/4) was not merged.

- Email / password login (`POST /api/login/password`) next to QR, with optional **auto-renew** on `USER_SESSION_LOSS` / `USER_SESSION_INVALID` (fixes streams dying after Tuya's 72 h session)
- Startup falls back to cached camera list if cloud discovery fails; `/proc` fallback when `pgrep` / `pkill` are missing; `procps` in images
- New login strings translated for all 18 UI languages
- `cryptography` added to requirements (password login needed it but it was missing)
- Docker: prebuilt multi-arch images on GHCR (`ghcr.io/juanmandev/tuya-rtsp-bridge`, amd64 + arm64), engine cross-compiled
- Docker: entrypoint chowns `/data` and `/config` then drops to uid 1000 (`PUID` / `PGID`) — fixes `PermissionError` with fresh bind mounts on Linux
- HA add-on: prebuilt images (`ghcr.io/juanmandev/tuya-rtsp-bridge-addon-{arch}`), Debian trixie base; armv7 dropped (no Pillow wheels; HA dropped 32-bit)
- Updated: Go 1.27 (module needs 1.26+), pion/webrtc 4.2.26, x/net 0.63, Python 3.14, requests 2.34, pillow 13, tinytuya 1.21, cryptography 50, python-vlc 3.0.21203
- CI: runs all tests + engine build; GitHub Actions bumped to current majors

## 1.2.6

- HA add-on: bust Docker git-clone cache (stale 1.2.4 image after “update”)
- Discover cameras via login `extras.homeId` when homeList is empty
- Do not print session JSON (`sid`) in the web log
- Windows preview still uses SD; a black tile with VLC 3 + HEVC is not a dead RTSP stream

## 1.2.5

- Fix empty camera list after login (#1): more Tuya categories (doorbells, `sp_*`, p2p), keep devices if jarvis/config fails, show `homes=`/`skipped=` in the UI
- HA add-on README: troubleshooting for Session-active / 0 cameras

## 1.2.4

- Fix Windows QR display: Canvas + fixed 320×320 NEAREST (no Tk Label slit) — #2
- Windows DPI awareness; API reconnects if backend was down (WinError 10061)
- Home Assistant OS add-on skeleton (`homeassistant/tuya_rtsp_bridge`) — #1
- Cloud PTZ fallback + protect password auto-relogin (local builds)
- Docs parity: 17 locales each have faq / getting-started / why / windows / api / docker / nvr

## 1.2.3

- Honest licenses: bundled ffmpeg is GPL-3 (Gyan essentials), VLC zip is GPL-2 / libVLC LGPL
- Short legal notes: [docs/legal.md](docs/legal.md), [docs/rechtliches.md](docs/rechtliches.md)
- Same app as 1.2.2

## 1.2.2

- App UI and docs in 18 languages (added Japanese, Korean, Hebrew, Yiddish)
- Windows Setup wizard: Japanese, Korean, Hebrew (Yiddish stays in the app menu)
- Project mark on the installer and desktop shortcut
- Docs no longer ask Windows users to install Python / VLC / ffmpeg

## 1.2.1

- Same bundled runtime as 1.2.0
- App icon on Setup.exe and shortcuts

## 1.2.0

- Foolproof Setup: private CPython, VLC, ffmpeg, RTSP engine
- No system Python, no extra installers

## 1.1.0

- Arch packaging, more languages, no Windows EXE on that tag

## 1.0.0

- First public release (small Setup, no bundled runtime)
