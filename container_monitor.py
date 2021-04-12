import time
import Queue
import logging
import datetime
import subprocess
import collections
import docker
from sql_service import Sqlite3ContainerMonitor

ContainerReport = collections.namedtuple('ContainerReport', ['container',
                                                             'status', 'cpu',
                                                             'mem', 'size',
                                                             'delta_memory',
                                                             'pre_checkpoint',
                                                             'time_checkpoint',
                                                             'time_xdelta'])

class ContainerMonitor(object):
    UNITS = {'MiB': 1024**2/1000**2,
             'GiB': 1024**3/1000**2,
             'MB': 1,
             'GB':1000}
    def __init__(self, delay=5*60, **kwargs):
        self.database = Sqlite3ContainerMonitor()
        self.database.create()
        self.client = docker.from_env()
        self.delay = delay
        self.report_method = kwargs.get('report', None)
        self.containers = []
        self.queue = Queue.Queue()

    def measure_container_basic_stat(self, name):
        """
        Example result:
        3.64%    49.98MiB / 15.59GiB
        """
        # print(' '.join(cmd))
        cmd_prefix = \
            'docker stats --no-stream --format "{{.CPUPerc}}    {{.MemUsage}}" '
        out = subprocess.check_output(cmd_prefix + name, shell=True)
        logging.debug('command {} return {}'.format(cmd_prefix+name, out))
        stats = out.split("\n")[0].split("    ")
        cpu = float(stats[0].rstrip('%'))
        mem_str = stats[1].split(' / ')[0]
        mem_unit = mem_str[-3:]
        mem = float(mem_str[:-3])*ContainerMonitor.UNITS[mem_unit]
        return (cpu,mem)

    def measure_container_size(self, name, image):
        query_size = 'docker images ' + image + ' --format "{{.Size}}"'
        out = subprocess.check_output(query_size, shell=True).replace(' ', '').\
                                                         rstrip("\n")
        logging.debug('command {} return {}'.format(query_size, out))
        val = float(out[:-2])
        unit = out[-2:]
        return val*ContainerMonitor.UNITS[unit]

    def container_status(self, name):
        containers = self.client.containers.list(filters={'name':name})
        if len(containers) != 0:
            return containers[0].status
        else:
            logging.warn("Canot find container")
            return None

    def measure(self, data):
        self.services = data
        for s in self.services:
            if s.delta_memory is None or s.pre_checkpoint is None:
                continue
            container = s.get_container_name()
            img = s.container_img
            status = self.container_status(container)
            if status is None:
                # Cannot find the container, ignore it
                continue
            try:
                cpu, mem = self.measure_container_basic_stat(container)
                size = self.measure_container_size(container, img)
            except ValueError:
                logging.warn("Cannot check container stats")
                continue
            except subprocess.CalledProcessError:
                logging.warn("Cannot check container stats")
                continue
            ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            self.database.insert_container_metrics(ts, container, status, cpu,
                                                   mem, size);
            report = ContainerReport(container, status, cpu, mem, size,
                                     s.delta_memory,
                                     s.pre_checkpoint,
                                     s.time_checkpoint,
                                     s.time_xdelta)
            if self.report_method is not None:
                logging.debug("Publish container report!")
                self.report_method(report)
            else:
                logging.warn("None report method")

    def main_monitor(self):
        self.last_list = []
        while True:
            try:
                new_data = self.queue.get(True, self.delay)
                self.measure(new_data)
                self.last_list = new_data
            except Queue.Empty:
                # Measure the old result
                self.measure(self.last_list)
