CHECK=http-check
BUCKET=my-bucket
STACKNAME=http-check
AWSREGION=ap-southeast-2
COMMIT=$(shell git rev-parse --verify HEAD)

build-image:
	echo "docker image not required"

build:
	zip "${COMMIT}.zip" "handler.py"

test:
	echo "no python unit tests yet"
	
deploy:
	sam package --region ${AWSREGION} --template-file template.yaml --output-template-file packaged.yaml --s3-bucket ${BUCKET}
	sam deploy --region ${AWSREGION} --template-file packaged.yaml --stack-name ${STACKNAME}-${COMMIT} --capabilities CAPABILITY_IAM
	aws cloudformation wait stack-create-complete --region ${AWSREGION} --stack-name ${STACKNAME}-${COMMIT}
	
lambda-test:
	aws lambda invoke --function-name ${CHECK} --payload file://./test/ipify_statuscode_mistmatch.json lambda-test-1.json --log-type Tail --query 'LogResult' --output text | base64 -d
	aws lambda invoke --function-name ${CHECK} --payload file://./test/ipify.json lambda-test-2.json --log-type Tail --query 'LogResult' --output text | base64 -d
	aws lambda invoke --function-name ${CHECK} --payload file://./test/ipifyRegexFail.json lambda-test-3.json --log-type Tail --query 'LogResult' --output text | base64 -d
	aws lambda invoke --function-name ${CHECK} --payload file://./test/postRequest.json lambda-test-4.json --log-type Tail --query 'LogResult' --output text | base64 -d
	aws lambda invoke --function-name ${CHECK} --payload file://./test/compressed.json lambda-test-5.json --log-type Tail --query 'LogResult' --output text | base64 -d
	aws lambda invoke --function-name ${CHECK} --payload file://./test/image.json lambda-test-6.json --log-type Tail --query 'LogResult' --output text | base64 -d
	if grep -q "errorMessage" lambda-test-*.json; then echo "\nLambda tests failed"; exit 1; else echo "\nLambda tests passed";	fi

destroy:
	aws cloudformation delete-stack --region ${AWSREGION} --stack-name ${STACKNAME}-${COMMIT}