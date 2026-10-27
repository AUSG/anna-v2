"""빅챗 캘린더 다운로드 HTTP 진입점."""

from flask import Blueprint, Response, abort, request

from features.bigchat.models import CalendarAccessDenied, CalendarUnavailable
from features.bigchat.presentation.calendar import to_ics
from features.bigchat.services.calendar import load_calendar_context


def create_blueprint(dependencies):
    blueprint = Blueprint("bigchat", __name__)

    @blueprint.get("/bigchat/<int:worksheet_id>/event.ics")
    def bigchat_ics(worksheet_id: int):
        token_secret = dependencies.envs.ICS_TOKEN_SECRET
        if not token_secret:
            abort(404)
        args = request.args
        try:
            event, description = load_calendar_context(
                worksheet_id,
                args.get("channel", ""),
                args.get("ts", ""),
                args.get("token", ""),
                token_secret=token_secret,
                sheets_factory=dependencies.GoogleSpreadsheetClient,
                web_client_factory=dependencies.create_web_client,
            )
        except CalendarAccessDenied:
            abort(403)
        except CalendarUnavailable:
            abort(404)
        return Response(
            to_ics(
                event, uid=f"bigchat-{worksheet_id}@ausg-anna", description=description
            ),
            mimetype="text/calendar",
            headers={"Content-Disposition": 'attachment; filename="event.ics"'},
        )

    return blueprint
