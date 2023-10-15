import jsonobject


class PlexLibrary(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id", required=True)
    name = jsonobject.StringProperty(name="name", required=True)
    enabled = jsonobject.BooleanProperty(name="enabled", required=True)


class PlexSettings(jsonobject.JsonObject):
    name = jsonobject.StringProperty(name="name", required=True)
    machine_id = jsonobject.StringProperty(name="machineId", required=True)
    ip = jsonobject.StringProperty(name="ip", required=True)
    port = jsonobject.IntegerProperty(name="port", required=True)
    use_ssl = jsonobject.BooleanProperty(name="useSsl")
    libraries = jsonobject.ListProperty(lambda: PlexLibrary, name="libraries")
    web_app_url = jsonobject.StringProperty(name="webAppUrl")


class PlexConnection(jsonobject.JsonObject):
    protocol = jsonobject.StringProperty(name="protocol", required=True)
    address = jsonobject.StringProperty(name="address", required=True)
    port = jsonobject.IntegerProperty(name="port", required=True)
    uri = jsonobject.StringProperty(name="uri", required=True)
    local = jsonobject.BooleanProperty(name="local", required=True)
    status = jsonobject.IntegerProperty(name="status")
    message = jsonobject.StringProperty(name="message")


class PlexDevice(jsonobject.JsonObject):
    name = jsonobject.StringProperty(name="name", required=True)
    product = jsonobject.StringProperty(name="product", required=True)
    product_version = jsonobject.StringProperty(name="productVersion", required=True)
    platform = jsonobject.StringProperty(name="platform", required=True)
    platform_version = jsonobject.StringProperty(name="platformVersion")
    device = jsonobject.StringProperty(name="device", required=True)
    client_identifier = jsonobject.StringProperty(
        name="clientIdentifier", required=True
    )
    created_at = jsonobject.DateTimeProperty(name="createdAt", required=True)
    last_seen_at = jsonobject.DateTimeProperty(name="lastSeenAt", required=True)
    provides = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="provides", required=True
    )
    owned = jsonobject.BooleanProperty(name="owned", required=True)
    owner_id = jsonobject.StringProperty(name="ownerId")
    home = jsonobject.BooleanProperty(name="home")
    source_title = jsonobject.StringProperty(name="sourceTitle")
    access_token = jsonobject.StringProperty(name="accessToken")
    public_address = jsonobject.StringProperty(name="publicAddress")
    https_required = jsonobject.BooleanProperty(name="httpsRequired")
    synced = jsonobject.BooleanProperty(name="synced")
    relay = jsonobject.BooleanProperty(name="relay")
    dns_rebinding_protection = jsonobject.BooleanProperty(name="dnsRebindingProtection")
    nat_loopback_supported = jsonobject.BooleanProperty(name="natLoopbackSupported")
    public_address_matches = jsonobject.BooleanProperty(name="publicAddressMatches")
    presence = jsonobject.BooleanProperty(name="presence")
    connection = jsonobject.ListProperty(lambda: PlexConnection, name="connection")
