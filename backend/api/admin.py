from django.contrib import admin

from .models import (
    ChatSession,
    Chunk,
    Document,
    Library,
    Message,
    Page,
    PlatformLedger,
    Profile,
    RetrievalLog,
    UsageLedger,
)

# The admin site is deliberately not installed. Supabase owns auth and there is
# no Django user model to log in with, so admin/ would be unreachable. See
# decisions.md D-004, where this is recorded as an accepted loss.
admin.site.register(
    [
        Profile,
        Library,
        Document,
        Page,
        Chunk,
        ChatSession,
        Message,
        UsageLedger,
        PlatformLedger,
        RetrievalLog,
    ]
)
