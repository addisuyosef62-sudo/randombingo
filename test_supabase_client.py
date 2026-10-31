import os
import unittest
from unittest.mock import patch

from supabase_client import supabase_request


class SupabaseClientTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://example.supabase.co/rest/v1/",
            "SUPABASE_SERVICE_ROLE_KEY": "test-key",
        },
    )
    @patch("supabase_client.urlopen")
    def test_rest_endpoint_url_is_normalized(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"[]"

        result = supabase_request("GET", "user_profiles")

        self.assertEqual(result, [])
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://example.supabase.co/rest/v1/user_profiles",
        )


if __name__ == "__main__":
    unittest.main()
