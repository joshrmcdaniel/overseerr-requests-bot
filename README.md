# Overseerr Requests bot

discord bot for managing requests in overseerr/seerr. partly abandoned, only updating when stuff breaks (for me) or i need a new feature.

still a WIP. the view code and error handling could use some work.


## Current features

- search for movies/tv and request them through discord
- approve or deny requests
- auto approve requests while the user is under their storage quota
- let users remove old downloads to free up their quota

## Known issues

- View code could be better

## TODO

- error handling
- better logging in the api module (better-ish)
- replace the view mess with pages and page groups (or something better)


## Usage

clone the project, create a venv, and install `requirements.txt`. use python 3.12 or 3.13.

create a `.env`:

```ini
GUILD_ID=123456789 # discord server the bot lives in
DISCORD_TOKEN=bot-token # replace with yours
OVERSEERR_URL=http://your.seerr.url/api/v1 # include /api/v1
OVERSEERR_API_KEY=seerr-api-key # replace with yours

# LOG_LEVEL=DEBUG # usually dont need this
```

link your discord ID in seerr's user settings. give users the `Requester` role to use `/search`, and `Approver` for `/requests`.

activate the venv and run `python main.py`. if youre running remotely, tmux works, or use the [systemd file](overseerrbot.service).

## docker

use the same `.env` as above:

```sh
docker run -d \
  --name overseerr-requests-bot \
  --restart unless-stopped \
  --env-file .env \
  --volume overseerr-bot-data:/data \
  ghcr.io/joshrmcdaniel/overseerr-requests-bot:latest
```

or build it locally:

```sh
docker build -t overseerr-requests-bot:local .
```

## storage quota

500 GB per seerr user by default, across movies, tv, and standard/4K libraries. multiple discord IDs linked to the same user share it. this is downloaded storage, so it doesnt reset monthly. GB here is decimal, not GiB.

the bot gets radarr/sonarr addresses and api keys from seerr. it needs to reach them directly. turn on **Tag Requests** in seerr's radarr/sonarr settings; the `UID-Username` tags tell the bot who requested things. it also uses seerr's request history to match users and tv seasons. renaming a user doesnt reset their quota.

**turn off Admin, Manage Requests, and Auto-Approve in seerr for users you want the bot's quota to control.** seerr otherwise approves their requests before the bot gets to check. manual approvals also bypass this check.

requests that fit get approved. requests that dont stay pending, with **Manage storage** and **Retry approval** buttons.

### freeing up space

use `/quota` to see downloaded, reserved, and remaining space.

- select a movie or tv season, then **Delete files**. this actually deletes the files and stops monitoring that movie/season
- shared titles need to be handled by the owner. active downloads have to finish first. shared files count against each attributed user
- tv removal only deletes the selected season. radarr/sonarr recycle-bin settings still apply
- seerr keeps the request history and updates availability on its normal scans

if you opened this from a pending request, the bot retries its approval after removal. otherwise, use `/quota` → **Pending requests** to retry an existing request.

### keeping something a user added

use `/quota-user user:@member`, admin only. admin doesnt need a linked seerr account, member does.

you get a list of individual titles showing **Counts toward quota** or **Kept outside quota**.

- select a movie → **Keep this movie**. its files stay, and only that movie stops counting against that user's quota
- for tv, use **Keep this season**, or **Keep whole show** if you want all their seasons of that show on that server. these include future episodes/seasons
- to undo it, select the kept title → **Count this movie**, **Count this season**, or **Count whole show**

the list filters just change what you see. they dont apply anything to the whole library.

kept titles also stop reserving quota for downloads. their tags, monitoring, and request history stay as they were, and the bot blocks users from deleting them. other users still get charged for shared titles. restoring a charge doesnt remove protection if another user's keep setting still covers it.

this frees up the user's allowance, not actual disk space. seerr's own request-count limits still apply.

### quota settings

these are optional. defaults:

```ini
AUTO_APPROVE_QUOTA_GB=500
QUOTA_RESERVE_DOWNLOADS=true
QUOTA_MOVIE_ESTIMATE_GB=20
QUOTA_EPISODE_ESTIMATE_GB=2
QUOTA_4K_MOVIE_ESTIMATE_GB=80
QUOTA_4K_EPISODE_ESTIMATE_GB=8
```

reservations estimate queued downloads so someone cant spend the same free space on a bunch of requests. movie estimates are per movie; tv estimates are per missing episode. actual file sizes replace them as downloads finish.

set `QUOTA_RESERVE_DOWNLOADS=false` to only check files already downloaded. that allows more requests while downloads are still queued. `AUTO_APPROVE_QUOTA_GB=0` disables quota auto-approval and the quota commands.

bigger downloads, quality upgrades, and future episodes can put someone over the limit. the bot wont automatically delete their stuff.

if the addresses in seerr arent reachable from the bot, override them using the service type and seerr server ID. include any proxy base path, but leave off `/api/v3`:

```ini
QUOTA_SERVER_URLS={"radarr:0":"http://radarr:7878","sonarr:0":"http://sonarr:8989"}
```

run one bot instance. quota state lives in `.data/quota.sqlite3`, or `/data/quota.sqlite3` in docker. `QUOTA_STATE_FILE` overrides it. keep this file across restarts; it remembers admin keep settings, removed items, and approvals that couldnt be confirmed.

if a server is down or the bot cant read a size, the request stays pending. if approval times out, check the existing request in seerr. its reservation stays until a later check confirms it was approved, declined, or deleted.

