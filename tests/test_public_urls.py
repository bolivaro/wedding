from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from guests.services.notifications import _absolute_url
from guests.services.ticket import _public_information_url
from lesbon.public_urls import normalize_public_base_url


class PublicURLTests(SimpleTestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_null_base_url_falls_back_to_canonical_production_domain(self):
        self.assertEqual(
            normalize_public_base_url("NULL", debug=False),
            "https://www.leslieniboli.fr",
        )

    def test_apex_domain_is_canonicalized_to_working_www_domain(self):
        self.assertEqual(
            normalize_public_base_url("https://leslieniboli.fr", debug=False),
            "https://www.leslieniboli.fr",
        )

    @patch.dict(
        "os.environ",
        {"RAILWAY_PUBLIC_DOMAIN": "wedding-production.up.railway.app"},
        clear=True,
    )
    def test_local_production_url_falls_back_to_railway_domain(self):
        self.assertEqual(
            normalize_public_base_url("http://127.0.0.1:8000", debug=False),
            "https://wedding-production.up.railway.app",
        )

    @override_settings(DEBUG=False, SITE_BASE_URL="NULL")
    @patch.dict("os.environ", {}, clear=True)
    def test_email_verification_link_never_contains_null(self):
        self.assertEqual(
            _absolute_url("/invites/email/verify/selector/secret/"),
            "https://www.leslieniboli.fr/invites/email/verify/selector/secret/",
        )

    @override_settings(
        DEBUG=False,
        SITE_BASE_URL="https://leslieniboli.fr",
    )
    def test_invalid_ticket_link_falls_back_to_public_page(self):
        self.assertEqual(
            _public_information_url("http://localhost:8000/programme/", "programme/"),
            "https://www.leslieniboli.fr/programme/",
        )
