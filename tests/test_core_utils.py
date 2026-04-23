import os
import unittest
from unittest.mock import patch, MagicMock

import data
import ui_utils
import ai_utils
from flask import Flask


class TestSessionTypeHelpers(unittest.TestCase):
    def test_is_race(self):
        self.assertTrue(data.is_race("Race"))
        self.assertTrue(data.is_race("Sprint"))
        self.assertFalse(data.is_race("Qualifying"))

    def test_is_qualifying(self):
        self.assertTrue(data.is_qualifying("Qualifying"))
        self.assertTrue(data.is_qualifying("Sprint Shootout"))
        self.assertFalse(data.is_qualifying("Race"))

    def test_is_practice(self):
        self.assertTrue(data.is_practice("Practice 1"))
        self.assertTrue(data.is_practice("FP2"))
        self.assertFalse(data.is_practice("Sprint"))


class TestAiCache(unittest.TestCase):
    def test_cache_round_trip(self):
        ctx = "test_session_context"
        q = "Who had better pace?"
        r = "Driver A had better average pace."
        ai_utils.store_cached_response(ctx, q, r)
        self.assertEqual(ai_utils.get_cached_response(ctx, q), r)

    def test_cache_key_normalizes_question(self):
        key1 = ai_utils._cache_key("ctx", " Hello  ")
        key2 = ai_utils._cache_key("ctx", "hello")
        self.assertEqual(key1, key2)


class TestFeedbackAdminAuth(unittest.TestCase):
    def setUp(self):
        self.flask_app = Flask(__name__)

    def test_authorized_via_query_param(self):
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            with self.flask_app.test_request_context("/?feedback_admin=secret"):
                with patch.object(ui_utils.flask, "request") as req:
                    req.headers = MagicMock()
                    req.cookies = MagicMock()
                    req.headers.get.return_value = ""
                    req.cookies.get.return_value = ""
                    self.assertTrue(ui_utils._feedback_admin_authorized("?feedback_admin=secret"))

    def test_authorized_via_header(self):
        with patch.dict(os.environ, {"FEEDBACK_ADMIN_TOKEN": "secret"}, clear=False):
            with self.flask_app.test_request_context("/"):
                with patch.object(ui_utils.flask, "request") as req:
                    req.headers = MagicMock()
                    req.cookies = MagicMock()
                    req.headers.get.return_value = "secret"
                    req.cookies.get.return_value = ""
                    self.assertTrue(ui_utils._feedback_admin_authorized(""))


if __name__ == "__main__":
    unittest.main()
