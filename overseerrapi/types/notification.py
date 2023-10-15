import jsonobject


class NotificationTypes(jsonobject.JsonObject):
    email = jsonobject.IntegerProperty(name="email")
    discord = jsonobject.IntegerProperty(name="discord")
    pushbullet = jsonobject.IntegerProperty(name="pushbullet")
    pushover = jsonobject.IntegerProperty(name="pushover")
    slack = jsonobject.IntegerProperty(name="slack")
    telegram = jsonobject.IntegerProperty(name="telegram")
    webhook = jsonobject.IntegerProperty(name="webhook")
    webpush = jsonobject.IntegerProperty(name="webpush")
