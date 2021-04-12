#!/bin/bash
# source: https://gist.github.com/dashohoxha/5767262
### make sure that this script is executed from root
if [ $(whoami) != 'root' ]
then
    echo "
This script should be executed as root or with sudo:
    sudo $0
"
    exit 1
fi

### make sure that iw is installed
apt-get -y install iw

### check that AP is supported
supports_access_point=$(iw list | sed -n -e '/* AP$/p')
if [ "$supports_access_point" = '' ]
then
    echo "AP is not supported by the driver of the wireless card."
    echo "This script does not work for this driver."
    exit 1
fi

##############################################################
##  Setup and host a network
##############################################################

### install hostapd
apt-get -y install hostapd

### it should not start automatically on boot
update-rc.d hostapd disable

### get ssid and password
#ssid=$(hostname --short)
ssid=edge01
read -p "The name of your hosted network (SSID) [$ssid]: " input
ssid=${input:-$ssid}
password='ngovanmao'
read -p "The password of your hosted network [$password]: " input
password=${input:-$password}


### get wifi interface
rfkill unblock wifi   # enable wifi in case it is somehow disabled (thanks to Darrin Wolf for this tip)
#wifi_interface=$(lshw -quiet -c network | sed -n -e '/Wireless interface/,+12 p' | sed -n -e '/logical name:/p' | cut -d: -f2 | sed -e 's/ //g')
wifi_interface=$(iw dev |awk '$1=="Interface"{print $2}' | grep wlp)

#sudo cp hostapd.conf /etc/hostapd/hostapd.conf
# create /etc/hostapd/hostapd.conf
cat <<EOF > /etc/hostapd/hostapd.conf
interface=$wifi_interface
# SSID to be used in IEEE 802.11 management frames
ssid=$ssid
# Driver interface type (hostap/wired/none/nl80211/bsd)
driver=nl80211
# Country code (ISO/IEC 3166-1)
country_code=US
# Operation mode (a = IEEE 802.11a (5 GHz), b = IEEE 802.11b (2.4 GHz)
hw_mode=a
# Channel number
channel=40
# Maximum number of stations allowed
max_num_sta=128
# Bit field: bit0 = WPA, bit1 = WPA2
wpa=3
# Bit field: 1=wpa, 2=wep, 3=both
auth_algs=1
### IEEE 802.11n
ieee80211n=1
ht_capab=[HT20][HT40+][SHORT-GI-20][SHORT-GI-40][DSSS_CCK-40]

### IEEE 802.11ac
ieee80211ac=1
#vht_oper_chwidth=1
#vht_capab=[HT40-]
#vht_oper_centr_freq_seg0_idx=46

# Set of accepted cipher suites
rsn_pairwise=CCMP
# Set of accepted key management algorithms
wpa_key_mgmt=WPA-PSK
wpa_passphrase=$password

# Time interval for rekeying GTK (broadcast/multicast encryption keys) in
# seconds. (dot11RSNAConfigGroupRekeyTime)
# I changed the default parameter wpa_group_rekey=600 to wpa_group_rekey=1800
# and the automatic disconnection happened only after 30 minutes.
wpa_group_rekey=1800

# hostapd event logger configuration
logger_stdout=-1
logger_stdout_level=2
# Beacon interval in kus (1.024 ms) (default: 100; range 15..65535)
beacon_int=15
# disable WMM for powersave feature kicking off hostapd
wmm_enabled=0
EOF

### modify /etc/default/hostapd
cp -n /etc/default/hostapd{,.bak}
sed -i /etc/default/hostapd \
    -e '/DAEMON_CONF=/c DAEMON_CONF="/etc/hostapd/hostapd.conf"'

################################################
## Set up DHCP server for IP address management
################################################

### make sure that the DHCP server is installed
apt-get -y install isc-dhcp-server

### it should not start automatically on boot
update-rc.d isc-dhcp-server disable

### set the INTERFACES on /etc/default/isc-dhcp-server
cp -n /etc/default/isc-dhcp-server{,.bak}
sed -i /etc/default/isc-dhcp-server \
    -e "/INTERFACES=/c INTERFACES=\"$wifi_interface\""

### modify /etc/dhcp/dhcpd.conf
cp -n /etc/dhcp/dhcpd.conf{,.bak}
sed -i /etc/dhcp/dhcpd.conf \
    -e 's/^option domain-name/#option domain-name/' \
    -e 's/^option domain-name-servers/#option domain-name-servers/' \
    -e 's/^default-lease-time/#default-lease-time/' \
    -e 's/^max-lease-time/#max-lease-time/'

sed -i /etc/dhcp/dhcpd.conf \
    -e '/subnet 10.10.0.0 netmask 255.255.255.0/,+4 d'
cat <<EOF >> /etc/dhcp/dhcpd.conf
subnet 10.10.0.0 netmask 255.255.255.0 {
        range 10.10.0.2 10.10.0.254;
        option domain-name-servers 8.8.4.4, 208.67.222.222;
        option routers 10.10.0.1;
}
EOF
#################################################
## Create a startup script
#################################################

cat <<EOF > /etc/init.d/wifi_access_point
#!/bin/bash
### BEGIN INIT INFO
# Provides: wifi_access_point
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Do not start daemon at boot time
# Description: Daemon to start hostapd and dhcp service for WiFi AP.
### END INIT INFO
#ext_interface=\$(ip route | grep default | cut -d' ' -f5| head -1)
ext_interface=\$(ip route | grep -m 1 default | cut -d' ' -f5)

function stop_wifi_ap {
    ### stop services dhcpd and hostapd
    service isc-dhcp-server stop
    service hostapd stop

    ### disable IP forwarding
    echo 0 > /proc/sys/net/ipv4/ip_forward
    iptables -t nat -D POSTROUTING -s 10.10.0.0/16 -o \$ext_interface -j MASQUERADE 2>/dev/null
    
    ### remove the static IP from the wifi interface
    if grep -q 'auto $wifi_interface' /etc/network/interfaces
    then
        sed -i /etc/network/interfaces -e '/auto $wifi_interface/,\$ d'
        sed -i /etc/network/interfaces -e '\$ d'
    fi

    ### restart network manager to takeover wifi management
    service network-manager restart
}

function start_wifi_ap {
    stop_wifi_ap
    sleep 3

    ### see: https://bugs.launchpad.net/ubuntu/+source/wpa/+bug/1289047/comments/8
    nmcli nm wifi off
    rfkill unblock wlan

    ### give a static IP to the wifi interface
    ip link set dev $wifi_interface up
    ip address add 10.10.0.1/24 dev $wifi_interface
    
    ifdown $wifi_interface
    ifup $wifi_interface

    ### protect the static IP from network-manger restart
    echo >> /etc/network/interfaces
    echo 'auto $wifi_interface' >> /etc/network/interfaces
    echo 'iface $wifi_interface' inet static >> /etc/network/interfaces
    echo 'address 10.10.0.1' >> /etc/network/interfaces
    echo 'netmask 255.255.255.0' >> /etc/network/interfaces

    ### enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    iptables -t nat -A POSTROUTING -s 10.10.0.0/16 -o \$ext_interface -j MASQUERADE
    iptables -P FORWARD ACCEPT
    iptables -F FORWARD

    ### start services dhcpd and hostapd
    service hostapd start
    service isc-dhcp-server start
    service hostapd status
    service isc-dhcp-server status
}

### start/stop wifi access point
case "\$1" in
    start) start_wifi_ap ;;
    stop)  stop_wifi_ap  ;;
esac
EOF

chmod +x /etc/init.d/wifi_access_point

### make sure that it is stopped on boot
sed -i /etc/rc.local \
    -e '/service wifi_access_point stop/ d'
sed -i /etc/rc.local \
    -e '/^exit/ i service wifi_access_point stop'


### display usage message
echo "
======================================

Wifi Access Point installed.

You can start and stop it with:
    service wifi_access_point start
    service wifi_access_point stop

"
