from slack_bolt import App

from config.env_config import envs
from config.log_config import init_logger, get_logger
from handler.bigchat import attend_bigchat, abandon_bigchat

init_logger()
app = App(token=envs.SLACK_BOT_TOKEN, signing_secret=envs.SLACK_SIGNING_SECRET)


@app.event("reaction_added")
def handle_reaction_added_event(ack, event, say, client):
    ack()
    attend_bigchat(event, say, client)


@app.event("reaction_removed")
def handle_reaction_removed_event(ack, event, say, client):
    ack()
    abandon_bigchat(event, say, client)


@app.event("message")
def handle_message_events(ack, event, say, client):
    ack()


get_logger().info("All listeners are registered")

if __name__ == "__main__":
    PORT = 8080
    get_logger().info("Anna wakes up at room %d", PORT)
    app.start(PORT)
