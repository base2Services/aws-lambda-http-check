import hashlib
import hmac
import unittest
from unittest.mock import patch

from handler import (
    HEALTH_CONFIG_OVERRIDES_HEADER,
    Config,
    HmacSigner,
    _hash_override_header,
)

SAMPLE_OVERRIDE_JSON = (
    '{"roles":{"my_service":{"probes":[{"id":"my-probe","enabled":false}]}}}'
)


class TestHashOverrideHeader(unittest.TestCase):
    def test_absent_header_hashes_empty_string(self):
        expected = hashlib.sha256(b'').hexdigest()
        self.assertEqual(_hash_override_header(None), expected)

    def test_present_header_hashes_raw_value(self):
        expected = hashlib.sha256(SAMPLE_OVERRIDE_JSON.encode('utf-8')).hexdigest()
        self.assertEqual(_hash_override_header(SAMPLE_OVERRIDE_JSON), expected)


class TestSevenLineCanonicalContract(unittest.TestCase):
    def test_canonical_uses_seven_lines(self):
        body_hash = hashlib.sha256(b'').hexdigest()
        override_hash = _hash_override_header(None)
        canonical = '\n'.join(
            ['GET', '/health', '1777508123', 'abc123nonce', '', body_hash, override_hash]
        )
        self.assertEqual(canonical.count('\n'), 6)
        self.assertTrue(canonical.endswith(override_hash))
        self.assertEqual(
            canonical,
            'GET\n/health\n1777508123\nabc123nonce\n\n'
            + body_hash
            + '\n'
            + override_hash,
        )


class TestHmacSigner(unittest.TestCase):
    def setUp(self):
        config = Config({})
        self.signer = HmacSigner(config)
        self.signer.secret_ssm = '/test/secret'

    @patch.object(HmacSigner, '_fetch_secret', return_value='test-secret')
    def test_signs_with_empty_override_hash_when_header_absent(self, _mock_secret):
        body_hash = hashlib.sha256(b'').hexdigest()
        empty_override_hash = _hash_override_header(None)
        canonical = '\n'.join(
            ['GET', '/health', '100', 'nonce', '', body_hash, empty_override_hash]
        )
        expected = hmac.new(
            b'test-secret',
            canonical.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        with patch('handler.time.time', return_value=100):
            with patch('handler.uuid.uuid4') as mock_uuid:
                mock_uuid.return_value.hex = 'nonce'
                headers = self.signer.sign('GET', '/health', '', b'')

        self.assertEqual(headers['X-Health-Signature'], expected)

    @patch.object(HmacSigner, '_fetch_secret', return_value='test-secret')
    def test_signs_with_override_header_hash_when_header_present(self, _mock_secret):
        body_hash = hashlib.sha256(b'').hexdigest()
        override_hash = _hash_override_header(SAMPLE_OVERRIDE_JSON)
        canonical = '\n'.join(
            ['GET', '/health', '100', 'nonce', '', body_hash, override_hash]
        )
        expected = hmac.new(
            b'test-secret',
            canonical.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        with patch('handler.time.time', return_value=100):
            with patch('handler.uuid.uuid4') as mock_uuid:
                mock_uuid.return_value.hex = 'nonce'
                headers = self.signer.sign(
                    'GET',
                    '/health',
                    '',
                    b'',
                    request_headers={
                        HEALTH_CONFIG_OVERRIDES_HEADER.lower(): SAMPLE_OVERRIDE_JSON
                    }

        self.assertEqual(headers['X-Health-Signature'], expected)


if __name__ == '__main__':
    unittest.main()
