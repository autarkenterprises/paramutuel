import unittest

from service.control_panel.security import token_authorized


class SecurityTests(unittest.TestCase):
    def test_requires_expected_token(self):
        self.assertFalse(token_authorized(expected_token=None, auth_header=None, x_token=None))

    def test_accepts_x_control_token(self):
        self.assertTrue(token_authorized(expected_token="secret", auth_header=None, x_token="secret"))
        self.assertFalse(token_authorized(expected_token="secret", auth_header=None, x_token="nope"))

    def test_accepts_bearer_token(self):
        self.assertTrue(
            token_authorized(expected_token="secret", auth_header="Bearer secret", x_token=None)
        )
        self.assertFalse(
            token_authorized(expected_token="secret", auth_header="Bearer nope", x_token=None)
        )


if __name__ == "__main__":
    unittest.main()
