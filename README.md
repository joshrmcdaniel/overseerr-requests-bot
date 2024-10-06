# Overseerr Requests bot

discord bot for managing requests in overseerr. partly abandoned, only updating stuff breaks (for me) or i need a new feature 

**This is a WIP. Functionality is not complete, and error handling is not properly set**
Current features
- Searching overseerr and requesting from an item

# Known issues
- ~~Pagination is not implemented, will error out after 20 results.~~
- View code could be better

# TODO
- ~~add requests embed~~
- error handling
- add better logging on the api module (better-ish)
- Replace the view mess with pages and page groups (or something better)

## Usage

- clone project
- create a .env with the following:

```ini
OVERSEERR_URL=http://your.overseerr.url
OVERSEERR_USER=overseerrrbot  # use your own creds. i created a service bot, admin accounts will have their requests auto approved
OVERSEERR_PASS=overrseerrpass # use your own creds. i created a service bot, admin accounts will have their requests auto approved
OVERSEERR_API_KEY=overseerr-api-key # replace with yours
```

> i use the user pass and api key for refreshing credentials; gets annoying to restart the prog every week

- assuming youre running on a remote instance, either run the python program in tmux and detach or utilize the systemd file (instructions found in the [systemd file](overseerrbot.service#L3-L10))