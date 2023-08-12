# 배포 프로세스

로컬에서 직접 또는 Github Action를 통해 fly.io에 배포한다.

fly.io 배포 방식은, k8s 의 pod 띄우기를 간소화했다고 보면 된다. 내가 로컬에서 `fly deploy` 명령어를 수행하면, Dockerfile로 이미지를 굽고, fly.toml 와 같이 fly.io 서버에 업로드한다.

정확히 어느 서버에 배포하고 어느 포트를 개방하고 등등 정보는 다 `fly.toml` 파일에 있다.

## 배포 과정

코드를 main 브랜치에 머지하거나 푸시하면 fly.io 에 배포된다. (`make deploy_remote` 사용)

로컬에서 직접 배포할 수도 있다. (`make deploy_local ` 사용)


## 환경변수 수정

https://github.com/AUSG/anna-v2-secret 레포지토리에 커밋하면 된다.
