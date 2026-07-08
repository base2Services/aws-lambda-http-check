# Lambda http check

Lambda function to check specific http endpoint, and report on it's availability.


Optionally, it can record metrics to CloudWatch.

## Inputs

All inputs are either defined as environment variables or as part of event data. Event data
will take priority over environment variables

`ENDPOINT` - url to be checked

`METHOD` - http method to use, defaults to `GET`

`PAYLOAD` - http payload, if `POST` or `PUT` used as method

`TIMEOUT` - timeout to use for http requests, defaults to 120s

`HEADERS` - list of _percentage sign (%)_ separated headers to send to target server, defaults to empty list.

`USER_AGENT` - If specified, will be added to the HEADERS. An example is: `Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Base2/Lambda`

`REPORT_RESPONSE_BODY` - set to 1 if you wish to report on response body, 0
otherwise, 0 otherwise, defaults to 0

`REPORT_AS_CW_METRICS` - set to 1 if you wish to store reported data as CW
custom metrics, 0 otherwise, defaults to 1

`CW_METRICS_NAMESPACE` - if CW custom metrics are being reported, this will determine
their namespace, defaults to 'HttpCheck'

`BODY_REGEX_MATCH` - if CW custom metrics are being reported, this will enable `ResponseBodyRegexMatch`
metric to be published as well, with value determined by success of matching response body against
regular expression contained within this option

`STATUS_CODE_MATCH` - report whether http status code is equal to given status code or not. If this option
is not present, it won't be reported upon. Defaults to empty

`FAIL_ON_STATUS_CODE_MISMATCH` - if checking for status code match treat mismatch as failure, ie report `Available: 0`

## HMAC Signed Requests

For endpoints that require HMAC authentication, the Lambda can dynamically compute and attach signed headers at request time. This supports replay-attack-resistant authentication schemes where each request requires a unique timestamp and nonce.

When `HMAC_SECRET_SSM` is set, the following headers are added to the request:

| Header | Description |
|---|---|
| `{prefix}-Signature` | HMAC-SHA256 hex digest of the canonical string |
| `{prefix}-Key-Id` | Key identifier |
| `{prefix}-Timestamp` | Unix epoch timestamp (seconds) |
| `{prefix}-Nonce` | Random UUID hex (prevents replay attacks) |

The canonical string signed is:

```
METHOD\nPATH\nTIMESTAMP\nNONCE\nQUERY\nBODY_HASH\nOVERRIDE_HEADER_HASH
```

Where:

- `BODY_HASH` is the SHA-256 hex digest of the request body (empty string hash for GET requests)
- `OVERRIDE_HEADER_HASH` is the SHA-256 hex digest of the raw `X-Health-Config-Overrides` header value when sent, otherwise the SHA-256 digest of an empty string (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`)

Set `X-Health-Config-Overrides` via the `HEADERS` input when you need request-scoped health check overrides. The override value must be included in the signature.

### HMAC Configuration

`HMAC_SECRET_SSM` - SSM Parameter Store path to the HMAC secret (SecureString). When set, HMAC signing is enabled. The Lambda execution role must have `ssm:GetParameter` permission for this parameter.

`HMAC_KEY_ID` - key identifier sent in the `{prefix}-Key-Id` header. Defaults to `default`.

`HMAC_HEADER_PREFIX` - prefix used for all HMAC header names. Defaults to `X-Health`, producing headers `X-Health-Signature`, `X-Health-Key-Id`, `X-Health-Timestamp`, and `X-Health-Nonce`.

### Example

```json
{
  "ENDPOINT": "https://api.example.com/health",
  "METHOD": "GET",
  "STATUS_CODE_MATCH": 200,
  "HMAC_SECRET_SSM": "/myapp/prod/HEALTH_HMAC_SECRET",
  "HMAC_KEY_ID": "default",
  "HMAC_HEADER_PREFIX": "X-Health"
}
```

With optional health check config overrides:

```json
{
  "ENDPOINT": "https://api.example.com/health",
  "METHOD": "GET",
  "STATUS_CODE_MATCH": 200,
  "HMAC_SECRET_SSM": "/myapp/prod/HEALTH_HMAC_SECRET",
  "HEADERS": "X-Health-Config-Overrides={\"roles\":{\"my_service\":{\"probes\":[{\"id\":\"my-probe\",\"enabled\":false}]}}}"
}
```

## Outputs

By default, following properties will be rendered in output Json

`Reason` - Reason

`Available` - 0 or 1

`TimeTaken` - Time in ms it took to get response from remote server. Default timeout
is 2 minutes for http requests.

`StatusCode` - Http Status Code

`ResponseBody` - Optional, by default this won't be reported

`ResponseBodyRegexMatch` - Optional, if `BODY_REGEX_MATCH` option is provided

`StatusCodeMatch` - Optional, if `STATUS_CODE_MATCH` options is provided

## Dependencies

Lambda function is having no external dependencies by design, so no additional packaging steps are required
for deploying it, such as doing `pip install [libname]`

## CloudWatch Metrics

In order to get some metrics which you can alert on, `REPORT_AS_CW_METRICS` and `CW_METRICS_NAMESPACE` environment
variables are used. Following metrics will be reported

- `Available` - 0 or 1, whether response was received in timely manner, indicating problems with network, DNS lookup or
server timeout

- `TimeTaken` - Time taken to fetch response, reported in milliseconds

- `StatusCode` - HTTP Status code received from server

- `ResponseBodyRegexMatch` - **optional** this will report 1 or 0 if `BODY_REGEX_MATCH` option is specified. 1 is reported
 if response body matches regex provided, or 0 otherwise. 

- `StatusCodeMatch` - **optional*& this will report 1 or 0 if `STATUS_CODE_MATCH` options is specified. 1 is reported
 if response status code matches code provided, or 0 otherwise

## Deployment

You can either deploy Lambda manually, or through [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/what-is-sam.html).
If the SAM CLI is being chosen as method of deployments use command below, while
making sure that you have [setup access](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-getting-started-set-up-credentials.html) to your AWS account.

build the lambda

```sh
sam build
```

deploy the template

```sh
sam deploy --guided
```

If you are setting up your Lambda function by hand, make sure it has proper IAM
permissions to push Cloud Watch metrics data, and to write to CloudWatch logs

## Testing

To test function locally with simple Google url (default), run following

```
sam local invoke Check
```

Optionally, for complicated example take a look at `test/ipify.json` file

```sh
sam local invoke Check --event test/ipify.json 
```

## Debugging

If you wish to see debug output for http request, set `HTTP_DEBUG` environment
variable to '1'. This can't be controlled through event payload. 

## Schedule execution 

Pull requests are welcome to serverless project to deploy CloudWatch rules in order
to schedule execution of Http Checking Lambda function.
