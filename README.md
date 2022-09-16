## 배포 과정 설명

로컬에서 직접 또는 Github Action를 통해 fly.io에 배포한다. 

fly.io 배포 방식은, k8s 의 pod 띄우기를 간소화했다고 보면 된다. 내가 로컬에서 `fly deploy` 명령어를 수행하면, Dockerfile로 이미지를 굽고, fly.toml 와 같이 fly.io 서버에 업로드한다. 

정확히 어느 서버에 배포하고 어느 포트를 개방하고 등등 정보는 다 fly.toml 에 있다.  

## 배포와 관련된 파일들

- .github/ : fly.io 에서 제공한 Github Action 을 트리거하는 workflow
- Dockerfile, .dockerignore, fly.toml : fly.io 배포할 때 사용

## 로컬 개발환경 구축
 
1. 파이썬 가상환경 생성 및 활성화, 깃헙 훅 활성화

```sh
python3 -m venv .venv # 가상환경 구축 (최초 1회)
source ./.venv/bin/activate # 가상환경 활성화
pip3 list # pip, setuptools 두 개만 나온다면 가상환경이 잘 세팅된 것

git config core.hooksPath .github/hooks # 깃헙 훅 활성화
```

2. 의존성 설치

```sh
pip3 install -r requirements.txt
pip3 list # 뭐가 많이 나온다면 잘 세팅된 것
```

작업 중 새로운 의존성이 추가된다면 아래와 같이 `requirements.txt`를 최신화하자.

```sh
pip3 freeze > requirements.txt
```

3. 환경변수 세팅

환경변수는 https://github.com/ausg/anna-v2-secret 에 넣어두었고, 루트 디렉토리의 `env` 디렉토리에 연동되어있다. 아래 명령어로 최신화하자.

```sh
git submodule update --init --recursive
```

4. 안나 깨우기

```sh
python3 src/anna.py
# INFO:slack_bolt.App:⚡️ Bolt app is running! 라는 메시지가 보이면 성공적으로 깨운 것이다.
```

5. 로컬에서 슬랙 이벤트 수신할 수 있도록 세팅

슬랙에선 따로 개발을 위한 테스트 콜백을 제공하지 않는다. 따라서 슬랙의 **실제** 이벤트를 로컬에서 수신받아서 검증해야된다. ~~super dog fooding~~

외부에서 내 로컬 컴퓨터로 요청을 쏠 수 있게 도와주는 도구가 많은데, 여기선 `ngrok` 예시를 들겠다.

```sh
brew install ngrok # 설치
ngrok http 8080 # 8080 포트 오픈
```

위 명령어 이후 나타나는 콘솔 화면에서 `Forwarding` 항목의 'xxx.ngrok.io'를 기억하자.

이후, [슬랙의 ANNA 설정 화면](https://api.slack.com/apps/AR4RK9XGX/event-subscriptions)에서`Request URL` 항목을 위에서 언급한 포워딩 URL 로 바꿔준다. 정확한 path 는 다음과 같다:

```text
만약 ngrok 에 나온 URL이 https://bee1-122-42-248-160.jp.ngrok.io 이라면, 
https://bee1-122-42-248-160.jp.ngrok.io/slack/events 을 입력해야 한다.
```

이 때 Step 4에서 안나를 미리 깨워두지 않았으면 에러 메시지가 나타날 것이다. 이는 url 을 바꿀 때 슬랙 측에서 정상적으로 이벤트 수신이 되는지 'challenge' 콜을 날리기 때문. 안나 콘솔과 ngrok 콘솔에서 관련 로그들을 확인할 수 있을 것이다.

반면에 성공적으로 "Verified" 메시지가 떴다면, 하단의 "Save Changes" 를 눌러 적용해주자.

6. 배포

코드를 main 브랜치에 올리면 fly.io 에 배포된다.

7. URL 원복

Step 5에서 세팅한 로컬 URL 을 다시 fly.io 서버의 것으로 바꿔두자. 현재는 아래 값이다.

```text
https://small-frost-842.fly.dev/slack/events
```

로컬에 [flyctl](https://fly.io/docs/hands-on/install-flyctl/)이 설치되어있고 로그인이 되어있다면 서버 주소도 정확히 알 수 있긴 하다.

## 환경변수 수정

anna-v2-secret 레포지토리에 커밋하시오.

## 코드 푸시 전 확인사항

충분히 테스트 코드를 추가해보자

## 참고문서

이벤트 콜백 data 스펙: https://api.slack.com/apis/connections/events-api#the-events-api__receiving-events__callback-field-overview