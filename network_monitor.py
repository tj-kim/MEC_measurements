import time
import Queue
import datetime
import subprocess
import logging
import collections

from sql_service import Sqlite3NetworkMonitor
from discovery_edge import DiscoveryYaml
from utilities import find_my_ip, listen_change_with_timeout
from random import randint, shuffle

MonitorReport = collections.namedtuple('MonitorReport', ['src_node', 'dest_node',
                                                        'latency', 'bw'])

class NetworkMonitor(object):
    """Network monitor service.

    Attributes:
        - report (function): Callback function.
    """

    def __init__(self, **kwargs):
        self.sql_database = Sqlite3NetworkMonitor()
        self.sql_database.create()
        self.report_method = kwargs.get('report', None)
        self.remote = '8.8.8.8'
        self.first = True
        self.conf_file = kwargs.get('conf', '')
        if self.conf_file == '':
            self.conf = None
        else:
            self.conf = DiscoveryYaml(self.conf_file)
        self.queue = Queue.Queue()

    def update_my_neighbors_info(self, my_neighbors):
        self.my_neighbors = my_neighbors

    def start_server(self):
        try:
            out = subprocess.check_output(['netserver'])
            logging.info("Start netperf server...{}".format(out))
        except subprocess.CalledProcessError:
            logging.info("Netserver is already started, use service netperf stop")

    def measure_latency(self, next_hop):
        """Measures latency using `netperf`.

        Options:
            - -P 0: suppress output
            - -t TCP_RR: TCP request/response, which is a default
            - P50_LATENCY,P90_LATENCY,P99_LATENCY,MEAN_LATENCY
            - 50th Percentile Latency Microseconds,
            - 90th Percentile Latency Microseconds,
            - 99th Percentile Latency Microseconds,
            - Mean Latency Microseconds

        Reference:
        https://github.com/grpc/grpc/blob/master/tools/run_tests/performance/run_netperf.sh

        This latency is an average rounf-trip latency:
        https://hewlettpackard.github.io/netperf/doc/netperf.html
        """
        cmd = 'netperf -P 0 -t  TCP_RR -H {} -- -r 1,1 -o \
            P50_LATENCY,P90_LATENCY,P99_LATENCY,MEAN_LATENCY'.format(next_hop)
        #print(cmd)
        out = subprocess.check_output(cmd, shell=True)
        latencies = out.strip().split(',')
        #print("out = {}".format(latencies))
        mean_latency = latencies[-1]
        #logging.debug("mean latency {} microseconds".format(mean_latency))
        return float(mean_latency)

    def measure_bandwidth(self, next_hop):
        """ Measure bandwidth,

        Example::

            MIGRATED TCP STREAM TEST from 0.0.0.0 (0.0.0.0) port 0 AF_INET to 172.18.34.113 () port 0 AF_INET : demo
            Recv   Send    Send
            Socket Socket  Message  Elapsed
            Size   Size    Size     Time     Throughput
            bytes  bytes   bytes    secs.    10^6bits/sec

            87380  16384  16384    10.01     934.07
        """
        cmd = 'netperf -P 0 -H {}'.format(next_hop)
        #print(cmd)
        out = subprocess.check_output(cmd, shell=True)
        #print("out = {}".format(out))
        bandwidth = out.split()[-1]
        #logging.debug("bandwidth {} Mbps".format(bandwidth))
        return float(bandwidth)

    def measure(self, data):
        self.neighbors = list(reversed(data))
        logging.debug("Start measure neighbors: {}".\
                      format(self.neighbors))
        my_ip = find_my_ip(self.remote)
        for nexthop_ip in self.neighbors:
            time.sleep(randint(0, 10))
            #logging.debug("measure metric from {} to {}".
            #    format(my_ip, nexthop_ip))
            # latency = self.measure_latency(nexthop_ip)
            # bandwidth = self.measure_bandwidth(nexthop_ip)
            # ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            # self.sql_database.insert_net_metrics(ts, my_ip, nexthop_ip,
            #                                      latency, bandwidth)
            my_name = self.conf.get_server_name_from_ip(my_ip)
            nexthop_name = self.conf.get_server_name_from_ip(nexthop_ip)
            metric = self.conf.get_metric(my_name, nexthop_name)
            if metric is None:
                logging.error("Cannot find metric from {} to {}".\
                              format(my_name, nexthop_name))
                continue
            latency = metric['delay']*2*10**3
            bandwidth = metric['bw']
            report = MonitorReport(my_ip, nexthop_ip, latency, bandwidth)
            if self.report_method is not None:
                self.report_method(report)
            else:
                logging.warning("Network monitor report method is undefined!")
        self.first = False

    def flush_queue(self):
        while self.queue.qsize() > 1:
            try:
                new_data = self.queue.get_nowait()
                self.queue.task_done()
            except Queue.Empty:
                return new_data
        return None

    def main_monitor(self):
        self.last_list = []
        while True:
            try:
                data = self.flush_queue()
                if data is None:
                    new_data = self.queue.get(True, randint(60, 900))
                else:
                    new_data = data
                self.measure(new_data)
                self.last_list = new_data
                self.queue.task_done()
            except Queue.Empty:
                # Measure the old result
                self.measure(self.last_list)

