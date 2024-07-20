class AnnounceNewChannelCreated:
    def __init__(self, event, slack_client):
        self.channel_id = event["channel"]["id"]
        self.slack_client = slack_client

    def run(self):
        self.slack_client.send_message_to_freetalk(msg=f'새로운 채널이 만들어졌어! <#{self.channel_id}>')
        return True
