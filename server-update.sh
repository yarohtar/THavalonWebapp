#!/usr/bin/env bash
# Runs ON THE SERVER. Pulls the latest master and restarts the app.
# Triggered by the GitHub "Deploy" workflow through a restricted SSH key
# (see authorized_keys: command="..."), so that key can do nothing else.
#
# Wrapped in { } so bash reads the whole script before `git reset`
# replaces this file.
{
set -euo pipefail
cd /var/www/avalon/THavalonWebapp

echo "Fetching latest master..."
git fetch --quiet origin master
git reset --hard origin/master
git log --oneline -1

echo "Installing requirements..."
/var/www/avalon/venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

echo "Restarting avalon..."
sudo systemctl restart avalon
sleep 2
systemctl is-active avalon
exit
}
