#!/bin/bash

# create prometheus and node_exporter account
if [[ $(cat /etc/passwd | grep 'node_exporter:') == *node_exporter* ]]; then
  echo 'Account node_exporter is already created'
else  
  sudo useradd --no-create-home --shell /bin/false node_exporter
fi

NODE_EXPORTER_VERSION=0.16.0-rc.3
NODE_EXPORTER_DIR=node_exporter-$NODE_EXPORTER_VERSION.linux-amd64
NODE_EXPORTER_PACKAGE=$NODE_EXPORTER_DIR.tar.gz
echo  curl -LO https://github.com/prometheus/node_exporter/releases/download/v$NODE_EXPORTER_VERSION/$NODE_EXPORTER_PACKAGE
curl -LO https://github.com/prometheus/node_exporter/releases/download/v$NODE_EXPORTER_VERSION/$NODE_EXPORTER_PACKAGE
tar xvf $NODE_EXPORTER_PACKAGE

sudo cp $NODE_EXPORTER_DIR/node_exporter /usr/local/bin
sudo chown node_exporter:node_exporter /usr/local/bin/node_exporter
rm -rf $NODE_EXPORTER_DIR $NODE_EXPORTER_PACKAGE

sudo cp node_exporter.service /etc/systemd/system/node_exporter.service
sudo systemctl daemon-reload
sudo systemctl start node_exporter
if [[ $(sudo systemctl status node_exporter | grep 'Active:') == *active* ]]; then
    echo "Start prometheus successfully!"
    sudo systemctl enable node_exporter
fi
