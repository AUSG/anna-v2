## 배포 과정 설명

로컬에서 직접 또는 Github Action를 통해 fly.io에 배포한다. 

fly.io 배포 방식은, k8s 의 pod 띄우기를 간소화했다고 보면 된다. 내가 로컬에서 `fly deploy` 명령어를 수행하면, Dockerfile로 이미지를 굽고, fly.toml 와 같이 fly.io 서버에 업로드한다. 

정확히 어느 서버에 배포하고 어느 포트를 개방하고 등등 정보는 다 fly.toml 에 있다.  

## 배포와 관련된 파일들

- .github/ : fly.io 에서 제공한 Github Action 을 트리거하는 workflow
- Dockerfile, .dockerignore, fly.toml : fly.io 배포할 때 사용

## 로컬 개발환경 구축
 
1. 파이썬 가상환경 생성 및 활성화

```sh
python3 -m venv .venv # 가상환경 구축 (최초 1회)
source ./.venv/bin/activate # 가상환경 활성화
pip3 list # pip, setuptools 두 개만 나온다면 가상환경이 잘 세팅된 것
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

2. 필수파일 세팅 (아래 참고)
3. git push --> deploy



# 필수파일

## 1. `gcp_serviceaccount_secret.json` 파일이 루트 디렉토리에 존재해야 함

해당 파일은 gcp - service account 를 생성한 후 해당 계정에 Key 를 추가함으로써 다운받을 수 있으며, 아래와 같이 생겼음:

```json
{
  "type": "service_account",
  "project_id": "ausg-anna",
  "private_key_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "private_key": "-----BEGIN PRIVATE KEY-----\characters_more_then_1000\n-----END PRIVATE KEY-----\n",
  "client_email": "service_account_email",
  "client_id": "xxxxxxxxxxxxxxxxxxxxx",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "url"
}
```

## 2. `.env` 파일이 루트 디렉토리에 존재해야 함

대략 아래와 같음

```text
## slack_bolt 관련
SLACK_SIGNING_SECRET=XXXXXXXXXXXX
SLACK_BOT_TOKEN=xoxb-XXXXXXXXXXXXXXXXXXXX

## 서비스 관련
# ANNA 관리 채널
ADMIN_CHANNEL=C03SZTDEDK3
# 'announcement' 채널의 id
ANNOUNCEMENT_CHANNEL_ID=CQJ9S88M6
# ANNA 의 slack_unique_id
ANNA_ID=U01BN035Y6L
# 신청서 제출에 사용되는 이모지 이름
SUBMIT_FORM_EMOJI=gogo
# 신청서 제출에 사용되는 구글스프레드 id ('AUSG_오프라인_모임_참가신청서')
FORM_SPREADSHEET_ID=1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k
# 위 구글스프레드 내에서 멤버들 정보가 있는 워크시트 id ('AUSG_오프라인_모임_참가신청서')
MEMBERS_INFO_WORKSHEET_ID=307140510
```

## 커밋 전 확인사항

TBD

## 참고문서

이벤트 콜백 data 스펙: https://api.slack.com/apis/connections/events-api#the-events-api__receiving-events__callback-field-overview