# NVR / Home Assistant

Replace `BRIDGE_IP` with the PC that runs this app (`127.0.0.1` if the NVR is on the same machine). Replace `CameraName` with the name shown in the UI (spaces become `_`).

Always use the **`/hd`** path unless you have a reason for `/sd`.

## Agent DVR

Add camera → RTSP:

```
rtsp://BRIDGE_IP:8554/CameraName/hd
```

Transport: TCP. Do not enable a second Tuya integration on the same cameras (it steals the WebRTC session).

## Frigate

```yaml
mqtt:
  enabled: false

cameras:
  front_yard:
    ffmpeg:
      inputs:
        - path: rtsp://BRIDGE_IP:8554/CameraName/hd
          input_args: preset-rtsp-restream
          roles: [record, detect]
    detect:
      width: 1920
      height: 1080
      fps: 5
    onvif:
      host: BRIDGE_IP   # or container name e.g. tuya-rtsp
      port: 8787
      user: ""
      password: ""
      profile: CameraName
```

Detect fps can stay at 5 even if the source is ~10. Record uses the same HD URL.

### PTZ movement in Frigate (ONVIF bridge)

Stock Tuya cameras do not ship ONVIF, so this bridge exposes a virtual ONVIF Device / Media / PTZ SOAP endpoint on `:8787` (`/onvif/device_service`). Every discovered camera appears as an ONVIF profile whose token/name equals its `frigateId` (e.g. `Security_Camera`).

- Set `onvif.host` to the bridge host/container, `onvif.port` to `8787` (or set `TUYA_ONVIF_PORT` if you prefer another port), and `onvif.profile` to the camera's `frigateId`.
- If the bridge runs in Docker bridge mode or across a wider subnet (e.g. `/22`), set `TUYA_LAN_SUBNETS=192.168.0.0/22` or pin the camera's LAN IP in the web UI (**Set PTZ IP**) or via `TUYA_CAMERA_IPS`.

See also `examples/frigate.yml`.

### Two-way audio (talk to the camera)

Verified with Frigate (bundled go2rtc 1.9.14) and bridge 1.3.2: the **Talk** button in Frigate's live view plays through the camera's speaker.

The bridge offers a sendonly G.711 track to go2rtc clients (`User-Agent: go2rtc/...`) and to ONVIF-aware clients (`Require: www.onvif.org/ver20/backchannel`). Plain players such as VLC or Agent DVR never see it. go2rtc enables talk-back by default, so **do not add `#backchannel=0`**.

Setup (go2rtc inside Frigate; use the bridge's container name or IP):

```yaml
go2rtc:
  streams:
    CamaraEntrada:
      - rtsp://tuya-rtsp:8554/Security_Camera/sd#tcp#timeout=30s
```

- The Frigate camera name must match the go2rtc stream name (`CamaraEntrada` here). Frigate then uses that stream for live view and Talk.
- Keep your existing Frigate detect/record inputs; only the live stream needs the entry above.
- Open Frigate over **HTTPS** (for example a reverse proxy). Browsers only allow microphone access on secure pages.

Checks:

1. Bridge log shows `Two-way audio (backchannel) ready: audio/PCMU` when the camera stream starts.
2. go2rtc shows the camera producer with `audio, sendonly, PCMU/8000`.
3. Frigate live view → **Talk** → speak. Sound comes out of the camera speaker.

Troubleshooting:

- No `ready` line: the camera has no speaker or Tuya does not offer two-way audio for it, or the bridge is older than 1.3.2.
- No sendonly track in go2rtc: `#backchannel=0` is still in the URL, or the bridge is older than 1.3.2.
- No Talk button: the page is not HTTPS, or the Frigate camera name differs from the go2rtc stream name.

Limits: G.711 only (PCMU/PCMA, 8 kHz); one talker at a time; mic-only cameras cannot talk back.

Home Assistant's own talk button needs Home Assistant 2026.11+ and an integration that declares two-way audio. A generic RTSP camera does not, so use Frigate for talk-back.

## go2rtc

```yaml
streams:
  cam1: rtsp://BRIDGE_IP:8554/CameraName/hd
```

Do **not** mix `tuya://` (password login) with this QR bridge on the same device.

## Home Assistant

Generic camera or go2rtc add-on with the same RTSP URL. Still no ONVIF.

On the HA host (Linux), the bridge can run next to Frigate:

```bash
git clone https://github.com/JuanmanDev/tuya-rtsp-bridge.git
cd tuya-rtsp-bridge
docker compose up -d --build
```

Then open `http://<ha-host>:8787`, scan the QR, and point Frigate at `rtsp://127.0.0.1:8554/<CameraName>/hd`. Details: [docs/docker.md](docker.md).

## VLC (debug only)

```
vlc --rtsp-tcp rtsp://127.0.0.1:8554/CameraName/hd
```

If the window is black, try ffplay or Agent — not another Tuya app.
