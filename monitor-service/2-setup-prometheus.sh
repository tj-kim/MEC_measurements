#!/bin/bash

# create prometheus and node_exporter account
if [[ $(cat /etc/passwd | grep 'prometheus:') == *prometheus* ]]; then
  echo 'Account node_exporter is already created'
else  
  sudo useradd --no-create-home --shell /bin/false prometheus
  sudo mkdir /etc/prometheus
  sudo mkdir /var/lib/prometheus
fi
sudo chown prometheus:prometheus /etc/prometheus
sudo chown prometheus:prometheus /var/lib/prometheus


PROMETHEUS_VERSION=2.2.1
PROMETHEUS_DIR=prometheus-$PROMETHEUS_VERSION.linux-amd64
PROMETHEUS_PACKAGE=$PROMETHEUS_DIR.tar.gz
#curl -LO https://github.com/prometheus/prometheus/releases/download/v2.2.1/$PROMETHEUS_VERSION.tar.gz 
echo curl -LO https://github.com/prometheus/prometheus/releases/download/v$PROMETHEUS_VERSION/$PROMETHEUS_PACKAGE 
curl -LO https://github.com/prometheus/prometheus/releases/download/v$PROMETHEUS_VERSION/$PROMETHEUS_PACKAGE 
tar xvf $PROMETHEUS_PACKAGE

sudo cp $PROMETHEUS_DIR/prometheus /usr/local/bin
sudo cp $PROMETHEUS_DIR/promtool /usr/local/bin/

sudo chown prometheus:prometheus /usr/local/bin/prometheus
sudo chown prometheus:prometheus /usr/local/bin/promtool

sudo cp -r $PROMETHEUS_DIR/consoles /etc/prometheus
sudo cp -r $PROMETHEUS_DIR/console_libraries /etc/prometheus

rm -rf $PROMETHEUS_DIR $PROMETHEUS_PACKAGE
sudo cp prometheus.yml /etc/prometheus/prometheus.yml
sudo chown prometheus:prometheus /etc/prometheus/prometheus.yml

sudo cp prometheus.service /etc/systemd/system/prometheus.service
sudo systemctl daemon-reload
sudo systemctl start prometheus
if [[ $(sudo systemctl status prometheus | grep 'Active:') == *active* ]]; then
  echo "Start prometheus successfully!"
  sudo systemctl enable prometheus
else
  sudo systemctl status prometheus
fi


