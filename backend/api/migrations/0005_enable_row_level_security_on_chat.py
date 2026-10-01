from django.db import migrations

from api.migration_ops import EnableRowLevelSecurity


class Migration(migrations.Migration):
    """Enable RLS on the chat tables, which 0003 could not.

    0003 enables RLS on the tables that existed when it was written. The chat
    tables were created afterwards by 0004, and a separate migration is the
    honest way to cover them: 0003 cannot list tables that do not exist yet,
    and making `EnableRowLevelSecurity` ignore missing tables would let a
    misspelled table name pass silently — which is the exact failure RLS is
    here to prevent.
    """

    dependencies = [
        ("api", "0004_chatsession_chatmessage_and_more"),
    ]

    operations = [
        EnableRowLevelSecurity(["chat_sessions", "chat_messages"]),
    ]
