"""Unit tests for ONVIF PTZ server and LAN PTZ subnet/IP helpers — no network."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_ptz import (  # noqa: E402
    LocalPtz,
    _env_camera_ips,
    _env_prefixes,
    _expand_subnet_to_prefixes,
)
from onvif_server import OnvifServer, velocity_to_direction  # noqa: E402


def _soap(inner: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
        'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
        'xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" '
        'xmlns:tt="http://www.onvif.org/ver10/schema">'
        f"<s:Body>{inner}</s:Body></s:Envelope>"
    ).encode("utf-8")


class TestSubnetAndIpHelpers(unittest.TestCase):
    def test_expand_cidr_22(self) -> None:
        self.assertEqual(
            _expand_subnet_to_prefixes("192.168.2.110/22"),
            ["192.168.0.", "192.168.1.", "192.168.2.", "192.168.3."],
        )

    def test_expand_prefix_and_clamp_wide(self) -> None:
        self.assertEqual(_expand_subnet_to_prefixes("192.168.0."), ["192.168.0."])
        self.assertEqual(_expand_subnet_to_prefixes("10.1.2.3/8"), ["10.1.2."])

    def test_env_subnets_and_ips(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TUYA_LAN_SUBNETS": "192.168.0.0/23,10.0.5.",
                "TUYA_CAMERA_IPS": "dev1=192.168.0.229,dev2=192.168.0.188",
            },
        ):
            self.assertEqual(
                _env_prefixes(),
                ["192.168.0.", "192.168.1.", "10.0.5."],
            )
            self.assertEqual(
                _env_camera_ips(),
                {
                    "dev1": {"ip": "192.168.0.229"},
                    "dev2": {"ip": "192.168.0.188"},
                },
            )

    def test_set_camera_ip_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            client = MagicMock()
            client.region_id = "eu"
            client.login = {}
            client._post.return_value = {"result": {"localKey": "0123456789abcdef"}}
            ptz = LocalPtz(Path(td), client)
            with patch.object(ptz, "_probe", return_value=True):
                res = ptz.set_camera_ip("bfb0f3ab3dfe35ff129ath", "192.168.0.229", 3.4)
            self.assertTrue(res["probed"])
            self.assertEqual(
                ptz.lan_cache(),
                {"bfb0f3ab3dfe35ff129ath": {"ip": "192.168.0.229", "version": 3.4}},
            )
            # Secret localKey must not be exposed in lan_cache or lan.json
            saved = (Path(td) / "lan.json").read_text(encoding="utf-8")
            self.assertNotIn("0123456789abcdef", saved)
            ptz.set_camera_ip("bfb0f3ab3dfe35ff129ath", "")
            self.assertEqual(ptz.lan_cache(), {})


class TestOnvifServer(unittest.TestCase):
    def setUp(self) -> None:
        self.cams = [
            {
                "deviceId": "bfb0f3ab3dfe35ff129ath",
                "deviceName": "Security Camera",
                "rtspPath": "/Security_Camera",
                "skill": '{"videos":[{"streamType":2,"width":1920,"height":1080,"codecType":2}]}',
            },
            {
                "deviceId": "bfdd9d3da5cfbc565bammg",
                "deviceName": "Camera 3D printer impresora",
                "rtspPath": "/Camera_3D_printer_impresora",
                "skill": "",
            },
        ]
        self.ptz = MagicMock()
        self.srv = OnvifServer(lambda: self.cams, self.ptz, rtsp_port=8554)

    def test_velocity_to_direction(self) -> None:
        self.assertEqual(velocity_to_direction(0.0, 0.5), "up")
        self.assertEqual(velocity_to_direction(0.0, -0.5), "down")
        self.assertEqual(velocity_to_direction(-0.5, 0.0), "left")
        self.assertEqual(velocity_to_direction(0.5, 0.0), "right")
        self.assertEqual(velocity_to_direction(0.5, 0.5), "upright")
        self.assertEqual(velocity_to_direction(0.0, 0.0), "stop")

    def test_capabilities_and_profiles(self) -> None:
        code, ctype, xml = self.srv.handle_http(
            "/onvif/device_service",
            _soap('<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>'),
            "tuya-rtsp:8787",
        )
        self.assertEqual(code, 200)
        self.assertIn("application/soap+xml", ctype)
        self.assertIn("http://tuya-rtsp:8787/onvif/media_service", xml)
        self.assertIn("http://tuya-rtsp:8787/onvif/ptz_service", xml)

        code, _, pxml = self.srv.handle_http(
            "/onvif/media_service",
            _soap("<trt:GetProfiles/>"),
            "tuya-rtsp:8787",
        )
        self.assertEqual(code, 200)
        root = ET.fromstring(pxml)
        profiles = [el for el in root.iter() if el.tag.endswith("}Profiles")]
        tokens = [p.attrib.get("token") for p in profiles]
        self.assertEqual(tokens, ["Security_Camera", "Camera_3D_printer_impresora"])

    def test_continuous_move_and_stop(self) -> None:
        code, _, _ = self.srv.handle_http(
            "/onvif/ptz_service",
            _soap(
                "<tptz:ContinuousMove>"
                "<tptz:ProfileToken>Security_Camera</tptz:ProfileToken>"
                '<tptz:Velocity><tt:PanTilt x="-0.5" y="0"/></tptz:Velocity>'
                "</tptz:ContinuousMove>"
            ),
            "tuya-rtsp:8787",
        )
        self.assertEqual(code, 200)
        self.ptz.move.assert_called_once_with("bfb0f3ab3dfe35ff129ath", "left")

        _, _, status_xml = self.srv.handle_http(
            "/onvif/ptz_service",
            _soap("<tptz:GetStatus><tptz:ProfileToken>Security_Camera</tptz:ProfileToken></tptz:GetStatus>"),
            "tuya-rtsp:8787",
        )
        self.assertIn(">MOVING<", status_xml)

        code, _, _ = self.srv.handle_http(
            "/onvif/ptz_service",
            _soap(
                "<tptz:Stop>"
                "<tptz:ProfileToken>Security_Camera</tptz:ProfileToken>"
                "<tptz:PanTilt>true</tptz:PanTilt>"
                "</tptz:Stop>"
            ),
            "tuya-rtsp:8787",
        )
        self.assertEqual(code, 200)
        self.ptz.stop.assert_called_once_with("bfb0f3ab3dfe35ff129ath")

        _, _, status_xml = self.srv.handle_http(
            "/onvif/ptz_service",
            _soap("<tptz:GetStatus><tptz:ProfileToken>Security_Camera</tptz:ProfileToken></tptz:GetStatus>"),
            "tuya-rtsp:8787",
        )
        self.assertIn(">IDLE<", status_xml)


if __name__ == "__main__":
    unittest.main()
