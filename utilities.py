from __future__ import division
import os
import sys
import json
import time
import socket
import logging
import traceback
import subprocess
from subprocess import check_output, Popen
import numpy as np

import Constants

def check_output_w_warning(args, **kwargs):
    p = Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ret = p.communicate()
    if p.returncode != 0:
        raise subprocess.CalledProcessError
    if ret[1] != '':
        print('Warning: {} returns a error message: {}'.format(args, ret[1]))
    return ret[0]

def get_time():
    return int(time.time()*1000000) # us

def find_my_ip(remote_ip='8.8.8.8'):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((remote_ip, 80))
    my_ip = s.getsockname()[0]
    # print("my ip is {}".format(my_ip))
    s.close()
    return my_ip

def get_hostname():
    hostname = os.uname()[1]
    print("hostname = {}".format(hostname))
    return hostname

def get_ap_ssid():
    ssid=check_output("cat /etc/hostapd/hostapd.conf | sed -n -e 's/ssid=//p'",
        shell=True).strip()
    print("my ssid={}".format(ssid))
    if ssid == '':
        return None
    else:
        return ssid

def get_json_from_object(data_object):
    return json.dumps(data_object, default=lambda o : o.__dict__)

def check_swap_file(file_name, options="-ntl"):
    if os.path.isfile(file_name):
        print("Existing file {}. We will rotate and save it.".format(file_name))
        output = check_output(["savelog", options,file_name])

def find_open_port(start_range=9900, end_range=9999):
    for port in range(start_range, end_range):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = 0
        try:
            result = sock.bind(('', port))
        except:
            print("port {} is already used.".format(port))
        sock.close()
        if result == None:
            print("available port: {}".format(port))
            return port

def get_container_for_service(service_name):
    # TODO: enhance the logic for scaling to other service.
    container_image = None
    container_port = None
    if service_name == Constants.OPENFACE:
        container_image = Constants.OPENFACE_DOCKER_IMAGE
        container_port = 9999
    elif service_name == Constants.YOLO:
        container_image = Constants.YOLO_DOCKER_IMAGE
        container_port = 9988
    elif service_name == Constants.SIMPLE_SERVICE:
        container_image = Constants.SIMPLE_DOCKER_IMAGE
        container_port = 9966
    return container_image, container_port

def init_with_dict(obj, input_dict, attr, init):
    setattr(obj, attr, input_dict.get(attr, init))

def listen_change_with_timeout(check_func, end_cb, timeout, time_step=1):
    while timeout:
        if check_func():
            end_cb()
            return
        else:
            timeout -= 1
            time.sleep(time_step)
    end_cb()

def handle_exception(exc_type, exc_value, exc_traceback):
    logging.error("".join(traceback.format_exception(exc_type, exec_value,
                                                     exc_traceback)))
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

def get_default_interface():
    """Get the name of the default interface.

    We get the name by using `route` command.
    """
    # ip route list match default
    cmd = ['ip', 'route', 'list', 'match', 'default']
    line = check_output(cmd).split("\n")[0]
    # default via 172.18.64.1 dev enp0s25 proto dhcp metric 100
    elements = line.split()
    return elements[4]

def get_interface_for_ip(ip):
    """Get the name of the interface that can match the ip.

    If the ip cannot match to any address other than default, the
    function return default interface.

    Args:
        ip (str): the IP address that we need to find the address
    Raises:
        RuntimeError: if the route table is empty
    """
    # ip route list match <ip>
    cmd = ['ip', 'route', 'list', 'match', ip]
    lines = check_output(cmd).split("\n")
    if len(lines) == 0:
        raise RuntimeError("Can not found any route entries!")
    for line in lines:
        elements = line.split()
        if elements[0] == 'default':
            # default via 172.18.64.1 dev enp0s25 proto static metric 100
            default = elements[4]
        else:
            # 10.0.99.0/24 dev vboxnet1 proto kernel scope link src 10.0.99.1
            return elements[2]

def approx(a, b, eps):
    return abs(a - b) < eps

def find_velocity(x, t):
    l = len(x)
    v = []
    for i in range(l-1):
        d_x = x[i+1] - x[i]
        d_t = (t[i+1] - t[i])/10.0**6 # divide 10^6 to get m/s
        v.append(d_x/d_t)
    return np.mean(v)
