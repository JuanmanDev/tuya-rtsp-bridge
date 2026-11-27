"""Minimal ONVIF Device / Media / PTZ SOAP server for Frigate & ONVIF clients.

Exposes every discovered camera from TuyaClient as an ONVIF Media Profile so
Frigate can control Tuya PTZ cameras via standard `onvif:` configuration:

  cameras:
    CamaraEntrada:
      onvif:
        host: tuya-rtsp
        port: 8787
        profile: Security_Camera
"""
from __future__ import annotations

import json
import os
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from xml.sax.saxutils import escape

from tuya_client import slug

_NS_SOAP12 = "http://www.w3.org/2003/05/soap-envelope"
_NS_SOAP11 = "http://schemas.xmlsoap.org/soap/envelope/"
_NS_TDS = "http://www.onvif.org/ver10/device/wsdl"
_NS_TRT = "http://www.onvif.org/ver10/media/wsdl"
_NS_TPTZ = "http://www.onvif.org/ver20/ptz/wsdl"
_NS_TT = "http://www.onvif.org/ver10/schema"

_VEL_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"
_POS_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace"

_AUTO_STOP_DEFAULT_S = 10.0


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_child(elem: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if elem is None:
        return None
    for child in elem:
        if _localname(child.tag) == name:
            return child
    return None


def _find_descendant(elem: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if elem is None:
        return None
    for node in elem.iter():
        if _localname(node.tag) == name:
            return node
    return None


def _text(elem: Optional[ET.Element], name: str, default: str = "") -> str:
    node = _find_descendant(elem, name)
    if node is not None and node.text is not None:
        return node.text.strip()
    return default


def _parse_iso_duration(val: str, default: float) -> float:
    """Parse simple ONVIF xs:duration values like PT5S or PT10.5S."""
    s = (val or "").strip().upper()
    if s.startswith("PT") and s.endswith("S"):
        try:
            sec = float(s[2:-1])
            if 0.2 <= sec <= 60.0:
                return sec
        except ValueError:
            pass
    return default


def velocity_to_direction(x: float, y: float, deadzone: float = 0.15) -> str:
    """Map ONVIF ContinuousMove (x, y) velocity to Tuya 8-way direction or 'stop'."""
    dx = 0
    dy = 0
    if x > deadzone:
        dx = 1
    elif x < -deadzone:
        dx = -1
    if y > deadzone:
        dy = 1
    elif y < -deadzone:
        dy = -1

    mapping = {
        (0, 1): "up",
        (1, 1): "upright",
        (1, 0): "right",
        (1, -1): "downright",
        (0, -1): "down",
        (-1, -1): "downleft",
        (-1, 0): "left",
        (-1, 1): "upleft",
        (0, 0): "stop",
    }
    return mapping[(dx, dy)]


def _parse_video_info(cam: dict) -> tuple[str, int, int]:
    """Best-effort (encoding, width, height) from Tuya skill JSON."""
    enc = "H264"
    width, height = 1920, 1080
    raw = cam.get("skill")
    if not raw or not isinstance(raw, str):
        return enc, width, height
    try:
        skill = json.loads(raw)
        videos = skill.get("videos") or []
        if videos:
            # Prefer HD (streamType 2) if present
            hd = next((v for v in videos if v.get("streamType") == 2), videos[0])
            w = int(hd.get("width") or 0)
            h = int(hd.get("height") or 0)
            if w > 0 and h > 0:
                width, height = w, h
            if int(hd.get("codecType") or 0) == 4:
                enc = "H265"
    except Exception:
        pass
    return enc, width, height


def _soap_envelope(body_xml: str, soap12: bool = True) -> str:
    ns = _NS_SOAP12 if soap12 else _NS_SOAP11
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<s:Envelope xmlns:s="{ns}" '
        f'xmlns:tds="{_NS_TDS}" '
        f'xmlns:trt="{_NS_TRT}" '
        f'xmlns:tptz="{_NS_TPTZ}" '
        f'xmlns:tt="{_NS_TT}">'
        f"<s:Body>{body_xml}</s:Body>"
        "</s:Envelope>"
    )


def _soap_fault(reason: str, soap12: bool = True) -> str:
    msg = escape(reason)
    if soap12:
        body = (
            "<s:Fault>"
            "<s:Code><s:Value>s:Sender</s:Value></s:Code>"
            f'<s:Reason><s:Text xml:lang="en">{msg}</s:Text></s:Reason>'
            "</s:Fault>"
        )
    else:
        body = (
            "<s:Fault>"
            "<faultcode>s:Client</faultcode>"
            f"<faultstring>{msg}</faultstring>"
            "</s:Fault>"
        )
    return _soap_envelope(body, soap12=soap12)


class OnvifServer:
    """Stateless-friendly SOAP handler translating ONVIF PTZ calls to LocalPtz."""

    def __init__(
        self,
        get_cameras: Callable[[], list[dict]],
        ptz: Any,
        rtsp_port: int = 8554,
        app_version: str = "1.3",
    ) -> None:
        self._get_cameras = get_cameras
        self._ptz = ptz
        self._rtsp_port = rtsp_port
        self._app_version = app_version
        self._lock = threading.Lock()
        self._moving: set[str] = set()
        self._timers: dict[str, threading.Timer] = {}

    def _auto_stop_s(self) -> float:
        try:
            v = float(os.environ.get("TUYA_PTZ_AUTO_STOP_SECONDS", _AUTO_STOP_DEFAULT_S))
            if v >= 0:
                return v
        except Exception:
            pass
        return _AUTO_STOP_DEFAULT_S

    def _cameras(self) -> list[dict]:
        cams = []
        for cam in self._get_cameras() or []:
            did = cam.get("deviceId")
            if not did:
                continue
            fid = slug(cam.get("deviceName") or did)
            cams.append({**cam, "frigateId": fid})
        return cams

    def _resolve_camera(self, token: str | None) -> Optional[dict]:
        cams = self._cameras()
        if not cams:
            return None
        if not token:
            return cams[0]
        tok = token.strip()
        # Strip ptz_ / ptz_node_ / vs_cfg_ / ve_cfg_ prefixes if passed as ConfigurationToken
        for prefix in ("ptz_node_", "ptz_", "vs_cfg_", "ve_cfg_", "vs_"):
            if tok.startswith(prefix):
                tok = tok[len(prefix) :]
                break
        for cam in cams:
            if tok in (
                cam["frigateId"],
                cam["deviceId"],
                cam.get("deviceName"),
            ):
                return cam
        return None

    def _schedule_auto_stop(self, device_id: str, timeout_s: float) -> None:
        with self._lock:
            old = self._timers.pop(device_id, None)
            if old:
                old.cancel()
            self._moving.add(device_id)
            if timeout_s <= 0:
                return

            def _stop_later() -> None:
                with self._lock:
                    self._timers.pop(device_id, None)
                    self._moving.discard(device_id)
                try:
                    self._ptz.stop(device_id)
                except Exception:
                    pass

            timer = threading.Timer(timeout_s, _stop_later)
            timer.daemon = True
            timer.start()
            self._timers[device_id] = timer

    def _clear_moving(self, device_id: str) -> None:
        with self._lock:
            old = self._timers.pop(device_id, None)
            if old:
                old.cancel()
            self._moving.discard(device_id)

    def handle_http(
        self,
        path: str,
        raw_body: bytes,
        host_header: str,
        scheme: str = "http",
    ) -> tuple[int, str, str]:
        """Process an ONVIF HTTP POST SOAP request.

        Returns (http_status, content_type, xml_body).
        """
        base_url = f"{scheme}://{host_header}" if host_header else "http://127.0.0.1:8787"
        try:
            root = ET.fromstring(raw_body)
        except Exception as exc:
            return 400, "application/soap+xml; charset=utf-8", _soap_fault(f"Invalid XML: {exc}")

        soap12 = _NS_SOAP12 in root.tag or _NS_SOAP11 not in root.tag
        ctype = (
            "application/soap+xml; charset=utf-8"
            if soap12
            else "text/xml; charset=utf-8"
        )
        body = _find_child(root, "Body")
        if body is None or len(body) == 0:
            return 400, ctype, _soap_fault("Missing SOAP Body", soap12=soap12)

        req_elem = body[0]
        action = _localname(req_elem.tag)

        # Optional /onvif/<camera_token>/... prefix support
        path_cam_token: Optional[str] = None
        parts = [p for p in path.split("/") if p]
        # e.g. ['onvif', 'Security_Camera', 'device_service']
        if len(parts) >= 3 and parts[0] == "onvif":
            path_cam_token = parts[1]

        try:
            resp_body = self._dispatch(action, req_elem, base_url, path_cam_token)
            return 200, ctype, _soap_envelope(resp_body, soap12=soap12)
        except KeyError as exc:
            return 400, ctype, _soap_fault(f"Unknown token: {exc}", soap12=soap12)
        except ValueError as exc:
            return 400, ctype, _soap_fault(str(exc), soap12=soap12)
        except Exception as exc:
            return 500, ctype, _soap_fault(str(exc), soap12=soap12)

    def _dispatch(
        self,
        action: str,
        req: ET.Element,
        base_url: str,
        path_cam_token: Optional[str],
    ) -> str:
        svc_prefix = f"/onvif/{escape(path_cam_token)}" if path_cam_token else "/onvif"
        device_xaddr = f"{base_url}{svc_prefix}/device_service"
        media_xaddr = f"{base_url}{svc_prefix}/media_service"
        ptz_xaddr = f"{base_url}{svc_prefix}/ptz_service"

        # --- Device Management ---
        if action == "GetSystemDateAndTime":
            now = datetime.now(timezone.utc)
            dt_xml = (
                f"<tt:Time><tt:Hour>{now.hour}</tt:Hour><tt:Minute>{now.minute}</tt:Minute>"
                f"<tt:Second>{now.second}</tt:Second></tt:Time>"
                f"<tt:Date><tt:Year>{now.year}</tt:Year><tt:Month>{now.month}</tt:Month>"
                f"<tt:Day>{now.day}</tt:Day></tt:Date>"
            )
            return (
                "<tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime>"
                "<tt:DateTimeType>NTP</tt:DateTimeType>"
                "<tt:DaylightSavings>false</tt:DaylightSavings>"
                "<tt:TimeZone><tt:TZ>UTC0</tt:TZ></tt:TimeZone>"
                f"<tt:UTCDateTime>{dt_xml}</tt:UTCDateTime>"
                f"<tt:LocalDateTime>{dt_xml}</tt:LocalDateTime>"
                "</tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse>"
            )

        if action == "GetDeviceInformation":
            return (
                "<tds:GetDeviceInformationResponse>"
                "<tds:Manufacturer>Tuya RTSP Bridge</tds:Manufacturer>"
                "<tds:Model>Virtual ONVIF PTZ</tds:Model>"
                f"<tds:FirmwareVersion>{escape(self._app_version)}</tds:FirmwareVersion>"
                "<tds:SerialNumber>tuya-rtsp-bridge</tds:SerialNumber>"
                "<tds:HardwareId>1</tds:HardwareId>"
                "</tds:GetDeviceInformationResponse>"
            )

        if action == "GetServiceCapabilities":
            # Differentiate Device vs Media vs PTZ by request namespace
            ns = req.tag.split("}", 1)[0].lstrip("{")
            if ns == _NS_TPTZ:
                return (
                    "<tptz:GetServiceCapabilitiesResponse>"
                    '<tptz:Capabilities EFlip="false" Reverse="false" '
                    'GetCompatibleConfigurations="false" MoveStatus="true" '
                    'StatusPosition="false"/>'
                    "</tptz:GetServiceCapabilitiesResponse>"
                )
            if ns == _NS_TRT:
                return (
                    "<trt:GetServiceCapabilitiesResponse>"
                    '<trt:Capabilities SnapshotUri="false" Rotation="false" '
                    'VideoSourceMode="false" OSD="false">'
                    '<trt:ProfileCapabilities MaximumNumberOfProfiles="32"/>'
                    '<trt:StreamingCapabilities RTPMulticast="false" RTP_TCP="true" '
                    'RTP_RTSP_TCP="true" NonAggregateControl="false"/>'
                    "</trt:Capabilities>"
                    "</trt:GetServiceCapabilitiesResponse>"
                )
            return (
                "<tds:GetServiceCapabilitiesResponse>"
                "<tds:Capabilities>"
                '<tds:Network IPFilter="false" ZeroConfiguration="false" IPVersion6="false" DynDNS="false"/>'
                '<tds:Security TLS1.0="false" TLS1.1="false" TLS1.2="false" OnboardKeyGeneration="false" '
                'AccessPolicyConfig="false" DefaultAccessPolicy="false" Dot1X="false" RemoteUserHandling="false" '
                'X.509Token="false" SAMLToken="false" KerberosToken="false" UsernameToken="false" '
                'HttpDigest="false" RELToken="false"/>'
                '<tds:System DiscoveryResolve="false" DiscoveryBye="false" RemoteDiscovery="false" '
                'SystemBackup="false" SystemLogging="false" FirmwareUpgrade="false"/>'
                "</tds:Capabilities>"
                "</tds:GetServiceCapabilitiesResponse>"
            )

        if action == "GetCapabilities":
            return (
                "<tds:GetCapabilitiesResponse><tds:Capabilities>"
                f"<tt:Device><tt:XAddr>{device_xaddr}</tt:XAddr></tt:Device>"
                f"<tt:Media><tt:XAddr>{media_xaddr}</tt:XAddr>"
                "<tt:StreamingCapabilities>"
                "<tt:RTPMulticast>false</tt:RTPMulticast>"
                "<tt:RTP_TCP>true</tt:RTP_TCP>"
                "<tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP>"
                "</tt:StreamingCapabilities></tt:Media>"
                f"<tt:PTZ><tt:XAddr>{ptz_xaddr}</tt:XAddr></tt:PTZ>"
                "</tds:Capabilities></tds:GetCapabilitiesResponse>"
            )

        if action == "GetServices":
            return (
                "<tds:GetServicesResponse>"
                f"<tds:Service><tds:Namespace>{_NS_TDS}</tds:Namespace>"
                f"<tds:XAddr>{device_xaddr}</tds:XAddr>"
                "<tds:Version><tt:Major>2</tt:Major><tt:Minor>40</tt:Minor></tds:Version></tds:Service>"
                f"<tds:Service><tds:Namespace>{_NS_TRT}</tds:Namespace>"
                f"<tds:XAddr>{media_xaddr}</tds:XAddr>"
                "<tds:Version><tt:Major>2</tt:Major><tt:Minor>40</tt:Minor></tds:Version></tds:Service>"
                f"<tds:Service><tds:Namespace>{_NS_TPTZ}</tds:Namespace>"
                f"<tds:XAddr>{ptz_xaddr}</tds:XAddr>"
                "<tds:Version><tt:Major>2</tt:Major><tt:Minor>40</tt:Minor></tds:Version></tds:Service>"
                "</tds:GetServicesResponse>"
            )

        # --- Media Service ---
        if action == "GetVideoSources":
            cams = self._select_cams(path_cam_token)
            items = []
            for cam in cams:
                fid = escape(cam["frigateId"])
                _, w, h = _parse_video_info(cam)
                items.append(
                    f'<trt:VideoSources token="vs_{fid}">'
                    "<tt:Framerate>15</tt:Framerate>"
                    f"<tt:Resolution><tt:Width>{w}</tt:Width><tt:Height>{h}</tt:Height></tt:Resolution>"
                    "</trt:VideoSources>"
                )
            return f"<trt:GetVideoSourcesResponse>{''.join(items)}</trt:GetVideoSourcesResponse>"

        if action == "GetProfiles":
            cams = self._select_cams(path_cam_token)
            items = [self._profile_xml(cam, tag="trt:Profiles") for cam in cams]
            return f"<trt:GetProfilesResponse>{''.join(items)}</trt:GetProfilesResponse>"

        if action == "GetProfile":
            tok = _text(req, "ProfileToken") or path_cam_token
            cam = self._resolve_camera(tok)
            if not cam:
                raise KeyError(tok or "profile")
            return f"<trt:GetProfileResponse>{self._profile_xml(cam, tag='trt:Profile')}</trt:GetProfileResponse>"

        if action == "GetStreamUri":
            tok = _text(req, "ProfileToken") or path_cam_token
            cam = self._resolve_camera(tok)
            if not cam:
                raise KeyError(tok or "profile")
            host_only = base_url.split("://", 1)[1].split(":", 1)[0]
            rtsp_path = cam.get("rtspPath") or f"/{cam['deviceId']}"
            uri = f"rtsp://{host_only}:{self._rtsp_port}{rtsp_path}/hd"
            return (
                "<trt:GetStreamUriResponse><trt:MediaUri>"
                f"<tt:Uri>{escape(uri)}</tt:Uri>"
                "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>"
                "<tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
                "<tt:Timeout>PT60S</tt:Timeout>"
                "</trt:MediaUri></trt:GetStreamUriResponse>"
            )

        # --- PTZ Service ---
        if action in ("GetNodes", "GetNode"):
            cams = self._select_cams(path_cam_token)
            if action == "GetNode":
                tok = _text(req, "NodeToken") or path_cam_token
                cam = self._resolve_camera(tok)
                if not cam:
                    raise KeyError(tok or "node")
                return f"<tptz:GetNodeResponse>{self._ptz_node_xml(cam, 'tptz:PTZNode')}</tptz:GetNodeResponse>"
            items = [self._ptz_node_xml(cam, "tptz:PTZNode") for cam in cams]
            return f"<tptz:GetNodesResponse>{''.join(items)}</tptz:GetNodesResponse>"

        if action in ("GetConfigurations", "GetConfiguration"):
            if action == "GetConfiguration":
                tok = _text(req, "PTZConfigurationToken") or path_cam_token
                cam = self._resolve_camera(tok)
                if not cam:
                    raise KeyError(tok or "configuration")
                return (
                    "<tptz:GetConfigurationResponse>"
                    f"{self._ptz_cfg_xml(cam, 'tptz:PTZConfiguration')}"
                    "</tptz:GetConfigurationResponse>"
                )
            cams = self._select_cams(path_cam_token)
            items = [self._ptz_cfg_xml(cam, "tptz:PTZConfiguration") for cam in cams]
            return f"<tptz:GetConfigurationsResponse>{''.join(items)}</tptz:GetConfigurationsResponse>"

        if action == "GetConfigurationOptions":
            return (
                "<tptz:GetConfigurationOptionsResponse>"
                "<tptz:PTZConfigurationOptions>"
                "<tt:Spaces>"
                "<tt:ContinuousPanTiltVelocitySpace>"
                f"<tt:URI>{_VEL_SPACE}</tt:URI>"
                "<tt:XRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:XRange>"
                "<tt:YRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:YRange>"
                "</tt:ContinuousPanTiltVelocitySpace>"
                "</tt:Spaces>"
                "<tt:PTZTimeout><tt:Min>PT1S</tt:Min><tt:Max>PT60S</tt:Max></tt:PTZTimeout>"
                "</tptz:PTZConfigurationOptions>"
                "</tptz:GetConfigurationOptionsResponse>"
            )

        if action == "GetPresets":
            return "<tptz:GetPresetsResponse/>"

        if action == "GetStatus":
            tok = _text(req, "ProfileToken") or path_cam_token
            cam = self._resolve_camera(tok)
            if not cam:
                raise KeyError(tok or "profile")
            with self._lock:
                moving = cam["deviceId"] in self._moving
            mv = "MOVING" if moving else "IDLE"
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return (
                "<tptz:GetStatusResponse><tptz:PTZStatus>"
                f'<tt:Position><tt:PanTilt x="0" y="0" space="{_POS_SPACE}"/></tt:Position>'
                f"<tt:MoveStatus><tt:PanTilt>{mv}</tt:PanTilt></tt:MoveStatus>"
                f"<tt:UtcTime>{now_iso}</tt:UtcTime>"
                "</tptz:PTZStatus></tptz:GetStatusResponse>"
            )

        if action == "ContinuousMove":
            tok = _text(req, "ProfileToken") or path_cam_token
            cam = self._resolve_camera(tok)
            if not cam:
                raise KeyError(tok or "profile")
            pt = _find_descendant(req, "PanTilt")
            x = float(pt.attrib.get("x", 0.0)) if pt is not None else 0.0
            y = float(pt.attrib.get("y", 0.0)) if pt is not None else 0.0
            direction = velocity_to_direction(x, y)
            did = cam["deviceId"]
            if direction == "stop":
                self._clear_moving(did)
                self._ptz.stop(did)
            else:
                timeout_s = _parse_iso_duration(_text(req, "Timeout"), self._auto_stop_s())
                self._ptz.move(did, direction)
                self._schedule_auto_stop(did, timeout_s)
            return "<tptz:ContinuousMoveResponse/>"

        if action == "Stop":
            tok = _text(req, "ProfileToken") or path_cam_token
            cam = self._resolve_camera(tok)
            if not cam:
                raise KeyError(tok or "profile")
            did = cam["deviceId"]
            self._clear_moving(did)
            self._ptz.stop(did)
            return "<tptz:StopResponse/>"

        raise ValueError(f"Unsupported ONVIF action: {action}")

    def _select_cams(self, path_cam_token: Optional[str]) -> list[dict]:
        if path_cam_token:
            cam = self._resolve_camera(path_cam_token)
            return [cam] if cam else []
        return self._cameras()

    def _ptz_cfg_xml(self, cam: dict, tag: str) -> str:
        fid = escape(cam["frigateId"])
        return (
            f'<{tag} token="ptz_{fid}">'
            f"<tt:Name>ptz_{fid}</tt:Name>"
            "<tt:UseCount>1</tt:UseCount>"
            f"<tt:NodeToken>ptz_node_{fid}</tt:NodeToken>"
            f"<tt:DefaultContinuousPanTiltVelocitySpace>{_VEL_SPACE}</tt:DefaultContinuousPanTiltVelocitySpace>"
            "<tt:DefaultPTZTimeout>PT10S</tt:DefaultPTZTimeout>"
            "<tt:DefaultPTZSpeed>"
            f'<tt:PanTilt x="0.5" y="0.5" space="{_VEL_SPACE}"/>'
            "</tt:DefaultPTZSpeed>"
            f"</{tag}>"
        )

    def _ptz_node_xml(self, cam: dict, tag: str) -> str:
        fid = escape(cam["frigateId"])
        return (
            f'<{tag} token="ptz_node_{fid}" FixedHomePosition="false">'
            f"<tt:Name>ptz_node_{fid}</tt:Name>"
            "<tt:SupportedPTZSpaces>"
            "<tt:ContinuousPanTiltVelocitySpace>"
            f"<tt:URI>{_VEL_SPACE}</tt:URI>"
            "<tt:XRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:XRange>"
            "<tt:YRange><tt:Min>-1</tt:Min><tt:Max>1</tt:Max></tt:YRange>"
            "</tt:ContinuousPanTiltVelocitySpace>"
            "</tt:SupportedPTZSpaces>"
            "<tt:MaximumNumberOfPresets>0</tt:MaximumNumberOfPresets>"
            "<tt:HomeSupported>false</tt:HomeSupported>"
            f"</{tag}>"
        )

    def _profile_xml(self, cam: dict, tag: str) -> str:
        fid = escape(cam["frigateId"])
        enc, w, h = _parse_video_info(cam)
        return (
            f'<{tag} token="{fid}" fixed="true">'
            f"<tt:Name>{fid}</tt:Name>"
            f'<tt:VideoSourceConfiguration token="vs_cfg_{fid}">'
            f"<tt:Name>vs_cfg_{fid}</tt:Name>"
            "<tt:UseCount>1</tt:UseCount>"
            f"<tt:SourceToken>vs_{fid}</tt:SourceToken>"
            f'<tt:Bounds x="0" y="0" width="{w}" height="{h}"/>'
            "</tt:VideoSourceConfiguration>"
            f'<tt:VideoEncoderConfiguration token="ve_cfg_{fid}">'
            f"<tt:Name>ve_cfg_{fid}</tt:Name>"
            "<tt:UseCount>1</tt:UseCount>"
            f"<tt:Encoding>{enc}</tt:Encoding>"
            f"<tt:Resolution><tt:Width>{w}</tt:Width><tt:Height>{h}</tt:Height></tt:Resolution>"
            "<tt:Quality>5</tt:Quality>"
            "<tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit>"
            "<tt:EncodingInterval>1</tt:EncodingInterval>"
            "<tt:BitrateLimit>2048</tt:BitrateLimit></tt:RateControl>"
            "<tt:SessionTimeout>PT60S</tt:SessionTimeout>"
            "</tt:VideoEncoderConfiguration>"
            f"{self._ptz_cfg_xml(cam, 'tt:PTZConfiguration')}"
            f"</{tag}>"
        )
