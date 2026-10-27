"""빅챗 캘린더 다운로드 HTTP 진입점."""

from flask import Blueprint, Response, abort, request

from features.bigchat.models import CalendarFailure
from features.bigchat.presentation.calendar import to_ics
from features.bigchat.services.calendar import load_calendar_context
from runtime import Runtime


def create_blueprint(runtime: Runtime):
    blueprint = Blueprint("bigchat", __name__)

    @blueprint.get("/bigchat/<int:worksheet_id>/event.ics")
    def bigchat_ics(worksheet_id: int):
        token_secret = runtime.settings.ICS_TOKEN_SECRET
        if not token_secret:
            abort(404)
        args = request.args
        context = load_calendar_context(
            worksheet_id,
            args.get("channel", ""),
            args.get("ts", ""),
            args.get("token", ""),
            token_secret=token_secret,
            sheets=runtime.sheets(),
            slack=runtime.slack_client(runtime.web_client()),
        )
        if isinstance(context, CalendarFailure):
            abort(403 if context.reason == "denied" else 404)
        return Response(
            to_ics(
                context.event,
                uid=f"bigchat-{worksheet_id}@ausg-anna",
                description=context.description,
            ),
            mimetype="text/calendar",
            headers={"Content-Disposition": 'attachment; filename="event.ics"'},
        )

    return blueprint
