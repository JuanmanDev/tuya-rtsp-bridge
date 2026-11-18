# Tuya RTSP Bridge — Home Assistant add-on

Turn Tuya / Smart Life cameras into plain RTSP for Frigate, go2rtc, Agent DVR.

## Install (Add-on store)

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add `https://github.com/JuanmanDev/tuya-rtsp-bridge`
3. **⋮ → Check for updates**
4. Install **Tuya RTSP Bridge** → **Start**
5. Open `http://<ha-host>:8787` → **Create QR** → scan & confirm in Smart Life
   — or **Email** tab + **Auto-renew session** (survives Tuya's ~72 h session expiry)
6. Frigate / go2rtc:
   ```
   rtsp://<ha-host>:8554/<CameraName>/hd
   ```

## Requirements

- **host_network: true** (already set) — cameras need LAN WebRTC/UDP and PTZ TCP 6668
- Do **not** also enable the official Tuya cloud integration for the same cams (it steals the live session)

## Empty camera list after sign-in

**Restart is not enough.** Update the add-on (or Uninstall + Install). Version must be **1.3.0+**. Then Sign out → Create QR → confirm → **Refresh cameras**.

Do not paste login JSON into GitHub.

## Local copy (optional)

If you prefer a local add-on instead of the store:

```
/addons/tuya_rtsp_bridge
```

Clone the repo and symlink `homeassistant/tuya_rtsp_bridge` there, then **Check for updates**.
