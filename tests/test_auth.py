import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import tempfile
import shutil
import sys
import os

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tuya_client import TuyaClient

class TestAuth(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.client = TuyaClient(Path(self.test_dir))

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch.object(TuyaClient, 'password_login')
    def test_login_with_password(self, mock_password_login):
        mock_password_login.return_value = {
            "sid": "test_sid",
            "uid": "test_uid",
            "email": "test@example.com"
        }
        
        result = self.client.login_with_password("test@example.com", "password123", "34", auto_renew=True)
        
        self.assertEqual(result["sid"], "test_sid")
        mock_password_login.assert_called_once_with("test@example.com", "password123", "34")
        
        cloud_auth_path = self.client._cloud_auth_path()
        self.assertTrue(cloud_auth_path.exists())
        
        data = json.loads(cloud_auth_path.read_text(encoding="utf-8"))
        self.assertEqual(data["email"], "test@example.com")
        self.assertEqual(data["password"], "password123")
        self.assertEqual(data["countryCode"], "34")

    @patch.object(TuyaClient, 'password_login')
    def test_try_password_relogin(self, mock_password_login):
        auth_file = self.client._cloud_auth_path()
        auth_file.write_text(json.dumps({"email": "user@test.com", "password": "secret", "countryCode": "34"}), encoding="utf-8")
        mock_password_login.return_value = {"sid": "new_sid"}
        
        ok = self.client._try_password_relogin()
        self.assertTrue(ok)
        mock_password_login.assert_called_once_with("user@test.com", "secret", "34")


class TestTuyaErrorText(unittest.TestCase):
    def test_known_code_is_english(self):
        from tuya_client import tuya_error_text
        body = {"success": False, "errorCode": "USER_PASSWD_WRONG", "errorMsg": "账号或密码错误"}
        self.assertTrue(tuya_error_text(body, "x").startswith("Wrong email or password"))

    def test_unknown_code_keeps_message_and_code(self):
        from tuya_client import tuya_error_text
        self.assertEqual(tuya_error_text({"errorCode": "FOO", "errorMsg": "bar"}, "x"), "bar (FOO)")

    def test_fallback(self):
        from tuya_client import tuya_error_text
        self.assertEqual(tuya_error_text({}, "fallback"), "fallback")


if __name__ == '__main__':
    unittest.main()
