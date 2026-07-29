---
name: prod
description: Connect to the production EC2 box for cgovind.com and inspect it - shell in over SSH, read the shared SQLite database (TTR / ERS / King of Tokyo), tail service logs, restart services, or check nginx. Use whenever the user wants to look at prod, query the live database, debug a live game, or check on a running service.
---

# The production box

Everything at `cgovind.com` runs on **one Ubuntu EC2 instance** at the Elastic IP
`54.157.20.148`, user `ubuntu`.

## Connecting

A dedicated keypair for agent access lives at `~/.ssh/kot_prod`, with a `kotprod`
host alias already in `~/.ssh/config`. Just use:

```bash
ssh kotprod 'hostname; uptime'
```

Always run one-shot commands (`ssh kotprod '<cmd>'`) rather than opening an
interactive session - an interactive shell will hang waiting for input.

**If that fails with `Permission denied (publickey)`,** the key is not installed
(or the box was rebuilt). It cannot be self-served: the deploy key exists only as
the `EC2_SSH_KEY` GitHub secret, which `gh` cannot read back. Ask the user to SSH
in by their own means and run:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<contents of ~/.ssh/kot_prod.pub>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Regenerate the pair with `ssh-keygen -t ed25519 -f ~/.ssh/kot_prod -N ""` if it is
missing locally.

## What runs there

Four Flask apps behind nginx + certbot, each its own systemd service and port:

| Service        | Port | Directory                    | Serves                |
|----------------|------|------------------------------|-----------------------|
| `website`      | 5002 | `/home/ubuntu/website`       | `cgovind.com`, `www`  |
| `tickettoride` | 5001 | `/home/ubuntu/TicketToRide`  | `ttr.cgovind.com`     |
| `ers`          | 5003 | `/home/ubuntu/website/ers`   | `ers.cgovind.com`     |
| `kot`          | 5004 | `/home/ubuntu/website/kot`   | `kot.cgovind.com`     |

The games run `-w 1` eventlet gunicorn on purpose: socket rooms and in-flight
game state live in-process, so **a restart drops every live game**. Never restart
a game service casually - check for live games first (see below).

**The TTR gotcha:** the live Ticket to Ride is NOT this repo's `ttr/` submodule.
It is a separate clone at `/home/ubuntu/TicketToRide`, and its instance directory
holds the database everything else shares.

## The database

All four apps share **one SQLite file**:

```
/home/ubuntu/TicketToRide/instance/tickettoride.db
```

`users` is the shared account table. Each game keeps its own tables alongside it:
`ttr_*` (well, TTR still uses `users.elo` in prod), `ers_stats` / `ers_games` /
`ers_players` / `ers_slaps`, and `kot_stats` / `kot_games` / `kot_players`.

Confirm the path from the app's own config rather than trusting this file, since
it is set per-app in a gitignored `.env`:

```bash
ssh kotprod 'grep DATABASE_URL /home/ubuntu/website/kot/.env'
```

**Read it read-only.** It is a live database under WAL with four writers; open it
with `file:...?mode=ro` so a stray query can never take a write lock:

```bash
ssh kotprod 'sqlite3 "file:/home/ubuntu/TicketToRide/instance/tickettoride.db?mode=ro" ".tables"'
```

Useful starting points:

```bash
# schema of one table
ssh kotprod 'sqlite3 "file:/home/ubuntu/TicketToRide/instance/tickettoride.db?mode=ro" ".schema kot_games"'

# how much real play data exists
ssh kotprod 'sqlite3 "file:/home/ubuntu/TicketToRide/instance/tickettoride.db?mode=ro" \
  "SELECT status, COUNT(*) FROM kot_games GROUP BY status;"'

# any game currently live (check before restarting a service)
ssh kotprod 'sqlite3 "file:/home/ubuntu/TicketToRide/instance/tickettoride.db?mode=ro" \
  "SELECT code, last_activity_at FROM kot_games WHERE status='\''playing'\'';"'
```

Every finished game stores a full move-by-move replay in `events_json`
(`kot_games`, `ers_games`), which is the thing to pull for analysing real play.
For anything bigger than a couple of queries, copy the DB down instead of running
long queries against the live file:

```bash
scp kotprod:/home/ubuntu/TicketToRide/instance/tickettoride.db /tmp/prod-copy.db
```

Quoting nests badly over SSH. For any non-trivial SQL, write the query to a local
file and pipe it in: `ssh kotprod 'sqlite3 "file:...?mode=ro"' < query.sql`.

## Logs and services

```bash
ssh kotprod 'sudo systemctl status kot --no-pager'
ssh kotprod 'sudo journalctl -u kot -n 100 --no-pager'
ssh kotprod 'sudo journalctl -u kot -n 200 --no-pager | grep -i error'
```

Restarting drops live games, so confirm with the user first unless they already
asked for it:

```bash
ssh kotprod 'sudo systemctl restart kot'
```

## nginx and TLS

Configs are at `/etc/nginx/sites-available/{website,ers,kot}`, each a proxy to its
port with a WebSocket upgrade block for the game hosts, each with its own Let's
Encrypt cert (certbot auto-renews).

```bash
ssh kotprod 'sudo nginx -t && sudo systemctl reload nginx'
```

## What the deploy does not cover

The `Deploy` Action (see the `push` skill) only pulls `main`, installs
requirements, and restarts services. nginx, TLS, DNS (Route 53) and every `.env`
are **hand-managed on the box** and must be changed here over SSH. `.env` files
are gitignored and exist only on the box - never commit one, and never print a
`SECRET_KEY` into the transcript.
