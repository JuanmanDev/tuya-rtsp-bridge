# Tuya RTSP Bridge (Home Assistant add-on)

Turns Smart Life / Tuya cameras into RTSP for Frigate, go2rtc, Agent DVR.

## Install

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add: `https://github.com/JuanmanDev/tuya-rtsp-bridge`
3. **Check for updates**
4. Install **Tuya RTSP Bridge** → **Start**
5. Open `http://HOME-IP:8787` → **Create QR** → scan and confirm in Smart Life
   — or the **Email** tab (email, password, country code) with **Auto-renew session** ticked, so streams survive Tuya's ~72 h session expiry

RTSP URL:

```
rtsp://HOME-IP:8554/Camera_Name/hd
```

## Update (empty camera list)

**Restart is not enough.** On the add-on page:

1. **Stop**
2. **Update** (or Uninstall + Install)
3. Version must be **1.3.0** or newer
4. **Start** → Sign out → Create QR → confirm → **Refresh cameras**

Do not paste login JSON into GitHub issues.

## Notes

- Needs `host_network` (already on) for camera video on the LAN
- Do not also run the official Tuya cloud integration on the same cameras
