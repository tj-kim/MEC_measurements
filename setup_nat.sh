#!/bin/bash

function start_nat () {
    if [ -z "$1" ]
    then
        echo "Invalid interface"
        echo "setup_nat.sh <start|stop> interface"
        return 1
    else
        echo 1 > /proc/sys/net/ipv4/ip_forward
        iptables -t nat -o $1 -A POSTROUTING -j MASQUERADE
        iptables -A FORWARD -j ACCEPT
        return 0
    fi
}

function stop_nat () {
    if [ -z "$2" ]
    then
        echo "Invalid interface"
        echo "setup_nat.sh <start|stop> interface"
        return 1
    else
        echo 0 > /proc/sys/net/ipv4/ip_forward
        iptables -t nat -o $1 -D POSTROUTING -j MASQUERADE
        iptables -D FORWARD -j ACCEPT
        return 0
    fi
}

case "$1" in
    start)
        start_nat $2
        ;;
    stop)
        stop_nat $2
        ;;
    *)
        echo "Invalid operation"
        echo "setup_nat.sh <start|stop> interface"
        return 2
        ;;
esac

