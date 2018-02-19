import json
import os
import http.client
import boto3
from time import perf_counter as pc
from urllib.parse import urlparse
import ssl

import re


class Config:
    """Lambda function runtime configuration"""

    ENDPOINT = 'ENDPOINT'
    METHOD = 'METHOD'
    PAYLOAD = 'PAYLOAD'
    TIMEOUT = 'TIMEOUT'
    HEADERS = 'HEADERS'
    REPORT_RESPONSE_BODY = 'REPORT_RESPONSE_BODY'
    REPORT_AS_CW_METRICS = 'REPORT_AS_CW_METRICS'
    CW_METRICS_NAMESPACE = 'CW_METRICS_NAMESPACE'
    CW_METRICS_METRIC_NAME = 'CW_METRICS_METRIC_NAME'
    BODY_REGEX_MATCH = 'BODY_REGEX_MATCH'
    STATUS_CODE_MATCH = 'STATUS_CODE_MATCH'
    FAIL_ON_STATUS_CODE_MISMATCH = 'FAIL_ON_STATUS_CODE_MISMATCH'

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
            self.HEADERS: '',
            self.BODY_REGEX_MATCH: None,
            self.STATUS_CODE_MATCH: None,
            self.FAIL_ON_STATUS_CODE_MISMATCH: None
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
        headers = self.__get_property(self.HEADERS)
        if headers == '':
            return {}
        else:
            try:
                return dict(u.split("=") for u in headers.split(' '))
            except:
                print(f"Could not decode headers: {headers}")

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
    def cwoptions(self):
        return {
            'enabled': self.__get_property(self.REPORT_AS_CW_METRICS),
            'namespace': self.__get_property(self.CW_METRICS_NAMESPACE),
        }


class HttpCheck:
    """Execution of HTTP(s) request"""

    def __init__(self, config):
        self.method = config.method
        self.endpoint = config.endpoint
        self.timeout = config.timeout
        self.payload = config.payload
        self.headers = config.headers
        self.bodyregexmatch = config.bodyregexmatch
        self.statuscodematch = config.statuscodematch
        self.fail_on_statuscode_mismatch = config.fail_on_statuscode_mismatch

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

        try:
            t0 = pc()

            # perform request
            request.request(self.method, path, self.payload, self.headers)
            # read response
            response_data = request.getresponse()

            # stop the stopwatch
            t1 = pc()

            response_body = str(response_data.read().decode())
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
