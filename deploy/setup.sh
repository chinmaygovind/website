#!/usr/bin/env bash
# One-time setup for the website on an Ubuntu EC2 box. Run from the repo root:
#   git clone --recurse-submodules <repo> ~/website && cd ~/website && sh deploy/setup.sh
# Re-runnable. Tested on Ubuntu 22.04 LTS.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$APP_DIR/venv"
RUN_USER="$(whoami)"

echo "==> App directory : $APP_DIR"
echo "==> Running as    : $RUN_USER"

# ── System packages ──────────────────────────────────────────────────────────
sudo apt-get update -q
sudo apt-get install -y python3 python3-pip python3-venv nginx git

# ── Submodule (TTR) code present ──────────────────────────────────────────────
git -C "$APP_DIR" submodule update --init --recursive

# ── Python virtualenv ─────────────────────────────────────────────────────────
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "==> Created .env from .env.example — edit TTR_URL before going live"
fi

# ── systemd service ───────────────────────────────────────────────────────────
sed \
    -e "s|{{APP_DIR}}|$APP_DIR|g" \
    -e "s|{{VENV}}|$VENV|g" \
    -e "s|{{USER}}|$RUN_USER|g" \
    "$APP_DIR/deploy/website.service" \
    | sudo tee /etc/systemd/system/website.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable website
sudo systemctl restart website
echo "==> website service: $(sudo systemctl is-active website)"

# ── nginx ─────────────────────────────────────────────────────────────────────
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/website
sudo ln -sf /etc/nginx/sites-available/website /etc/nginx/sites-enabled/website
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

PUBLIC_IP=$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "<your-ec2-ip>")
echo ""
echo "✓ Website up at http://$PUBLIC_IP"
echo ""
echo "Ticket to Ride:"
echo "  /ttr redirects to TTR_URL (set in .env). Either keep TTR on its own host,"
echo "  or run it from the submodule on this box (see deploy/ttr.service and"
echo "  ttr/deploy/setup.sh) behind a subdomain."
