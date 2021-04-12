#!/bin/bash

# Provision for VM
while getopts ":p" opt; do
    case $opt in
        p)
            export PROVISION=1
            echo "Start provision"
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            ;;
    esac
done

apt-get update
apt-get install -q -y python-pip netperf openssh-server mosquitto ntp
pip2 install -r requirements.txt

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


# setup ssh key
if [[ $(ls ~/.ssh/) == *id_rsa* ]]; then
    echo 'This edge node already has ssh key'
else
    #cp .id_rsa_edge /root/.ssh/id_rsa
    #cp .id_rsa_edge.pubcentre_edge  /root/.ssh/id_rsa
    #cat ~/.ssh/id_rsa.pub ~/.ssh/id_rsa > identity_edge.pem
    # Allow Root user can ssh
    sed -i /etc/ssh/sshd_config \
        -e 's/^PermitRootLogin/#PermitRootLogin/' \
        -e '/PermitRootLogin prohibit-password/a PermitRootLogin yes'
fi

# Change kernel to >=4.12
if [[ $(uname -r) != 4.13.0-41-generic ]]; then
    apt-get install -q -y linux-headers-4.13.0-41-generic \
            linux-image-4.13.0-41-generic
    update-grub
fi
# Check kernel version
echo $(uname -r)

service centre_edge stop
echo "Check and Stop the old centre_edge service"
chk_cmd=`service centre_edge status | sed -n '/CGroup/p'`
if [ "$chk_cmd" != "" ]; then
  service centre_edge stop
  service centre_edge status
  sleep 2
fi
service centre_edge status


if [[ $PROVISION ]]; then
  echo "Add ssh key"
  cp /vagrant/id_rsa /root/.ssh/id_rsa
  cp /vagrant/id_rsa.pub /root/.ssh/id_rsa.pub
  chmod 600 /root/.ssh/id_rsa
  cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys

  echo "Deploy program"
  rsync -ar /mnt/edge /opt/

  echo "Add startup file for centralized controller"
  cat <<EOF | tee /etc/init.d/centre_edge
#!/bin/bash
### BEGIN INIT INFO
# Provides: centre_edge
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
### END INIT INFO
PID=/tmp/centre_edge.pid
RUNDIR=/opt/edge/

function stop_centre_edge {
         echo "Stop centre_edge"
         kill \$(cat \$PID)
         sleep 2
         kill -9 \$(cat \$PID)
}

function start_centre_edge {
         # start mosquitto
         echo "Start MQTT"
         service mosquitto start
         mosquitto -p 9999 -d
         # This script need detect check PID file before it start
         echo "Start centre_edge"
         cd \$RUNDIR
         /usr/bin/python /opt/edge/centralized_controller.py \
                         --log=/var/log/centre_edge.log \
                         --database_file=/var/log/centre_edge.db \
                         --planner=nearest \
                         --verbose \
                         --log_level=DEBUG &
         echo \$! > \$PID
}

case "\$1" in
start) start_centre_edge ;;
stop) stop_centre_edge ;;
restart) stop_centre_edge
         sleep 10
         start_centre_edge
         ;;
esac

EOF

  echo "Add startup file for edge controller"
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
                         --distance=0 &
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

  chmod +x /etc/init.d/migrate
  update-rc.d -f migrate remove
  service migrate start

else
  # real machine
  echo "Deploy centre_edge program"
  #cp -r . /opt/edge/

  echo "Add startup file"
  cat <<EOF | tee /etc/init.d/centre_edge
#!/bin/bash
### BEGIN INIT INFO
# Provides: centre_edge
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
### END INIT INFO
PID=/tmp/centre_edge.pid
RUNDIR=/opt/edge/

function stop_centre_edge {
         echo "Stop centre_edge"
         kill \$(cat \$PID)
         sleep 2
         kill -9 \$(cat \$PID)
}

function start_centre_edge {
         # start mosquitto
         echo "Start MQTT"
         service mosquitto start
         mosquitto -p 9999 -d
         # This script need detect check PID file before it start
         echo "Start centre_edge"
         cd \$RUNDIR
         /usr/bin/python /opt/edge/centralized_controller.py \
                         --log=/var/log/centre_edge.log \
                         --log_level=DEBUG \
                         --database_file=/var/log/centre_edge.db \
                         --verbose \
                         --profile_file=/opt/edge/real_edge_nodes_2d.yml \
                         --planner=nearest &
         echo \$! > \$PID
}

case "\$1" in
start) start_centre_edge ;;
stop) stop_centre_edge ;;
restart) stop_centre_edge
         sleep 10
         start_centre_edge
         ;;
esac

EOF
fi

chmod +x /etc/init.d/centre_edge
### Make sure the service centre_edge is stopped on boot
#systemctl daemon-reload
#sed -i /etc/rc.local \
#    -e '/centre_edge/ d'
#sed -i /etc/rc.local \
#    -e '/^exit/ i centre_edge stop'

### start the script only in product deployment.
update-rc.d -f centre_edge remove
# update-rc.d centre_edge defaults

service centre_edge start


chk_cmd=`service centre_edge status | sed -n '/socket.error/p'`
if [ "$chk_cmd" != "" ]; then
    service centre_edge stop
    sleep 5
    service centre_edge start
fi
service centre_edge status

