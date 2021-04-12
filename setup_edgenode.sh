#!/bin/bash

# Provision for VM
while getopts ":n:d:p" opt; do
    case $opt in
        p)
            export PROVISION=1
            echo "Start provision"
            ;;
        d)
            export DISTANCE=${OPTARG}
            echo "DISTANCE $DISTANCE"
            ;;
        n)
            export BTS_NAME=${OPTARG}
            echo "BTS name $NAME"
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            ;;
    esac
done

apt-get update
apt-get install -q -y xdelta python-pip openssh-server netperf ntp wpasupplicant
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

# dependencies for CRIU:
if [[ $(criu --version) == *3.8.1* ]]; then
  echo "Already install CRIU 3.8.1"
else
  apt-get install -q -y libprotobuf-dev libprotobuf-c0-dev \
       protobuf-c-compiler protobuf-compiler python-protobuf \
       pkg-config python-ipaddr iproute2  libcap-dev libnl-3-dev libnet1-dev
  apt-get install -q -y --no-install-recommends asciidoc xmlto
  cd $HOME
  if [ ! -d criu ]; then
    git clone https://github.com/checkpoint-restore/criu.git
  fi  
  cd criu
  git pull origin master
  git checkout v3.8.1
  make
  make install
fi

# install Docker-ce in Ubuntu 16.04
if [[ $(docker -v) == *17.03.2* ]]; then
  echo "Edge node already has installed Docker-ce 17.03.2-ce"
else
  apt-get install \
      apt-transport-https \
      ca-certificates \
      curl \
      software-properties-common

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
  apt-key fingerprint 0EBFCD88
  add-apt-repository \
     "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) \
     stable"

  apt-get update
  apt-get install -y docker-ce=17.03.2~ce-0~ubuntu-xenial
fi

# add fake BTS to VMs in CI testbed.
if [ $PROVISION ]; then
    if [[ $BTS_NAME ]]; then
        mkdir -p /etc/hostapd
        echo ssid=$BTS_NAME > /etc/hostapd/hostapd.conf
    fi
fi

# Setup experimental for docker and allow prometheus collect data via port 9323
if [ -f /etc/docker/daemon.json ] ; then
  echo "Already has file /etc/docker/daemon.json"
  if [[ $(cat /etc/docker/daemon.json) == *experimental* ]]; then
    echo "Already set docker with experimental mode"
  else
    if ! [ $PROVISION ]; then
      cp ./docker_daemon.json /etc/docker/daemon.json
    else
      cat <<EOF | tee /etc/docker/daemon.json
{
  "metrics-addr" : "127.0.0.1:9323",
  "experimental" : true
}
EOF
    fi
      systemctl restart docker
  fi
else
  # NOTE: We can replace this code as a function
  if ! [ $PROVISION ]; then
    cp docker_daemon.json /etc/docker/daemon.json
  else
    cat <<EOF | tee /etc/docker/daemon.json
{
  "metrics-addr" : "127.0.0.1:9323",
  "experimental" : true
}
EOF
  fi
  systemctl restart docker
fi

#setup mosquito brige

# setup ssh key
if [[ $(ls ~/.ssh/) == *id_rsa* ]]; then
  echo 'This edge node already has ssh key, we overwrite this for all edge node has the same ssh key.'
fi
#cp .id_rsa_edge /root/.ssh/id_rsa
#cp .id_rsa_edge.pub /root/.ssh/id_rsa
#cat ~/.ssh/id_rsa.pub ~/.ssh/id_rsa > identity_edge.pem
# Allow Root user can ssh
sed -i /etc/ssh/sshd_config \
    -e 's/^PermitRootLogin/#PermitRootLogin/' \
    -e '/PermitRootLogin prohibit-password/a PermitRootLogin yes'

# Change kernel to >=4.12
if [[ $(uname -r) != 4.13.0-41-generic ]]; then
  apt-get install -q -y linux-headers-4.13.0-41-generic \
       linux-image-4.13.0-41-generic
  update-grub
fi
# Check kernel version
echo $(uname -r)

# TODO: Setup NAT table

echo "Check and Stop the old migrate service"
service migrate stop
chk_cmd=`service migrate status | sed -n '/CGroup/p'`
if [ "$chk_cmd" != "" ]; then
  service migrate stop
  service migrate status
  sleep 10
fi
service migrate status

if [[ $PROVISION ]]; then
  echo "Add ssh key"
  cp /vagrant/id_rsa /root/.ssh/id_rsa
  cp /vagrant/id_rsa.pub /root/.ssh/id_rsa.pub
  chmod 600 /root/.ssh/id_rsa
  cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys

  echo "Deploy program"
  rsync -ar --exclude-from=/mnt/edge/exclude_files --delete /mnt/edge /opt/

  echo "Add startup file"
  cat <<EOF | tee /etc/init.d/migrate
#!/bin/bash
### BEGIN INIT INFO
# Provides: migrate
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
### END INIT INFO
PID=/tmp/migrate.pid
RUNDIR=/opt/edge/

function stop_migrate {
         echo "Stop migrate"
         kill \$(cat \$PID)
         sleep 2
         kill -9 \$(cat \$PID)
}

function start_migrate {
         # This script need detect check PID file before it start
         echo "Start migrate"
         cd \$RUNDIR
         /usr/bin/python /opt/edge/edge_controller.py \
                         --verbose \
                         --log=/var/log/migrate_$HOSTNAME.log \
                         --broker_ip='10.0.99.2' \
                         --log_level=DEBUG \
                         --distance=$DISTANCE &
         echo \$! > \$PID
}

case "\$1" in
start) start_migrate ;;
stop) stop_migrate ;;
restart) stop_migrate
         sleep 5
         start_migrate
         ;;
esac

EOF
else
  # real machine
  echo "Deploy program"
  #cp -r . /opt/edge/

  echo "Add startup file"
  cat <<EOF | tee /etc/init.d/migrate
#!/bin/bash
### BEGIN INIT INFO
# Provides: migrate
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
### END INIT INFO
PID=/tmp/migrate.pid
RUNDIR=/opt/edge/

function stop_migrate {
         echo "Stop migrate"
         kill \$(cat \$PID)
         sleep 2
         kill -9 \$(cat \$PID)
}

function start_migrate {
         # This script need detect check PID file before it start
         echo "Start migrate"
         cd \$RUNDIR
         /usr/bin/python /opt/edge/edge_controller.py \
                         --verbose \
                         --log=/var/log/migrate_$HOSTNAME.log \
                         --log_level=DEBUG \
                         --conf=/opt/edge/real_edge_nodes_2d.yml \
                         --broker_ip='172.18.35.196' \
                         --distance=$DISTANCE &
         echo \$! > \$PID
}

case "\$1" in
start) start_migrate ;;
stop) stop_migrate ;;
restart) stop_migrate
         sleep 5
         start_migrate
         ;;
esac

EOF
fi

chmod +x /etc/init.d/migrate
### Make sure the service migrate is stopped on boot
#systemctl daemon-reload
#sed -i /etc/rc.local \
#    -e '/migrate/ d'
#sed -i /etc/rc.local \
#    -e '/^exit/ i migrate stop'

### start the script only in product deployment.
update-rc.d -f migrate remove
# update-rc.d migrate defaults

service migrate start

check_netserver=`ps -ef | grep netserver | grep -v 'grep'`
if [ "$check_netserver" = "" ]; then
  echo "Start netserver"
  netserver
else
  echo "netserver is running"
  echo "$check_netserver"
fi

docker pull ngovanmao/openface:17
docker pull ngovanmao/u1404_opencv_py3_yolov3:05
docker pull gochit/simple_tcp_service:03
docker pull ngovanmao/yolov3-mini-cpu-amd64:01

chk_cmd=`service migrate status | sed -n '/socket.error/p'`
if [ "$chk_cmd" != "" ]; then
    service migrate stop
    sleep 5
    service migrate start
fi
service migrate status
# Start monitoring service container (prometheus, node_exporter, cadvisor)
#cd /opt/edge/monitor-service
#docker-compose -f docker-compose-edge.yml  up -d
