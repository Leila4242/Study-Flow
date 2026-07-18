import unittest

from app import app


class AuthNavigationTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_root_route_shows_login_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome back", response.data)
        self.assertIn(b"Create one", response.data)

    def test_login_page_contains_register_link(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/register", response.data)
        self.assertIn(b"Create one", response.data)

    def test_register_page_contains_login_link(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/login", response.data)
        self.assertIn(b"Log in", response.data)


if __name__ == "__main__":
    unittest.main()
