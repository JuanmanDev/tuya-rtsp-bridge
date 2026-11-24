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
```

Detect fps can stay at 5 even if the source is ~10. Record uses the same HD URL.

See also `examples/frigate.yml`.

### Two-way audio (talk to the camera)

The bridge can play audio from the NVR through the camera's speaker. It only does this for go2rtc clients (identified by their `User-Agent: go2rtc/...`) and ONVIF-aware clients that send `Require: www.onvif.org/ver20/backchannel`. Plain RTSP players such as VLC or Agent DVR get the same receive-only stream as before. To turn talk-back off for one go2rtc stream, add `#backchannel=0` to its URL.

Only one talker at a time: a second backchannel client writes to the same camera speaker.

```yaml
go2rtc:
  streams:
    living_room:
      - rtsp://BRIDGE_IP:8554/CameraName/hd

cameras:
  living_room:
    live:
      stream_name: living_room   # the Talk button uses this go2rtc stream
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/living_room
          input_args: preset-rtsp-restream
          roles: [record, detect]
```

Requirements and checks:

- The camera must have a speaker and Tuya must expose two-way audio for it. Mic-only models will not talk back.
- The audio is G.711 (PCMU or PCMA, 8 kHz), the same format as the camera's own audio.
- When the camera accepts the track, the bridge log shows `Two-way audio (backchannel) ready`. If the line is missing, the camera does not support talk-back through this path.
- The Talk button only appears in Frigate when its go2rtc stream reports a backchannel. Check your Frigate version's docs for the exact `live:` / go2rtc keys.

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
