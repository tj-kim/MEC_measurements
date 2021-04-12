"""The discovery service running in each edge node, functions:

- It helps to self discover neighbour edge node, and their offered
    services.
- It also help to discover a new edge node that just joins to the edge
    computing networks.
"""

import yaml

import central_database as db

class Discovery(object):
    """Absact class for discovery service.

    This service can use yaml, or database to get nodes list.
    """

    def __init__(self):
        pass

    def get_server_ip(self, name):
        raise NotImplementedError

class DiscoveryYaml(Discovery):
    """Load AP list from a yaml file.

    Example::

        centre:
        aps:
          - name: "docker1-bts"
            - bssid: '51:3e:aa:49:98:cb'
            - server: "docker1"
          - name: "docker2-bts"
            - bssid: '52:3e:aa:49:98:cb'
            - server: "docker2"
        servers:
          - name: "docker1"
            ip: 10.0.99.10
          - name: "docker2"
            ip: 10.0.99.11
            ...
        end_users:
    """

    def __init__(self, conf):
        super(DiscoveryYaml, self).__init__()
        self.obj = {}
        with open(conf, 'r') as f:
            self.obj = yaml.safe_load(f)
        self.aps = self.obj.get('aps', [])
        self.servers = self.obj.get('servers', [])
        self.centre = self.obj.get('centre', [])

    def get_end_users(self):
        """Gets all username."""
        return self.obj.get('end_users', [])

    def get_centre_ip(self):
        centre_info = self.obj.get('centre', [])
        return centre_info[0].get('ip','')

    def get_server_info(self, name, field, default):
        servers = filter(lambda x: name == x.get('name', ''), self.servers)
        if len(servers) > 0:
            return servers[0].get(field, default)
        else:
            return ''

    def get_placement_bs_model(self):
        placement = self.obj.get('placement_bs', '')
        model = placement.get('model', 'line')
        distance_bs = placement.get('distance_bs', 0)
        number_bs = placement.get('number_bs', 0)
        return (model, number_bs, distance_bs)

    def get_ap_info(self, name, field, default=None):
        return next((m.get(field, default)
                     for m in self.aps if m.get('name','') == name),
                    None)

    def get_server_info_from_name(self, name):
        server = [i for i in self.servers if i.get('name') == name]
        return server[0]

    def get_server_name_from_ip(self, ip):
        return next((m.get('name', '') for m in self.servers
            if m.get('ip', '')==ip), None)

    def get_server_ip(self, name):
        return self.get_server_info(name, 'ip', '')

    def get_server_port(self, name):
        return self.get_server_info(name, 'port', 9889)

    def get_ap_pass(self, name):
        return self.get_ap_info(name, 'passwd', '')

    def get_ap_bssid(self, name):
        return self.get_ap_info(name, 'bssid', '')

    def get_metrics(self, from_node):
        return self.get_server_info(from_node, 'metrics', [])

    def get_metric(self, from_node, to_node):
        metrics = self.get_metrics(from_node)
        return next((m for m in metrics if m.get('name','')==to_node), None)

    def get_ips(self):
        return list(map(lambda x: x.get('ip'), self.servers))

    def get_server_names(self):
        return list(map(lambda x: x.get('name'), self.servers))

    def get_ap_names(self):
        return list(map(lambda x: x.get('name'), self.aps))

class DiscoverySql(Discovery):
    def __init__(self, conf):
        super(DiscoverySql, self).__init__()
        self.db = db.DBCentral(database=conf)

    def get_end_users(self):
        users = self.db.session.query(db.EndUserInfo.name)
        return [i[0] for i in users]

    def get_centre_ip(self):
        return self.db.session.query(db.EdgeServerInfo.ip).\
            filter(db.EdgeServerInfo.name == 'centre').scalar()

    def get_server_name_from_ip(self, ip):
        return self.db.session.query(db.EdgeServerInfo.name).\
            filter(db.EdgeServerInfo.ip == ip).scalar()

    def get_ap_pass(self, name):
        server = self.db.session.query(db.EdgeServerInfo).\
            filter(db.EdgeServerInfo.name == name).first()
        return server.bts_info.pwd

    # def get_server_port(self, name):
    #     return self.db.session.query(db.EdgeServerInfo.port).\
    #         filter(db.EdgeServerInfo.name == name).scalar()

    def get_server_ip(self, name):
        return self.db.session.query(db.EdgeServerInfo.ip).\
            filter(db.EdgeServerInfo.name == name).scalar()

    def get_server_names(self):
        results = self.db.session.query(db.EdgeServerInfo.name)
        return [i[0] for i in results]
