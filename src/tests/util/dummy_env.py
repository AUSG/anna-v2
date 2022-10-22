import os


def enable_dummy_envs():
    os.environ['GCP_type'] = 'xxx'
    os.environ['GCP_project_id'] = 'xxx'
    os.environ['GCP_private_key_id'] = 'xxx'
    os.environ['GCP_private_key'] = 'xxx'
    os.environ['GCP_client_email'] = 'xxx'
    os.environ['GCP_client_id'] = 'xxx'
    os.environ['GCP_auth_uri'] = 'xxx'
    os.environ['GCP_token_uri'] = 'xxx'
    os.environ['GCP_auth_provider_x509_cert_url'] = 'xxx'
    os.environ['GCP_client_x509_cert_url'] = 'xxx'
    os.environ['MEMBERS_INFO_WORKSHEET_ID'] = '1'
    os.environ['ANNOUNCEMENT_CHANNEL_ID'] = 'announcement_channel_id'
    os.environ['ANNA_ID'] = 'xxx'
    os.environ['SUBMIT_FORM_EMOJI'] = 'submit_form_emoji'
    os.environ['FORM_SPREADSHEET_ID'] = 'xxx'
    os.environ['SUSPEND_FORM_EMOJI'] = 'reject_form_emoji'
    os.environ['SLACK_BOT_TOKEN'] = 'token1234'
    os.environ['SLACK_SIGNING_SECRET'] = 'secret1234'