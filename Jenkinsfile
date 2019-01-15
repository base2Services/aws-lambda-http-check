
pipeline {
  environment {
    VERSION = '0.1'
    BUCKET_NAME_PREFIX = 'base2.lambda.'
    PROJECT = 'aws-lambda-http-check'
    HANDLER = 'handler.zip'
  }

  agent {
    node {
      label 'docker'
    }
  }

  stages {

    stage('Package Python script') {
      steps {
        sh "zip ${env.HANDLER} handler.py"
      }
    }

    stage('Deploy to S3 buckets') {
      steps {
        script {
          def output = sh (script: 'aws ec2 describe-regions --query "Regions[*].RegionName" --output text | tr "\t" "\n" | sort', returnStdout: true)
          echo "Current regions:\n${output}"

          def regions = output.split()

          regions.each { region ->
            // For each region, try to deploy the binary. If the bucket doesn't exist, create it and make it pubicly readable.
            def bucket = env.BUCKET_NAME_PREFIX + region
            def response = sh (script: "aws s3api head-bucket --bucket ${bucket} --region ${region} 2>&1 || exit 0", returnStdout: true)

            if (response.contains("Not Found")) {
              echo "Creating S3 bucket as it does not exist: ${bucket} ..."
              createPolicy(bucket)
              sh "aws s3api create-bucket --bucket ${bucket} --create-bucket-configuration LocationConstraint=${region} --region ${region}"
              sh "aws s3api put-bucket-policy --bucket ${bucket} --policy file://s3-policy.json --region ${region}"
            }

            echo "Copying binary to S3 bucket: s3://${bucket}/${env.PROJECT}/${env.VERSION}/${env.HANDLER} ..."
            sh "aws s3 cp ${env.HANDLER} s3://${bucket}/${env.PROJECT}/${env.VERSION}/${env.HANDLER} --region ${region}"
          }
        }
      }
    }
  }
}


def createPolicy(bucket) {
  sh """/bin/bash
  tee s3-policy.json <<EOF
{
  "Id": "Policy2397633521930",
  "Statement": [
    {
      "Sid": "Stmt2397633521930",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:s3:::${bucket}",
        "arn:aws:s3:::${bucket}/*"
      ],
      "Principal": {
        "AWS": [
          "*"
        ]
      }
    }
  ]
}
EOF
  """
}
