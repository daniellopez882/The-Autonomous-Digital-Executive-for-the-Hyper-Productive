import unittest
from src.services.auth_service import GoogleAuthManager

class TestAuth(unittest.TestCase):
    def test_auth_manager_init(self):
        auth = GoogleAuthManager()
        self.assertIsNotNone(auth.credentials_path)

if __name__ == '__main__':
    unittest.main()
