@Library('ciinabox') _

pipeline {
  environment {
    PROJECT = 'aws-lambda-http-check'
    HANDLER = 'handler.zip'
    NOW = new Date().format('yyyyMMdd')
    BRANCH = env.BRANCH_NAME.replace('/', '-')
    VERSION = "${env.BUILD_NUMBER}-${env.NOW}-${env.GIT_COMMIT.substring(0,7)}-${env.BRANCH}"
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
        echo "Uploading package to S3 buckets"

        uploadLambdaToBuckets(
          bucket: 'base2.lambda.${region}',
          key: env.PROJECT + '/' + env.VERSION,
          regions: '*',
          file: env.HANDLER,
          createBucket: true,
          publicBucket: true
        )
      }
    }
  }
}
