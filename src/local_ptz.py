"""PTZ: LAN 6668 first, then Cloud reverse Smart-Life API. Keine Secrets loggen."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import tinytuya

from cloud_mobile import CloudMobile

DIR = {
    "up": "0",
    "upright": "1",
    "right": "2",
    "downright": "3",
    "down": "4",
    "downleft": "5",
    "left": "6",
    "upleft": "7",
}
PTZ_DP = "119"
STOP_DP = "116"
LAN_CACHE = "lan.json"
VERS = (3.5, 3.4, 3.3)

# Interfaces that are almost never the camera LAN (VPN tunnels, docker, …)
_SKIP_IFACE_PREFIX = (
    "lo",
    "nordlynx",
    "wg",
    "tun",
    "tap",
    "docker",
    "br-",
    "veth",
    "virbr",
    "tailscale",
    "zt",
)


def _rank_iface(iface: str, ip: str) -> tuple[int, str]:
    if iface.startswith(("en", "eth", "wl", "wlan")):
        return (0, iface)
    if ip.startswith(("192.168.", "10.")) or ip.startswith("172."):
        return (1, iface)
    return (2, iface)


def _iface_ipv4_nets_ioctl() -> list[tuple[str, str, int]]:
    """Pure-Python Linux fallback via ioctl when `ip` command is unavailable."""
    out: list[tuple[str, str, int]] = []
    if os.name == "nt":
        return out
    try:
        import array
        import fcntl
        import struct

        max_possible = 64
        buf_size = max_possible * 40
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            names = array.array("B", b"\0" * buf_size)
            outbytes = struct.unpack(
                "iL",
                fcntl.ioctl(
                    sock.fileno(),
                    0x8912,  # SIOCGIFCONF
                    struct.pack("iL", buf_size, names.buffer_info()[0]),
                ),
            )[0]
            namestr = names.tobytes()
            step = 40 if struct.calcsize("P") == 8 else 32
            for i in range(0, outbytes, step):
                iface = namestr[i : i + 16].split(b"\0", 1)[0].decode("utf-8", "ignore")
                if not iface or any(iface.startswith(p) for p in _SKIP_IFACE_PREFIX):
                    continue
                ip = socket.inet_ntoa(namestr[i + 20 : i + 24])
                if ip.startswith("127."):
                    continue
                prefixlen = 24
                try:
                    ifreq = struct.pack("256s", iface.encode("utf-8")[:15])
                    mask_raw = fcntl.ioctl(sock.fileno(), 0x891B, ifreq)[20:24]  # SIOCGIFNETMASK
                    mask = socket.inet_ntoa(mask_raw)
                    prefixlen = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
                except Exception:
                    pass
                out.append((iface, ip, prefixlen))
        finally:
            sock.close()
    except Exception:
        return []
    return out


def _iface_ipv4_nets() -> list[tuple[str, str, int]]:
    """Return [(iface, ip, prefixlen)] for usable LAN addresses — never prefer VPN."""
    out: list[tuple[str, str, int]] = []
    text = ""
    try:
        text = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            text=True,
            timeout=3,
        )
    except Exception:
        text = ""
    for line in text.splitlines():
        # 2: enp…    inet 192.168.2.159/22 …
        parts = line.split()
        if len(parts) < 4 or "inet" not in parts:
            continue
        iface = parts[1]
        if any(iface.startswith(p) for p in _SKIP_IFACE_PREFIX):
            continue
        try:
            cidr = parts[parts.index("inet") + 1]
            if "/" in cidr:
                ip, plen_s = cidr.split("/", 1)
                plen = int(plen_s)
            else:
                ip, plen = cidr, 24
        except Exception:
            continue
        if ip.startswith("127."):
            continue
        out.append((iface, ip, plen))

    if not out:
        out = _iface_ipv4_nets_ioctl()

    out.sort(key=lambda item: _rank_iface(item[0], item[1]))
    return out


def _iface_ipv4s() -> list[tuple[str, str]]:
    """Return [(iface, ip)] for usable LAN addresses — never prefer VPN over Ethernet."""
    return [(iface, ip) for iface, ip, _ in _iface_ipv4_nets()]


def _local_ipv4() -> str:
    """Best-effort LAN IP for the camera subnet (not VPN)."""
    ifaces = _iface_ipv4s()
    if ifaces:
        return ifaces[0][1]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _expand_subnet_to_prefixes(spec: str) -> list[str]:
    """Expand a CIDR (e.g. 192.168.0.0/22), IP, or '192.168.0.' prefix into /24 prefixes."""
    s = (spec or "").strip()
    if not s:
        return []
    if s.endswith(".") and s.count(".") == 3:
        return [s]
    try:
        if "/" in s:
            net = ipaddress.IPv4Network(s, strict=False)
            # Avoid scanning huge /8 or /16 networks; clamp to host's /24 if wider than /20.
            if net.prefixlen < 20:
                host_ip = s.split("/", 1)[0]
                parts = host_ip.split(".")
                if len(parts) == 4 and not host_ip.startswith("127."):
                    return [".".join(parts[:3]) + "."]
                return []
            if net.prefixlen <= 24:
                return [".".join(str(sub.network_address).split(".")[:3]) + "." for sub in net.subnets(new_prefix=24)]
            return [".".join(str(net.network_address).split(".")[:3]) + "."]
        ipaddress.IPv4Address(s)
        return [".".join(s.split(".")[:3]) + "."]
    except Exception:
        return []


def _env_prefixes() -> list[str]:
    raw = os.environ.get("TUYA_LAN_SUBNETS", "").strip()
    if not raw:
        return []
    prefs: list[str] = []
    for item in raw.split(","):
        for p in _expand_subnet_to_prefixes(item):
            if p not in prefs:
                prefs.append(p)
    return prefs


def _env_camera_ips() -> dict[str, dict]:
    raw = os.environ.get("TUYA_CAMERA_IPS", "").strip()
    if not raw:
        return {}
    out: dict[str, dict] = {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for did, val in parsed.items():
                    if isinstance(val, str) and val.strip():
                        out[str(did)] = {"ip": val.strip()}
                    elif isinstance(val, dict) and val.get("ip"):
                        rec = {"ip": str(val["ip"]).strip()}
                        if val.get("version"):
                            rec["version"] = float(val["version"])
                        out[str(did)] = rec
                return out
        except Exception:
            return {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        did, ip = pair.split("=", 1)
        did, ip = did.strip(), ip.strip()
        if did and ip:
            out[did] = {"ip": ip}
    return out


def _prefixes() -> list[str]:
    """All /24 prefixes we should scan for port 6668 (handles /22 etc. + TUYA_LAN_SUBNETS)."""
    prefs = _env_prefixes()
    for _, ip, plen in _iface_ipv4_nets():
        for p in _expand_subnet_to_prefixes(f"{ip}/{plen}"):
            if p not in prefs:
                prefs.append(p)
    if not prefs:
        ip = _local_ipv4()
        for p in _expand_subnet_to_prefixes(f"{ip}/24"):
            if p not in prefs:
                prefs.append(p)
    return prefs


def _udp_scan_ips() -> list[str]:
    """Fast Tuya UDP broadcast discovery (6666/6667); works on host LAN."""
    try:
        devices = tinytuya.deviceScan(verbose=False, maxretry=1)
        if isinstance(devices, dict):
            ips = []
            for info in devices.values():
                ip = (info or {}).get("ip") if isinstance(info, dict) else None
                if ip and ip not in ips:
                    ips.append(ip)
            return ips
    except Exception:
        pass
    return []


def _scan_6668(prefix: str | None = None) -> list[str]:
    prefixes = [prefix] if prefix else _prefixes()
    found: list[str] = []
    if not prefix:
        for ip in _udp_scan_ips():
            if ip not in found:
                found.append(ip)

    def chk(ip: str) -> Optional[str]:
        s = socket.socket()
        s.settimeout(0.35)
        try:
            if s.connect_ex((ip, 6668)) == 0:
                return ip
        except Exception:
            return None
        finally:
            s.close()
        return None

    for pref in prefixes:
        with ThreadPoolExecutor(max_workers=96) as ex:
            ips = [f"{pref}{i}" for i in range(1, 255)]
            for ip in ex.map(chk, ips):
                if ip and ip not in found:
                    found.append(ip)
    return found


class LocalPtz:
    def __init__(self, data_dir: Path, tuya_client) -> None:
        self.data_dir = data_dir
        self.client = tuya_client
        region = getattr(tuya_client, "region_id", None) or "eu"
        self.cloud = CloudMobile(data_dir, region_id=str(region))
        self._lock = threading.Lock()
        self._map: dict[str, dict] = {}
        self._load_cache()
        self._seed_env_ips()
        self._seed_cloud_email()

    def _seed_env_ips(self) -> None:
        for did, rec in _env_camera_ips().items():
            cur = self._map.get(did) or {}
            if not cur.get("ip"):
                self._map[did] = {
                    "ip": rec["ip"],
                    "version": rec.get("version") or 3.4,
                }

    def _seed_cloud_email(self) -> None:
        try:
            login = getattr(self.client, "login", None) or {}
            if isinstance(login, dict) and login:
                self.cloud.seed_from_session(login)
                return
            for p in self.data_dir.glob("user_*.json"):
                data = json.loads(p.read_text(encoding="utf-8"))
                lr = (data.get("sessionData") or {}).get("loginResult") or {}
                if lr:
                    self.cloud.seed_from_session(lr)
                    break
        except Exception:
            pass

    def _load_cache(self) -> None:
        p = self.data_dir / LAN_CACHE
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._map = {
                    k: v for k, v in data.items() if isinstance(v, dict) and v.get("ip")
                }
        except Exception:
            self._map = {}

    def _save_cache(self) -> None:
        out = {
            did: {"ip": v["ip"], "version": v.get("version", 3.4)}
            for did, v in self._map.items()
            if v.get("ip")
        }
        (self.data_dir / LAN_CACHE).write_text(json.dumps(out, indent=2), encoding="utf-8")

    def lan_cache(self) -> dict[str, dict]:
        """Safe public view of cached/configured LAN IPs (never includes localKey)."""
        with self._lock:
            return {
                did: {"ip": v["ip"], "version": v.get("version")}
                for did, v in self._map.items()
                if v.get("ip")
            }

    def set_camera_ip(
        self, device_id: str, ip: str, version: float | None = None
    ) -> dict:
        ip = (ip or "").strip()
        if not ip:
            with self._lock:
                self._map.pop(device_id, None)
                self._save_cache()
            return {"deviceId": device_id, "ip": None}
        ipaddress.IPv4Address(ip)
        key = self._local_key(device_id)
        vers = (float(version),) if version else VERS
        for ver in vers:
            if self._probe(device_id, ip, key, float(ver)):
                rec = {"ip": ip, "version": float(ver), "key": key}
                with self._lock:
                    self._map[device_id] = rec
                    self._save_cache()
                return {"deviceId": device_id, "ip": ip, "version": float(ver), "probed": True}
        raise RuntimeError(f"Camera {device_id} did not respond at {ip}:6668")

    def _local_key(self, device_id: str) -> str:
        body = self.client._post(
            "/api/jarvis/config",
            payload={"devId": device_id, "clientTraceId": "ptz"},
            referer="/playback",
        )
        key = (body.get("result") or {}).get("localKey") or ""
        if not key:
            raise RuntimeError("kein localKey")
        return key

    def _probe(self, device_id: str, ip: str, key: str, ver: float) -> bool:
        d = tinytuya.Device(device_id, ip, key, version=ver)
        d.set_socketTimeout(1.2)
        try:
            st = d.status()
        except Exception:
            return False
        if not isinstance(st, dict):
            return False
        if st.get("Error") or st.get("Err"):
            return False
        return "dps" in st or "DPS" in st

    def _claimed_ips(self, exclude_device_id: str) -> set[str]:
        with self._lock:
            return {
                v["ip"]
                for did, v in self._map.items()
                if did != exclude_device_id and v.get("ip")
            }

    def ensure(self, device_id: str, candidate_ips: list[str] | None = None) -> dict:
        with self._lock:
            hit = self._map.get(device_id)
            if hit and hit.get("ip") and hit.get("key") and hit.get("version"):
                return hit
            cached_ip = (hit or {}).get("ip")
            cached_ver = (hit or {}).get("version")
        key = self._local_key(device_id)
        if cached_ip:
            vers = (cached_ver,) if cached_ver else VERS
            for ver in vers:
                if self._probe(device_id, cached_ip, key, float(ver)):
                    rec = {"ip": cached_ip, "version": float(ver), "key": key}
                    with self._lock:
                        self._map[device_id] = rec
                        self._save_cache()
                    return rec
        claimed = self._claimed_ips(device_id)
        with self._lock:
            ips: list[str] = []
            hit = self._map.get(device_id) or {}
            if hit.get("ip"):
                ips.append(hit["ip"])
            ips.extend(
                v.get("ip")
                for v in self._map.values()
                if v.get("ip") and v.get("ip") not in ips and v.get("ip") not in claimed
            )
        prefs = _prefixes()
        scanned: list[str] = []
        if candidate_ips is not None:
            scanned = list(candidate_ips)
        elif ips or prefs:
            try:
                scanned = _scan_6668() if prefs else []
            except Exception:
                scanned = []
        for ip in scanned:
            if ip not in ips and ip not in claimed:
                ips.append(ip)
        last = ""
        for ip in ips:
            for ver in VERS:
                if self._probe(device_id, ip, key, ver):
                    rec = {"ip": ip, "version": ver, "key": key}
                    with self._lock:
                        self._map[device_id] = rec
                        self._save_cache()
                    return rec
                last = f"{ip} v{ver}"
        raise RuntimeError(
            f"Camera {device_id} not found on LAN "
            f"(prefixes={prefs or ['?']}, scanned={len(scanned)}, last={last or 'none'})"
        )

    def warmup(self, device_ids: list[str]) -> None:
        def run() -> None:
            if not device_ids:
                return
            # Scan LAN once for any uncached cameras instead of per-camera full scans.
            with self._lock:
                need_scan = any(did not in self._map for did in device_ids)
            scanned = _scan_6668() if (need_scan and _prefixes()) else []
            for did in device_ids:
                try:
                    self.ensure(did, candidate_ips=scanned)
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True, name="ptz-warmup").start()

    def _device(self, device_id: str):
        rec = self.ensure(device_id)
        d = tinytuya.Device(device_id, rec["ip"], rec["key"], version=rec["version"])
        d.set_socketTimeout(5)
        return d

    def move(self, device_id: str, direction: str) -> dict:
        direction = (direction or "").lower().strip()
        if direction == "stop":
            return self.stop(device_id)
        if direction not in DIR:
            raise ValueError(f"unbekannte Richtung {direction}")
        prefer_cloud = self.cloud.has_auth() and device_id not in self._map
        lan_err: Optional[str] = None
        if not prefer_cloud:
            try:
                d = self._device(device_id)
                res = d.set_value(PTZ_DP, DIR[direction])
                return {
                    "via": "lan",
                    "dp": PTZ_DP,
                    "value": DIR[direction],
                    "result": res,
                    "ip": self._map.get(device_id, {}).get("ip"),
                }
            except Exception as exc:
                lan_err = str(exc)
        try:
            out = self.cloud.move(device_id, direction)
            if lan_err:
                out["lan_error"] = lan_err
            return out
        except Exception as cloud_exc:
            if prefer_cloud and lan_err is None:
                try:
                    d = self._device(device_id)
                    res = d.set_value(PTZ_DP, DIR[direction])
                    return {
                        "via": "lan",
                        "dp": PTZ_DP,
                        "value": DIR[direction],
                        "result": res,
                        "ip": self._map.get(device_id, {}).get("ip"),
                        "cloud_error": str(cloud_exc),
                    }
                except Exception as exc:
                    lan_err = str(exc)
            raise RuntimeError(
                f"PTZ fail lan=({lan_err or 'n/a'}) cloud=({cloud_exc})"
            ) from cloud_exc

    def stop(self, device_id: str) -> dict:
        lan_err: Optional[str] = None
        try:
            rec = self.ensure(device_id)
            d = tinytuya.Device(device_id, rec["ip"], rec["key"], version=rec["version"])
            d.set_socketTimeout(2.0)
            res = d.set_value(STOP_DP, True)
            return {
                "via": "lan",
                "dp": STOP_DP,
                "value": True,
                "result": res,
                "ip": rec.get("ip"),
            }
        except Exception as exc:
            lan_err = str(exc)
        try:
            out = self.cloud.stop(device_id)
            out["lan_error"] = lan_err
            return out
        except Exception as cloud_exc:
            raise RuntimeError(
                f"PTZ stop fail lan=({lan_err or 'n/a'}) cloud=({cloud_exc})"
            ) from cloud_exc
