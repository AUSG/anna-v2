"""HTTP 입력 검증과 응답. 외부 조회는 주입받은 기능 서비스에 맡긴다."""

from flask import Response, abort, request

from config.env_config import Settings
from features.bigchat.calendar import calendar_payload, to_ics, verify_calendar_token
from features.bigchat.services.calendar import BigchatCalendar, CalendarNotFound


def register_http_routes(
    app, slack_request_handler, calendar: BigchatCalendar, settings: Settings
):
    @app.route("/slack/events", methods=["POST"])
    def slack_events():
        return slack_request_handler.handle(request)

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}

    @app.route("/bigchat/<int:worksheet_id>/event.ics", methods=["GET"])
    def bigchat_ics(worksheet_id: int):
        # 비활성화·인증 실패는 외부 클라이언트를 생성하기 전에 처리한다.
        if not settings.ICS_TOKEN_SECRET:
            abort(404)
        channel = request.args.get("channel", "")
        ts = request.args.get("ts", "")
        if not verify_calendar_token(
            settings.ICS_TOKEN_SECRET,
            calendar_payload(worksheet_id, channel, ts),
            request.args.get("token", ""),
        ):
            abort(403)

        try:
            event, description = calendar.load(worksheet_id, channel, ts)
        except CalendarNotFound:
            abort(404)

        return Response(
            to_ics(
                event, uid=f"bigchat-{worksheet_id}@ausg-anna", description=description
            ),
            mimetype="text/calendar",
            headers={"Content-Disposition": 'attachment; filename="event.ics"'},
        )
