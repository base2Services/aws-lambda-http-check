import json
import os
import http.client
import hmac
import time
import uuid
import boto3
from time import perf_counter as pc
from urllib.parse import urlparse
import ssl
from io import StringIO
import gzip
import re
import hashlib

HEALTH_CONFIG_OVERRIDES_HEADER = 'X-Health-Config-Overrides'


def _hash_override_header(raw_value):
    """SHA-256 hex digest of the raw override header value (empty string when absent)."""
    value = raw_value if isinstance(raw_value, str) else ''
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class Config:
    """Lambda function runtime configuration"""

    ENDPOINT = 'ENDPOINT'
    METHOD = 'METHOD'
    PAYLOAD = 'PAYLOAD'
    TIMEOUT = 'TIMEOUT'
    HEADERS = 'HEADERS'
    USER_AGENT = 'USER_AGENT'
    COMPRESSED = 'COMPRESSED'
    REPORT_RESPONSE_BODY = 'REPORT_RESPONSE_BODY'
    REPORT_AS_CW_METRICS = 'REPORT_AS_CW_METRICS'
    CW_METRICS_NAMESPACE = 'CW_METRICS_NAMESPACE'
    CW_METRICS_METRIC_NAME = 'CW_METRICS_METRIC_NAME'
    BODY_REGEX_MATCH = 'BODY_REGEX_MATCH'
    STATUS_CODE_MATCH = 'STATUS_CODE_MATCH'
    FAIL_ON_STATUS_CODE_MISMATCH = 'FAIL_ON_STATUS_CODE_MISMATCH'
    HMAC_SECRET_SSM = 'HMAC_SECRET_SSM'
    HMAC_KEY_ID = 'HMAC_KEY_ID'
    HMAC_HEADER_PREFIX = 'HMAC_HEADER_PREFIX'

    def __init__(self, event):
        self.event = event
        self.defaults = {
            self.ENDPOINT: 'https://google.com.au',
            self.METHOD: 'GET',
            self.PAYLOAD: None,
            self.TIMEOUT: 120,
            self.REPORT_RESPONSE_BODY: '0',
            self.REPORT_AS_CW_METRICS: '1',
            self.CW_METRICS_NAMESPACE: 'HttpCheck',
            self.USER_AGENT: '',
            self.HEADERS: '',
            self.COMPRESSED: '0',
            self.BODY_REGEX_MATCH: None,
            self.STATUS_CODE_MATCH: None,
            self.FAIL_ON_STATUS_CODE_MISMATCH: None,
            self.HMAC_SECRET_SSM: None,
            self.HMAC_KEY_ID: 'default',
            self.HMAC_HEADER_PREFIX: 'X-Health',
        }

    def __get_property(self, property_name):
        if property_name in self.event:
            return self.event[property_name]
        if property_name in os.environ:
            return os.environ[property_name]
        if property_name in self.defaults:
            return self.defaults[property_name]
        return None

    @property
    def endpoint(self):
        return self.__get_property(self.ENDPOINT)

    @property
    def method(self):
        return self.__get_property(self.METHOD)

    @property
    def payload(self):
        payload = self.__get_property(self.PAYLOAD)
        if payload is not None:
            return payload.encode('utf-8')
        return payload

    @property
    def timeout(self):
        return self.__get_property(self.TIMEOUT)

    @property
    def reportbody(self):
        return self.__get_property(self.REPORT_RESPONSE_BODY)

    @property
    def headers(self):
        header_dict = {}
        headers = self.__get_property(self.HEADERS)
        user_agent = self.__get_property(self.USER_AGENT)
        if user_agent != '':
            header_dict['User-Agent'] = user_agent
        
        if headers == '':
            return header_dict
        else:
            try:
                for u in headers.split(' '):
                    key = u.split("=")[0]
                    val = u.split("=")[1].replace('%20',' ')
                    header_dict[key] = val
                return header_dict
            except:
                print(f"Could not decode headers: {header_dict}")
                return header_dict

    @property
    def bodyregexmatch(self):
        return self.__get_property(self.BODY_REGEX_MATCH)

    @property
    def statuscodematch(self):
        return self.__get_property(self.STATUS_CODE_MATCH)

    @property
    def fail_on_statuscode_mismatch(self):
        return self.__get_property(self.FAIL_ON_STATUS_CODE_MISMATCH)

    @property
    def hmac_secret_ssm(self):
        return self.__get_property(self.HMAC_SECRET_SSM)

    @property
    def hmac_key_id(self):
        return self.__get_property(self.HMAC_KEY_ID)

    @property
    def hmac_header_prefix(self):
        return self.__get_property(self.HMAC_HEADER_PREFIX)

    @property
    def cwoptions(self):
        return {
            'enabled': self.__get_property(self.REPORT_AS_CW_METRICS),
            'namespace': self.__get_property(self.CW_METRICS_NAMESPACE),
        }
    
    @property
    def compressed(self):
        return self.__get_property(self.COMPRESSED)


# Module-level SSM secret cache: {ssm_path: (secret_value, fetched_at)}
# Cached values are reused across warm Lambda invocations for up to SSM_CACHE_TTL seconds.
_SSM_CACHE = {}
_SSM_CACHE_TTL = 600  # 10 minutes


class HmacSigner:
    """Generates HMAC signed request headers using a secret fetched from SSM Parameter Store.

    The canonical string used for signing is:
        METHOD\\nPATH\\nTIMESTAMP\\nNONCE\\nQUERY\\nBODY_HASH\\nOVERRIDE_HEADER_HASH

    OVERRIDE_HEADER_HASH is SHA-256 of the raw X-Health-Config-Overrides header value,
    or SHA-256 of an empty string when that header is not sent.
    """

    def __init__(self, config):
        self.secret_ssm = config.hmac_secret_ssm
        self.key_id = config.hmac_key_id
        self.header_prefix = config.hmac_header_prefix

    def _fetch_secret(self):
        now = time.time()
        cached = _SSM_CACHE.get(self.secret_ssm)
        if cached and (now - cached[1]) < _SSM_CACHE_TTL:
            return cached[0]
        ssm = boto3.client('ssm')
        response = ssm.get_parameter(Name=self.secret_ssm, WithDecryption=True)
        secret = response['Parameter']['Value']
        _SSM_CACHE[self.secret_ssm] = (secret, now)
        return secret

    def sign(self, method, path, query, body, request_headers=None):
        secret = self._fetch_secret()
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        body_hash = hashlib.sha256(body if body else b'').hexdigest()
        override_raw = (request_headers or {}).get(HEALTH_CONFIG_OVERRIDES_HEADER)
        override_hash = _hash_override_header(override_raw)
        canonical = '\n'.join(
            [method, path, timestamp, nonce, query or '', body_hash, override_hash]
        )
        signature = hmac.new(
            secret.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        prefix = self.header_prefix
        if 'HTTP_DEBUG' in os.environ and os.environ['HTTP_DEBUG'] == '1':
            print(f"HMAC canonical string: {repr(canonical)}")
        return {
            f'{prefix}-Signature': signature,
            f'{prefix}-Key-Id': self.key_id,
            f'{prefix}-Timestamp': timestamp,
            f'{prefix}-Nonce': nonce,
        }


class HttpCheck:
    """Execution of HTTP(s) request"""

    def __init__(self, config):
        self.method = config.method
        self.endpoint = config.endpoint
        self.timeout = config.timeout
        self.payload = config.payload
        self.headers = config.headers
        self.compressed = config.compressed
        self.bodyregexmatch = config.bodyregexmatch
        self.statuscodematch = config.statuscodematch
        self.fail_on_statuscode_mismatch = config.fail_on_statuscode_mismatch
        self.hmac_signer = HmacSigner(config) if config.hmac_secret_ssm else None

    def execute(self):
        url = urlparse(self.endpoint)
        location = url.netloc
        if url.scheme == 'http':
            request = http.client.HTTPConnection(location, timeout=int(self.timeout))

        if url.scheme == 'https':
            request = http.client.HTTPSConnection(location, timeout=int(self.timeout), context=ssl._create_unverified_context())

        if 'HTTP_DEBUG' in os.environ and os.environ['HTTP_DEBUG'] == '1':
            request.set_debuglevel(1)

        path = url.path
        if path == '':
            path = '/'
        if url.query is not None:
            path = path + "?" + url.query

        if self.hmac_signer:
            hmac_headers = self.hmac_signer.sign(
                self.method,
                url.path if url.path else '/',
                url.query or '',
                self.payload,
                request_headers=self.headers,
            )
            self.headers.update(hmac_headers)

        if self.compressed == '1':
            self.headers['Accept-Encoding'] = 'deflate, gzip'
        
        try:
            t0 = pc()
            
            # perform request
            request.request(self.method, path, self.payload, self.headers)
            # read response
            response_data = request.getresponse()

            # stop the stopwatch
            t1 = pc()
            print(f"Request headers: {self.headers}")
            print(f"Headers: {response_data.getheaders()}")
            
            if response_data.getheader('Content-Encoding') == 'gzip':
                data = gzip.decompress(response_data.read())
                response_body = str(data,'utf-8')
            elif response_data.getheader('Content-Type') and response_data.getheader('Content-Type').startswith('image/'):
                response_body = hashlib.md5(response_data.read()).hexdigest()
                print(response_body)
            else:
                response_body = str(response_data.read().decode('utf-8','replace'))
            
            result = {
                'Reason': response_data.reason,
                'ResponseBody': response_body,
                'StatusCode': response_data.status,
                'TimeTaken': int((t1 - t0) * 1000),
                'Available': '1'
            }

            if self.bodyregexmatch is not None:
                regex = re.compile(self.bodyregexmatch)
                value = 1 if regex.search(response_body) else 0
                result['ResponseBodyRegexMatch'] = value

            if self.statuscodematch is not None:
                result['StatusCodeMatch'] = int(int(response_data.status) == int(self.statuscodematch))
                if not result['StatusCodeMatch'] and self.fail_on_statuscode_mismatch:
                    result['Available'] = '0'

            # return structure with data
            return result
        except Exception as e:
            print(f"Failed to connect to {self.endpoint}\n{e}")
            return {'Available': 0, 'Reason': str(e)}


class ResultReporter:
    """Reporting results to CloudWatch"""

    def __init__(self, config, context):
        self.options = config.cwoptions
        self.endpoint = config.endpoint

    def report(self, result):
        if self.options['enabled'] == '1':
            try:
                cloudwatch = boto3.client('cloudwatch')
                metric_data = [{
                    'MetricName': 'Available',
                    'Dimensions': [
                        {'Name': 'Endpoint', 'Value': self.endpoint}
                    ],
                    'Unit': 'None',
                    'Value': int(result['Available'])
                }]
                if result['Available'] == '1':
                    metric_data.append({
                        'MetricName': 'TimeTaken',
                        'Dimensions': [
                            {'Name': 'Endpoint', 'Value': self.endpoint}
                        ],
                        'Unit': 'Milliseconds',
                        'Value': int(result['TimeTaken'])
                    })
                    metric_data.append({
                        'MetricName': 'StatusCode',
                        'Dimensions': [
                            {'Name': 'Endpoint', 'Value': self.endpoint}
                        ],
                        'Unit': 'None',
                        'Value': int(result['StatusCode'])
                    })
                    for additional_metric in ['ResponseBodyRegexMatch', 'StatusCodeMatch']:
                        if additional_metric in result:
                            metric_data.append({
                                'MetricName': additional_metric,
                                'Dimensions': [
                                    {'Name': 'Endpoint', 'Value': self.endpoint}
                                ],
                                'Unit': 'None',
                                'Value': int(result[additional_metric])
                            })

                result = cloudwatch.put_metric_data(
                    MetricData=metric_data,
                    Namespace=self.options['namespace']
                )
                print(f"Sent data to CloudWatch requestId=:{result['ResponseMetadata']['RequestId']}")
            except Exception as e:
                print(f"Failed to publish metrics to CloudWatch:{e}")


def http_check(event, context):
    """Lambda function handler"""

    config = Config(event)
    http_check = HttpCheck(config)

    result = http_check.execute()

    # report results
    ResultReporter(config, result).report(result)

    # Remove body if not required
    if (config.reportbody != '1') and ('ResponseBody' in result):
        del result['ResponseBody']

    result_json = json.dumps(result, indent=4)
    # log results
    print(f"Result of checking {config.method} {config.endpoint}\n{result_json}")

    # return to caller
    return result
