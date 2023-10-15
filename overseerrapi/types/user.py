import jsonobject


from .notification import NotificationTypes


class User(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id", required=True)
    email = jsonobject.StringProperty(name="email", required=True)
    username = jsonobject.StringProperty(name="username")
    plex_token = jsonobject.StringProperty(name="plexToken")
    plexUsername = jsonobject.StringProperty(name="plexUsername")
    user_type = jsonobject.IntegerProperty(name="userType")
    permissions = jsonobject.IntegerProperty(name="permissions")
    avatar = jsonobject.StringProperty(name="avatar")
    created_at = jsonobject.DateTimeProperty(name="createdAt")
    updated_at = jsonobject.DateTimeProperty(name="updatedAt")
    request_count = jsonobject.IntegerProperty(name="requestCount")

    # Only shown on direct user request
    settings = jsonobject.ObjectProperty(
        lambda: UserSettings, name="settings", exclude_if_none=True
    )


class UserSettings(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    locale = jsonobject.StringProperty(name="locale")
    region = jsonobject.StringProperty(name="region")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    pgp_key = jsonobject.StringProperty(name="pgpKey")
    discord_id = jsonobject.StringProperty(name="discordId")
    pushbullet_access_token = jsonobject.StringProperty(name="pushbulletAccessToken")
    pushbullet_application_token = jsonobject.StringProperty(
        name="pushbulletApplicationToken"
    )
    pushover_user_key = jsonobject.StringProperty(name="pushoverUserKey")
    telegram_chat_id = jsonobject.StringProperty(name="telegramChatId")
    telegram_send_silently = jsonobject.BooleanProperty(name="telegramSendSilently")
    watchlist_sync_movies = jsonobject.BooleanProperty(name="watchlistSyncMovies")
    watchlist_sync_tv = jsonobject.BooleanProperty(name="watchlistSyncTv")
    notification_types = jsonobject.ObjectProperty(
        lambda: NotificationTypes, name="notificationTypes"
    )
