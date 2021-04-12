from __future__ import division

import time
import datetime
import subprocess
import collections
from random import randint, shuffle
from discovery_edge import DiscoveryYaml
from utilities import get_hostname
import psutil

from sql_service import Sqlite3ServerMonitor

ServerReport = collections.namedtuple('ServerReport', ['cpu_max', 'cpu_cores',
                                                       'mem_total', 'mem_free',
                                                       'disk_total', 'disk_free'])
def alternative_cpu_freq():
    out = subprocess.check_output(['cat', '/proc/cpuinfo']).split("\n")
    line = next((i for i in out if 'cpu MHz' in i), None)
    freq = None
    if line is not None:
        freq = int(float(line.split(':')[1].lstrip(' ')))
    return freq


class ServerMonitor(object):
    def __init__(self, delay=5*60, **kwargs):
        self.database = Sqlite3ServerMonitor();
        self.database.create()
        self.delay = delay
        self.report_method = kwargs.get('report', None)
        self.conf_file = kwargs.get('conf', None)
        if self.conf_file is None:
            self.configs = None
        else:
            self.configs = DiscoveryYaml(self.conf_file)

    def get_cpu_info(self):
        if self.configs is not None:
            hostname = get_hostname()
            server_info = self.configs.get_server_info_from_name(hostname)
            time_benchmark = float(server_info.get('benchmark'))
            cnt = int(server_info.get('core'))
            if cnt != 0:
                freq = (1/time_benchmark * 1000) / cnt
            else:
                freq = 0
        else:
            freq_obj = psutil.cpu_freq()
            if freq_obj is None:
                freq = alternative_cpu_freq()
            else:
                freq = freq_obj.max
            cnt = psutil.cpu_count()
        return freq, cnt

    def get_ram_info(self):
        mem = psutil.virtual_memory()
        # Memory in MB
        return mem.total/1000**2, \
               mem.free/1000**2

    def get_disk_info(self):
        disk = psutil.disk_usage('/')
        return disk.total/1024**2, \
            disk.free/1024**2 # Disk in MB

    def main_monitor(self):
        while True:
            cpu_max, cpu_cores = self.get_cpu_info()
            mem_total, mem_free = self.get_ram_info()
            disk_total, disk_free = self.get_disk_info()
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.database.insert_server_metrics(ts, cpu_max, cpu_cores,
                                                mem_total, mem_free, disk_total,
                                                disk_free)
            report = ServerReport(cpu_max, cpu_cores, mem_total, mem_free,
                                   disk_total, disk_free)
            if self.report_method is not None:
                self.report_method(report)
            time.sleep(randint(0, self.delay))
