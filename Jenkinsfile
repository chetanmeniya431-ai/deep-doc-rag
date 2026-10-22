// CI/CD for DeepDoc RAG.
// Jenkins needs: Docker on the agent, and an SSH credential "vps-deploy" for the server.
// Set DEPLOY_HOST (user@host) and DEPLOY_PATH (repo folder on the server) as job
// parameters or global environment variables.
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }

    parameters {
        string(name: 'DEPLOY_HOST', defaultValue: '', description: 'SSH target, e.g. deploy@203.0.113.10')
        string(name: 'DEPLOY_PATH', defaultValue: '/srv/deep-doc-rag', description: 'Repo folder on the server')
        string(name: 'HEALTH_URL', defaultValue: 'https://deepdoc.nirmantra.com/health', description: 'Checked after deploy')
    }

    stages {
        stage('Build image') {
            steps {
                sh 'docker build -f docker/Dockerfile -t deep-doc-rag:${GIT_COMMIT} .'
            }
        }

        stage('Test') {
            steps {
                // Fast tests only: no models, no index, capped at 1 GB.
                sh '''
                    docker run --rm -m 1g -e DATA_DIR=/tmp/data --entrypoint sh deep-doc-rag:${GIT_COMMIT} -c \
                        "python -m pytest -q"
                '''
            }
        }

        stage('Deploy') {
            when { branch 'main' }
            steps {
                sshagent(credentials: ['vps-deploy']) {
                    sh '''
                        test -n "$DEPLOY_HOST" || { echo "DEPLOY_HOST is not set"; exit 1; }
                        ssh -o StrictHostKeyChecking=accept-new "$DEPLOY_HOST" "
                            set -e
                            cd '$DEPLOY_PATH'
                            git fetch --quiet origin main
                            git reset --hard origin/main
                            docker compose up -d --build  # compose files come from COMPOSE_FILE in the server .env
                            docker image prune -f
                        "
                    '''
                }
            }
        }

        stage('Health check') {
            when { branch 'main' }
            steps {
                retry(10) {
                    sleep(time: 6, unit: 'SECONDS')
                    sh 'curl -fsS "$HEALTH_URL"'
                }
            }
        }
    }

    post {
        always { sh 'docker image rm deep-doc-rag:${GIT_COMMIT} || true' }
    }
}
