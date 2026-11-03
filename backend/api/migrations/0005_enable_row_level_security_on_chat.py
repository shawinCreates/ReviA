from django.db import migrations

from api.migration_ops import EnableRowLevelSecurity


class Migration(migrations.Migration):
    """Enable RLS on the chat tables, which 0003 could not cover."""

    dependencies = [
        ("api", "0004_chatsession_chatmessage_and_more"),
    ]

    operations = [
        EnableRowLevelSecurity(["chat_sessions", "chat_messages"]),
    ]
