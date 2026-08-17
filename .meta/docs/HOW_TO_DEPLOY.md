# 배포 프로세스

fly.io 에 배포한다. fly.io 배포 방식은 k8s 의 pod 띄우기를 간소화했다고 보면 된다. `fly deploy` 를 수행하면 [Dockerfile](../deploy/Dockerfile) 로 이미지를 굽고 [fly.toml](../deploy/fly.toml) 과 같이 fly.io 서버에 업로드한다.

어느 서버에 배포하고 어느 포트를 개방하는지 등의 정보는 다 `fly.toml` 에 있다.

## 배포 과정

**main 브랜치에 머지하거나 푸시하면 자동으로 배포된다.** [deploy_with_fly.yml](../../.github/workflows/deploy_with_fly.yml) 액션이 `flyctl deploy --config .meta/deploy/fly.toml --dockerfile .meta/deploy/Dockerfile --remote-only` 를 실행한다.

로컬에서 직접 배포할 수도 있다. 이쪽은 배포 전에 `make ci` 가 먼저 돌아간다.

```sh
make deploy_local   # 내 컴퓨터에서 이미지를 굽는다
make deploy_remote  # fly.io 의 빌더에서 굽는다
```

## 환경변수 수정

https://github.com/AUSG/anna-v2-secret 레포지토리에 커밋하면 된다. `src/env` 서브모듈로 붙어 있어서, 배포 액션이 서브모듈을 체크아웃해 이미지에 담는다.
