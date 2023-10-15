import jsonobject


class MainSettings(jsonobject.JsonObject):
    api_key = jsonobject.StringProperty(name="apiKey")
    app_language = jsonobject.StringProperty(name="appLanguage")
    application_title = jsonobject.StringProperty(name="applicationTitle")
    application_url = jsonobject.StringProperty(name="applicationUrl")
    trust_proxy = jsonobject.BooleanProperty(name="trustProxy")
    csrf_protection = jsonobject.BooleanProperty(name="csrfProtection")
    hide_available = jsonobject.BooleanProperty(name="hideAvailable")
    partial_requests_enabled = jsonobject.BooleanProperty(name="partialRequestsEnabled")
    local_login = jsonobject.BooleanProperty(name="localLogin")
    new_plex_login = jsonobject.BooleanProperty(name="newPlexLogin")
    default_permissions = jsonobject.IntegerProperty(name="defaultPermissions")
