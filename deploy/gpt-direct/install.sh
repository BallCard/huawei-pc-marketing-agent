#!/bin/sh
# Only install the two dedicated services. Never change the host's network stack.
set -eu
source_dir=${1:?upload directory required}
[ "$(id -u)" = 0 ] || exit 1
for name in huazhang-gpt huazhang-poster; do
    if ! id "$name" >/dev/null 2>&1; then
        useradd --system --user-group --home-dir "/var/lib/$name" --shell /usr/sbin/nologin "$name"
    fi
done
install -d -o root -g root -m 755 /opt/huazhang-gpt
install -d -o root -g root -m 700 /etc/huazhang-gpt
install -d -o huazhang-gpt -g huazhang-gpt -m 700 /var/lib/huazhang-gpt
install -d -o huazhang-poster -g huazhang-poster -m 700 /var/lib/huazhang-poster-worker
install -o root -g root -m 755 "$source_dir/gptweb2api" /opt/huazhang-gpt/gptweb2api
install -o root -g root -m 644 "$source_dir/worker.py" /opt/huazhang-gpt/worker.py
install -o root -g root -m 644 "$source_dir/UPSTREAM-LICENSE" /opt/huazhang-gpt/UPSTREAM-LICENSE
for config in gateway worker; do
    install -o root -g root -m 600 "$source_dir/$config.env" "/etc/huazhang-gpt/$config.env"
done
for service in huazhang-gpt-web huazhang-poster-worker; do
    install -o root -g root -m 644 "$source_dir/$service.service" "/etc/systemd/system/$service.service"
done
systemd-analyze verify /etc/systemd/system/huazhang-gpt-web.service /etc/systemd/system/huazhang-poster-worker.service
systemctl daemon-reload
systemctl enable --now huazhang-gpt-web.service huazhang-poster-worker.service
systemctl is-active huazhang-gpt-web.service huazhang-poster-worker.service
