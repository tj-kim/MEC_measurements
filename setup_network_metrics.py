#!/usr/bin/python

import yaml
import argparse
import subprocess

import discovery_edge

root = 'fa:'

def delete_all_rules(dev):
    try:
        # tc qdisc del dev xxx root
        cmd = ['tc', 'qdisc', 'del', 'dev', dev , 'root']
        print(' '.join(cmd))
        subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        print("Error when clean rules")

def apply_metric(dev, metric, discovery_edge, handle):
    name = metric.get('name')
    delay = metric.get('delay')
    bw = metric.get('bw')
    ip = discovery_edge.get_server_ip(name)
    """
    /sbin/tc qdisc add dev vboxnet6 root handle 1f31: htb default 1
    /sbin/tc class add dev vboxnet6 parent 1f31: classid 1f31:1 htb rate 10000kbit
    /sbin/tc class add dev vboxnet6 parent 1f31: classid 1f31:2 htb rate 10000.0Kbit ceil 10000.0Kbit
    /sbin/tc qdisc add dev vboxnet6 parent 1f31:2 handle 1fb1: netem delay 10.000000ms
    /sbin/tc filter add dev vboxnet6 protocol ip parent 1f31: prio 2 u32 match ip dst 10.0.99.11/32 match ip src 0.0.0.0/0 flowid 1f31:2
    """
    cmd = ['tc', 'class', 'add', 'dev', dev, 'parent', root, 'classid',
           '{}{}{}'.format(root, handle, 1), 'htb', 'rate', '{}Mbit'.format(bw)]
    print(' '.join(cmd))
    subprocess.check_output(cmd)
    cmd = ['tc', 'class', 'add', 'dev', dev, 'parent', root, 'classid',
           '{}{}{}'.format(root, handle, 2), 'htb', 'rate', '{}Mbit'.format(bw),
           'ceil', '{}Mbit'.format(bw)]
    print(' '.join(cmd))
    subprocess.check_output(cmd)
    cmd = ['tc', 'qdisc', 'add', 'dev', dev, 'parent',
           '{}{}{}'.format(root, handle, 2), 'handle',
           '{}{}'.format(handle, root), 'netem', 'delay', '{}ms'.format(delay)]
    print(' '.join(cmd))
    subprocess.check_output(cmd)
    cmd = ['tc', 'filter', 'add', 'dev', dev, 'protocol', 'ip', 'parent', root,
           'prio', '2', 'u32', 'match', 'ip', 'dst', '{}/32'.format(ip), 'match',
           'ip', 'src', '0.0.0.0/0', 'flowid', '{}{}{}'.format(root, handle, 2)]
    print(' '.join(cmd))
    subprocess.check_output(cmd)

def setup_metrics(dev, metrics, discovery_service):
    delete_all_rules(dev)
    # Create root node, at handle 1
    # tc qdisc add dev xxx root handle 1: htb default 1 r2q 160
    # TODO: Need more explaination about tc command
    cmd = ['tc', 'qdisc', 'add', 'dev', dev, 'root', 'handle', root, 'htb',
           'default', '1']
    print(' '.join(cmd))
    subprocess.check_output(cmd)
    h = 1
    for m in metrics:
        print('Setup metric for {}'.format(m))
        apply_metric(dev, m, discovery_service, h)
        h += 1
        print('-----------------------------------------------')

def find_metrics(name, seq):
    obj = next((n for n in seq if n.get('name', '')==name), None)
    if obj is not None:
        return obj.get('metrics', [])
    else:
        return []

if __name__ == '__main__':
    out = subprocess.check_output(['whoami'])
    if out != 'root\n':
        print('You must run this script under root permission')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='op',
        help="Operate: add or del")
    add_parser = subparsers.add_parser('add',
        help='Add tc rule to the interface')
    add_parser.add_argument(
        '--name',
        type=str,
        help="Hostname of the source node in conf file",
        required=True)
    add_parser.add_argument(
        '--conf',
        type=str,
        help="Config file path",
        required=True)
    add_parser.add_argument(
        '--eu',
        help="End device",
        action='store_true')
    del_parser = subparsers.add_parser('del',
        help='Delete all tc rules of the interface')
    parser.add_argument(
        '--dev',
        type=str,
        help="Network device to apply the operation.",
        default='vboxnet0')
    args = parser.parse_args()
    if args.op == 'del':
        delete_all_rules(args.dev)
    elif args.op == 'add':
        with open(args.conf, 'r') as f:
            obj = yaml.load(f)
            if args.eu:
                # End user
                infos = obj.get('end_users', [])
            else:
                # Edge node
                infos = obj.get('servers', [])
            m = find_metrics(args.name, infos)
            filename = args.conf
            if filename.split('.')[-1] != 'db':
                dis = discovery_edge.DiscoveryYaml(args.conf)
            else:
                dis = discovery_edge.DiscoverySql(args.conf)
            setup_metrics(args.dev, m, dis)
