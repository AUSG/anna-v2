# AUSG Notoriously Nerdy Assistant

![anna screenshot](.meta/docs/images/anna_screenshot.png)

# 기본적인 개발환경 구축하기

```sh
make setup_local_env
```

# 실제 AUSG 슬랙과 로컬의 안나를 연동해서 테스트하기

1. 안나 깨우기

```sh
make run_local
```

2. 로컬에서 슬랙 이벤트를 수신할 수 있도록 포트 개방

슬랙에선 따로 개발을 위한 테스트 콜백을 제공하지 않는다. 따라서 슬랙의 **실제** 이벤트를 로컬에서 수신받아서 검증해야된다. ~~super dog fooding~~ 이 작업 도중엔 슬랙에서 안나가 졸게 되므로 (작동하지 않으므로) 미리 슬랙에서 다른 분들에게 공지해두는게 좋다.

외부에서 내 로컬 컴퓨터로 요청을 쏠 수 있게 도와주는 도구가 많은데, 여기선 `tunnelmole` 을 사용한다.

> 왜인지는 모르겠지만, ngrok 을 쓰면 슬랙의 검증 API 가 정상적으로 들어오지 않는다.

```sh
make open_port
```

> 💡 아래 작업을 하기 전 미리 경고: URL 값을 바꾸기 전 기존 값을 따로 저장해 둘 것.

이후, [슬랙 - ANNA 설정](https://api.slack.com/apps/AR4RK9XGX/event-subscriptions)에서 `Request URL` 항목을 위 명령어 결과로 나온 https 주소로 바꿔준다. 그냥 URL 만 입력하면 안되고, `/slack/events`를 붙여줘야 한다[^1]. 성공적으로 "Verified" 메시지가 떴다면, 하단의 "Save Changes" 를 눌러 적용해주자.

[^1]: 예를 들어 포워딩 URL이 https://a.b.dev 라면, https://a.b.dev/slack/events 을 입력해야 한다.

3. 뒷정리 (URL 원복)

로컬 테스트가 끝났다면 위에서 세팅한 로컬 URL을 기존 값으로 바꿔두자. 현재는 `https://anna-v2-2023.fly.dev/slack/events` 이다.

# 배포 방법

see [HOW_TO_DEPLOY.md](.meta/develop/HOW_TO_DEPLOY.md).

# Misc

## 참고자료

이벤트 콜백 data 스펙: https://api.slack.com/apis/connections/events-api#the-events-api__receiving-events__callback-field-overview
