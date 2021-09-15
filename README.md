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

`COMPRESSED` - Request a compressed response using gzip un decompresses the response to text

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

## Images

The http check function can work with images. It downloads the image and stores the response a md5 hash. This allows the ability to set `BODY_REGEX_MATCH` with the expected md5 value.

## Dependencies

Lambda function is having no external dependencies by design, so no additional packaging steps are required
for deploying it, such as doing `pip install [libname]`. The requirements.txt file is there a placeholder for
AWS SAM testing.

## CloudWatch Metrics

In order to get some metrics which you can alert on, `REPORT_AS_CW_METRICS` and `CW_METRICS_NAMESPACE` environment
variables are used. Following metrics will be reported

- `Available` - 0 or 1, whether response was received in timely manner, indicating problems with network, DNS lookup or
server timeout

- `TimeTaken` - Time taken to fetch response, reported in milliseconds

- `StatusCode` - HTTP Status code received from server

- `ResponseBodyRegexMatch` - **optional** this will report 1 or 0 if `BODY_REGEX_MATCH` option is specified. 1 is reported
 if response body matches regex provided, or 0 otherwise. 

- `StatusCodeMatch` - **optional** this will report 1 or 0 if `STATUS_CODE_MATCH` options is specified. 1 is reported
 if response status code matches code provided, or 0 otherwise

## Deployment

You can either deploy Lambda manually, through [serverless](serverless.com) project or using [AWS SAM](https://aws.amazon.com/serverless/sam/).

### Serverless

If serverless is being chosen as method of deployments use command below, while
making sure that you have setup proper access keys. For more information [read here](https://serverless.com/framework/docs/providers/aws/guide/workflow/)

Serverless framework version used during development
is `1.23.0`, but it is very likely that later versions
will function as well

```
sls deploy
```

If you are setting up your Lambda function by hand, make sure it has proper IAM
permissions to push Cloud Watch metrics data, and to write to CloudWatch logs

### AWS SAM

Make sure you have set up your AWS credentials in your environment and an available s3 bucket in the same region.

```sh
sam package --template-file template.yaml --output-template-file packaged.yaml --s3-bucket ${BUCKET}
sam deploy --template-file packaged.yaml --stack-name http-check --capabilities CAPABILITY_IAM
```

## Testing


### Serverless

To test function locally with simple Google url (default), run following

```
sls invoke local  -f httpcheck
```

Optionally, for complicated example take a look at `test/ipify.json` file

```
$ sls invoke local  -f httpcheck -p test/ipify.json 
Failed to connect to https://api.ipify.org?format=json
<urlopen error _ssl.c:732: The handshake operation timed out>
Failed to publish metrics to CloudWatch:'TimeTaken'
Result of checking https://api.ipify.org?format=json
{
 "Available": 0,
 "Reason": "<urlopen error _ssl.c:732: The handshake operation timed out>"
}
{
    "Available": 0,
    "Reason": "<urlopen error _ssl.c:732: The handshake operation timed out>"
}
```

### AWS SAM

build the code change

```
sam build
```

execute the test

```sh
sam local invoke Check --event test/ipify.json 
```

## Debugging

If you wish to see debug output for http request, set `HTTP_DEBUG` environment
variable to '1'. This can't be controlled through event payload. 

## Schedule execution 

Pull requests are welcome to serverless project to deploy CloudWatch rules in order
to schedule execution of Http Checking Lambda function.
