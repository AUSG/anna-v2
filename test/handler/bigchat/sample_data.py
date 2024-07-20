def create_sample_app_mention_event(msg):
    return {
        'client_msg_id': '8fb50d48-f93d-4cca-b9ca-6965479e9a93',
        'type': 'app_mention',
        'text': msg,
        'user': 'UQJ8HQJG5',
        'ts': '1689403771.805849',
        'blocks': [],  # not used and too long, so skipped
        'team': 'TQLEG4B38',
        'thread_ts': '1689403100.222939',
        'parent_user_id': 'UQJ8HQJG5',
        'channel': 'C03SZTDEDK3',
        'event_ts': '1689403771.805849'
    }


def create_sample_reaction_added_event(emoji_name):
    return {
        'type': 'reaction_added',
        'user': 'UQJ8HQJG5',
        'reaction': emoji_name,
        'item': {
            'type': 'message',
            'channel': 'C03SZTDEDK3',
            'ts': '1688801145.307229'
        },
        'item_user': "U01BN035Y6L",
        'event_ts': '1688833113.003600'
    }


def create_sample_reaction_removed_event(emoji_name):
    return {
        'type': 'reaction_removed',
        'user': 'UQJ8HQJG5',
        'reaction': emoji_name,
        'item': {
            'type': 'message',
            'channel': 'C03SZTDEDK3',
            'ts': '1688801145.307229'
        },
        'item_user': "U01BN035Y6L",
        'event_ts': '1688833113.003600'
    }


def create_sample_channel_created_event(channel_id):
    return {
        'type': 'channel_created',
        'channel': {
            'id': channel_id,
            'name': 'test-create-channel-2',
            'is_channel': True,
            'is_group': False,
            'is_im': False,
            'is_mpim': False,
            'is_private': False,
            'created': 1721484974,
            'is_archived': False,
            'is_general': False,
            'unlinked': 0,
            'name_normalized': 'test-create-channel-2',
            'is_shared': False,
            'is_frozen': False,
            'is_org_shared': False,
            'is_pending_ext_shared': False,
            'pending_shared': [],
            'context_team_id': 'TQLEG4B38',
            'updated': 1721484974161,
            'parent_conversation': None,
            'creator': 'UQJ8HQJG5',
            'is_ext_shared': False,
            'shared_team_ids': [
                'TQLEG4B38'
            ],
            'pending_connected_team_ids': [],
            'topic': {
                'value': '',
                'creator': '',
                'last_set': 0
            },
            'purpose': {
                'value': '',
                'creator': '',
                'last_set': 0
            },
            'previous_names': []
        },
        'event_ts': '1721484974.006000'
    }
