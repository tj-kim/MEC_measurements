import logging

import Constants
from utilities import init_with_dict

class MigrateRecord(object):
    def __init__(self, **kwargs):
        keys = [("source_ip", ""),
                ("dest_ip", ""),
                ("service", ""),
                ("method", ""),
                ("pre_checkpoint", 0),
                ("pre_rsync", 0),
                ("prepare", 0),
                ("checkpoint", 0),
                ("rsync", 0),
                ("xdelta_source", 0),
                ("final_rsync", 0),
                ("migrate", 0),
                ("premigration", 0),
                ("xdelta_dest", 0),
                ("restore", 0),
                ("size_pre_rsync", 0),
                ("size_rsync", 0),
                ("size_final_rsync", 0)]
        for key in keys:
            init_with_dict(self, kwargs, key[0], key[1])

class MigrateNode(object):
    def __init__(self, **kwargs):
        self.snapshot = kwargs.get("snapshot", "snapshot")
        self.end_user = kwargs.get("end_user", Constants.END_USER)
        self.service_name = kwargs.get("service_name", Constants.OPENFACE)
        self.registry = kwargs.get("registry", "ngovanmao")
        self.user = kwargs.get("user", "root")
        self.ip = kwargs.get("ip", "")
        self.server_name = kwargs.get('server_name', '')
        self.port = kwargs.get("port", 5678)
        self.ssid = kwargs.get("ssid", "")
        self.bssid = kwargs.get("bssid", "")
        self.container_port = kwargs.get('container_port', '')
        self.container_img = kwargs.get("container_img", "")
        self.dump_dir = kwargs.get("dump_dir", "/tmp")
        self.debug = kwargs.get("debug", False)
        self.method = kwargs.get("method", "delta")
        self.request = kwargs.get("request", 0)
        self.time_checkpoint = kwargs.get("time_checkpoint", 0)
        self.time_xdelta = kwargs.get("time_xdelta", 0)
        self.delta_memory = kwargs.get("delta_memory", None)
        self.pre_checkpoint = kwargs.get("pre_checkpoint", None)
        self.collect_report_cb = None

    def log_time(self, type_time, delay):
        logging.info("{} {}={}".format(":time:", type_time, delay))

    def log_size(self, type_size, size):
        logging.info("{} {}={}".format(":size:", type_size, size))

    def get_container_name(self):
        return '{}{}'.format(self.service_name, self.end_user)

    def get_checkpoint_folder(self):
        return '{}/{}'.format(self.dump_dir, self.get_container_name())

    def get_snapshot_folder(self):
        return '{}/{}/'.format(self.get_checkpoint_folder(), self.snapshot)

    def get_snapshot_name_pre(self, number=''):
        return '{}_pre{}'.format(self.snapshot, number)

    def get_snapshot_pre(self, number=''):
        return '{}/{}_pre{}/'.format(self.get_checkpoint_folder(),
                                     self.snapshot, number)

    def get_snapshot_delta(self, old=None, new=None):
        if (old is not None) and (new is not None):
            return '{}/{}_delta_{}_{}/'.format(self.get_checkpoint_folder(),
                                              self.snapshot, old, new)
        else:
            return '{}/{}_delta/'.format(self.get_checkpoint_folder(),
                                         self.snapshot)

    def set_container_img(self, container_img):
        self.container_img = container_img

    def get_container_img(self):
        return self.container_img

    def update_ip(self, new_ip):
        self.ip = new_ip

    def update_port(self, new_port):
        self.port = new_port

    def update_container_port(self, new_port):
        self.container_port = new_port

    def get_migrate_service(self):
        return {'snapshot':self.snapshot,
                'end_user':self.end_user,
                'service_name':self.service_name,
                'registry':self.registry,
                'user':self.user,
                'ip':self.ip,
                'server_name':self.server_name,
                'port':self.port,
                'ssid':self.ssid,
                'bssid':self.bssid,
                'container_port':self.container_port,
                'container_img':self.container_img,
                'dump_dir':self.dump_dir,
                'debug':self.debug,
                'method':self.method,
                'request':self.request,
                'time_checkpoint':self.time_checkpoint,
                'time_xdelta':self.time_xdelta,
                'delta_memory':self.delta_memory,
                'pre_checkpoint':self.pre_checkpoint}


