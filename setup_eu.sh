#!/bin/bash

apt-get update
apt-get install -q -y python-pip ntp
pip install -r requirements.txt

timedatectl set-timezone Asia/Singapore

cat <<EOF | tee /etc/ntp.conf
server 0.sg.pool.ntp.org
server 1.sg.pool.ntp.org
server 2.sg.pool.ntp.org
server 3.sg.pool.ntp.org
EOF

# service ntp stop
# ntpd -gq
service ntp start

echo "Deploy program"
rsync -ar /mnt/edge /opt/
