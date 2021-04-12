from __future__ import division

import re
import os
import time
import logging
import traceback
import contextlib

import Constants

import yaml
import sqlalchemy
from sqlalchemy_utils import force_instant_defaults
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import  PolynomialFeatures
from sklearn.pipeline import Pipeline

from utilities import get_hostname, get_time, find_velocity
import communication_models as comm
from communication_models import log_rssi_model_real as path_loss
import estimator

RSSI_LIMIT = -100

Base = declarative_base()
# The default value of a column is only valid when it is inserted to the
# database. This command makes the default value available when the object is
# created.
force_instant_defaults()

def get_exp_moving_average(rssi, RSSI):
    alpha = 0.5 # 2/(N+1) = 2/(4+1), consider upto last 4 rssis
    #alpha = 0.34 # 2/(N+1) = 2/(5+1), consider upto last 5 rssis
    #alpha = 0.2 # 2/(N+1) = 2/(5+1), consider upto last 5 rssis
    #return rssi
    if RSSI is None:
        return rssi
    else:
        return alpha * rssi + (1-alpha) * RSSI

def build_linear_regression(ts, RSSIs):
    X = np.asarray(ts)
    X = X.reshape(len(X), 1)
    y = np.asarray(RSSIs)
    if len(X) < 2:
        return None, None
    reg = LinearRegression().fit(X, y)
    #print("accuray of linear model {}".format(reg.score(X, y)))
    # R = eta1 * t + eta0
    eta1 =  reg.coef_[0]
    eta0 = reg.intercept_
    return eta1, eta0

def build_log_regression(ts, RSSIs, n=3, A=-30, t_offset=0):
    '''
    ts in microsecond from epoch. We convert to second and build the model
    RSSI = -10n*log10(eta1*t+eta0) + A
    eta1*t+eta0 = 10^-((RSSI - A)/10/n)
    '''
    X = np.asarray(ts)/10**6 # second
    X -= t_offset # second from start
    X = X.reshape(len(X), 1)
    y = np.asarray(RSSIs)
    y_transform = 10**(-(y-A)/(n*5.0))
    # logging.debug("Transform input from {} to {}".format(y, y_transform))
    if len(X) < 2:
        return None, None
    model = Pipeline([('poly', PolynomialFeatures(2)),
                      ('linear', Ridge(alpha=2))])
    result = model.fit(X, y_transform.reshape(len(y),1))
    reg = result.named_steps['linear']
    eta2 = reg.coef_[0][2]
    eta1 = reg.coef_[0][1]
    # print("Coeff: {}".format(reg.coef_))
    eta0 = reg.intercept_[0]
    # print("X: {}".format([ i for i in X]))
    # print("Real: {}".format([i for i in y_transform]))
    print("eta= [{},{},{}]".format(eta2, eta1, eta0))
    # logging.debug("Model for input {} {}: {} {}".format(X_transform,
    #                                                     y_transform,
    #                                                     eta2, eta1,
    #                                                     eta0))
    return eta2, eta1, eta0

def get_estimated_linear_model(eta1, eta0, t):
    return eta1 * t + eta0

def get_estimated_log_model(eta2, eta1, eta0, t, n=3, A=-30, t_offset=0):
    # t and t_offset are in second
    d = np.sqrt(eta2*(t - t_offset)**2 + eta1*(t - t_offset) + eta0)
    return -10.0*n*np.log10(max(d ,1)) + A

class ServiceProfile(Base):
    __tablename__ = 'service_profile'
    name = Column(String, primary_key=True)
    discover_name = Column(String)
    avg_dproc = Column(Float)
    avg_len = Column(Float)

class ServiceInfo(Base):
    __tablename__ = 'service_info'
    name = Column(String, primary_key=True) # service_name + end_user
    container_img = Column(String, ForeignKey('service_profile.name'))
    server_name = Column(String, ForeignKey('edge_server_info.name'))
    port = Column(Integer)
    container_port = Column(Integer)
    dump_dir = Column(String, default='/tmp')
    method = Column(String, default='delta')
    status = Column(String)
    # The cpu was reported as CPU % (it could > 100% if multi cores)
    # The stored value is convert to MHz by multiply with max_cpu of the server
    # Then calculate moving average with alpha =0.2
    cpu = Column(Float) # in MHz
    mem = Column(Float) # in MB
    size = Column(Float) # in MB
    delta_memory = Column(Float) # in B
    pre_checkpoint = Column(Float) # in B
    time_xdelta = Column(Float) # in second
    time_checkpoint = Column(Float) # in second
    state = Column(String) # init, running, pre_migrate,...
    no_request = Column(Integer) # reset counter after migration

    base_service = relationship('ServiceProfile',
                                foreign_keys='ServiceInfo.container_img')
    edge_server = relationship('EdgeServerInfo',
                               foreign_keys='ServiceInfo.server_name')
    user = relationship('EndUserInfo', uselist=False,
                        back_populates='service')

    def get_json(self):
        # This function intents to make this class compatible with MigrateNode
        json_msg = None
        try:
            json_msg = {
                'method': self.method,
                'container_img': self.container_img,
                'end_user': self.user.name,
                'server_name': self.server_name,
                'service_name': re.sub('{}$'.format(self.user.name), '', self.name),
                'ip': self.edge_server.ip,
                'port':self.port,
                'container_port': self.container_port,
                'ssid': self.user.bts,
                'bssid': self.user.bts_info.bssid
            }
        except AttributeError:
            logging.error(traceback.format_exc())
            logging.error("Missing attribute information")
        return json_msg

    def __repr__(self):
        return "<Service(name={}, server={}, user={}, status={})>".\
            format(self.name, self.server_name, self.user, self.status)

class EndUserInfo(Base):
    __tablename__ = 'end_user_info'
    #: User name
    name = Column(String, primary_key=True)
    bts = Column(String, ForeignKey('bts_info.name'))
    service_id = Column(String, ForeignKey('service_info.name'))
    status = Column(Boolean)
    x = Column(Float)
    y = Column(Float)
    a = Column(Float) # y = ax + b
    b = Column(Float)
    velocity_x = Column(Float)
    velocity_y = Column(Float)

    service = relationship('ServiceInfo', foreign_keys='EndUserInfo.service_id',
                           back_populates='user')
    bts_info = relationship('BTSInfo', foreign_keys='EndUserInfo.bts')

    def __repr__(self):
        return "<User(name={}, bts={}, service_id={})>".\
            format(self.name, self.bts, self.service_id)

class EdgeServerInfo(Base):
    __tablename__ = 'edge_server_info'
    name = Column(String, primary_key=True)
    ip = Column(String)
    # 0 is at cloud, add one for each layer toward the edge
    distance = Column(Integer)
    core_cpu = Column(Integer) # number of core
    max_cpu = Column(Integer) # MHz
    ram = Column(Float) # MB
    ram_free = Column(Float) # MB
    disk = Column(Float) # MB
    disk_free = Column(Float) # MB
    phi = Column(Float)
    rho = Column(Float)

    # Create one-to-one relationship between AP and Edge server
    bts_info = relationship('BTSInfo', uselist=False,
                      back_populates='server')

    def __repr__(self):
        return "Server<name={}, ip={}>".format(self.name, self.ip)

class BTSInfo(Base):
    __tablename__ = 'bts_info'
    name = Column(String, primary_key=True)
    ip = Column(String)
    server_id = Column(String, ForeignKey('edge_server_info.name'))
    # TODO: BSSID and name is a pair of primary key
    bssid = Column(String)
    pwd = Column(String, default="")
    x = Column(Float) # 2d-coordinate
    y = Column(Float) # 2d-coordinate

    # Create one-to-one relationship between AP and Edge server
    server = relationship("EdgeServerInfo",
                           back_populates='bts_info')

    def __repr__(self):
        return "BTS<name={}, server={}>".format(self.name, self.server)

class MigrateRecord(Base):
    """
    Migration history of the system.
    """
    __tablename__ = 'migrate_history'
    timestamp = Column(Integer, primary_key=True)
    source = Column(String, ForeignKey('edge_server_info.name'))
    dest = Column(String, ForeignKey('edge_server_info.name'))
    service = Column(String, ForeignKey('service_info.name'))
    method = Column(String)
    pre_checkpoint = Column(Float) # in second
    pre_rsync = Column(Float) # in second
    prepare = Column(Float)
    checkpoint = Column(Float) # in second
    rsync = Column(Float) # in second
    xdelta_source = Column(Float) # in second
    final_rsync = Column(Float) # in second
    migrate = Column(Float)
    premigration = Column(Float)
    xdelta_dest = Column(Float) # in second
    restore = Column(Float)
    size_pre_rsync = Column(Integer) # in byte
    size_rsync = Column(Integer) # in byte
    size_final_rsync = Column(Integer) # in byte

    src_server = relationship('EdgeServerInfo',
                              foreign_keys='MigrateRecord.source')
    dst_server = relationship('EdgeServerInfo',
                              foreign_keys='MigrateRecord.dest')
    service_obj = relationship('ServiceInfo',
                               foreign_keys='MigrateRecord.service')

class NetworkRecord(Base):
    __tablename__ = 'network_monitor'
    timestamp = Column(Integer, primary_key=True)
    src_node = Column(String)
    dest_node = Column(String)
    latency = Column(Float) # in microsecond
    bw = Column(Float) # in Mbps

class EndUserService(Base):
    """
    End users report to this table when they make a request to edge server.
    """
    __tablename__ = 'user_service'
    timestamp = Column(Integer, primary_key=True)
    user_id = Column(String)
    service_id = Column(String, ForeignKey('service_info.name'))
    ssid = Column(String)
    bssid = Column(String)
    server_name = Column(String)
    proc_delay = Column(Float) # unit ms
    e2e_delay = Column(Float) # ms
    request_size = Column(Integer) # unit B

    service = relationship('ServiceInfo',
                           foreign_keys='EndUserService.service_id')

class RSSIMonitor(Base):
    __tablename__ = 'rssi_monitor'
    timestamp = Column(Integer, primary_key=True)
    user_id = Column(String)
    x = Column(Float)
    y = Column(Float)
    bts = Column(String, ForeignKey('bts_info.name'))
    rssi = Column(Float) # measured value
    erssi = Column(Float) # filtered value (with Exp moving average)
    # d = sqrt(eta2*t^2 + eta1*t + eta0)
    eta2 = Column(Float)
    eta1 = Column(Float)
    eta0 = Column(Float)

    bts_info = relationship('BTSInfo', foreign_keys='RSSIMonitor.bts')

    def __repr__(self):
        return "<RSSI(time={}, user={}, bts={}, rssi={},erssi={},eta1={},eta0={})>".\
            format(self.timestamp, self.user_id, self.bts, self.rssi,
            self.erssi, self.eta1, self.eta0)

class EstimateTime(object):
    def __init__(self, end_user):
        self.end_user = end_user
        self.t_pre_mig = {} # in second
        self.t_mig = {} # in second
        self.no_connect = 0 # number source-dest

    def update_time(self, source,dest, t_pre_mig, t_mig):
        logging.debug("update user{} {}-{}: T_pre={}, T_mig={}".
            format(self.end_user, source, dest, t_pre_mig, t_mig))
        self.t_pre_mig[(source, dest)] = t_pre_mig
        self.t_mig[(source, dest)] = t_mig
        self.no_connect += 1

    def update_t_pre_mig(self, source, dest, T_pre_mig):
        logging.debug("update with REAL value user{} {}-{}: T_pre={}".
            format(self.end_user, source, dest, T_pre_mig))
        self.t_pre_mig[(source, dest)] = T_pre_mig

    def get_est_pre_mig_time(self, source, dest):
        T_pre_mig = 0
        if source != dest:
            T_pre_mig = self.t_pre_mig.get((source, dest), None)
        logging.debug("T_pre_mig {}-{}: {}".format(source, dest, T_pre_mig))
        return T_pre_mig # in second

    def get_est_mig_time(self, source, dest):
        T_mig = 0
        if source != dest:
            T_mig = self.t_mig.get((source, dest), None)
        logging.debug("T_mig {}-{}: {}".format(source, dest, T_mig))
        return T_mig # in second

    def get_avg_est_pre_mig_time(self):
        if len(self.t_pre_mig) > 0:
            values = self.t_pre_mig.values()
            return sum(values)/len(values)
        else:
            return None

    def get_max_est_pre_mig_time(self):
        if len(self.t_pre_mig) > 0:
            return max(self.t_pre_mig.values())
        else:
            return None

    def get_max_est_mig_time(self):
        if len(self.t_mig) > 0:
            return max(self.t_mig.values())
        else:
            return None

class DBCentral(object):
    def __init__(self, **kwargs):
        database = kwargs.get('database', '{}central.db'.format(get_hostname()))
        self.engine = sqlalchemy.create_engine('sqlite:///{}'.format(database))
        if not os.path.exists(database):
            Base.metadata.create_all(self.engine)
        else:
            Base.metadata.bind = self.engine
        self.DBSession = sessionmaker(bind=self.engine)
        self.session = self.DBSession()
        self.est_time_users = {}
        self.t0 = time.time()

    def insert_obj(self, obj):
        self.session.add(obj)

    def delete_obj(self, obj):
        if obj is not None:
            self.session.delete(obj)

    def delete_est_time(self, end_user):
        del(self.est_time_users[end_user])

    def close(self):
        self.session.commit()
        self.session.close()

    def clean_database(self):
        """
        A dangerous function, use it with your own risk.
        """
        self.session.commit()
        with contextlib.closing(self.engine.connect()) as con:
            trans = con.begin()
            for table in reversed(Base.metadata.sorted_tables):
                con.execute(table.delete())
            trans.commit()

    def query_bw(self, source, dest, size=10):
        """
        Get average over size samples.
        """
        results = self.session.query(NetworkRecord.bw).\
                  filter(NetworkRecord.src_node == source,
                         NetworkRecord.dest_node == dest).\
                         order_by(sqlalchemy.desc(NetworkRecord.timestamp)).\
                         limit(size)
        results_bw = [i[0] for i in results]
        logging.debug("Most recent BW from {} to {} [Mbps]: {}".\
                      format(source, dest, results_bw))
        if len(results_bw) == 0:
            return 0.001 # 1kbps
        else:
            return sum(results_bw)/len(results_bw)

    def query_bts_to_edge_bw(self, bts, server):
        """Queries BW from BTS to edge server.

        """
        obj = self.session.query(BTSInfo).\
              filter(BTSInfo.name == bts).first()
        if obj is None:
            return 0
        elif obj.server_id == server:
            return 1e9
        else:
            return self.query_bw(obj.server_id, server)

    def query_rtt(self, source, dest, size=10):
        results = self.session.query(NetworkRecord.latency).\
                  filter(NetworkRecord.src_node == source,
                         NetworkRecord.dest_node == dest).\
                         order_by(sqlalchemy.desc(NetworkRecord.timestamp)).\
                         limit(size)
        results_rtt = [i[0] for i in results]
        logging.debug("Most recent RTT from {} to {}: {}".\
                      format(source, dest, results_rtt))
        return sum(results_rtt)/len(results_rtt)

    def query_bts_to_edge_rtt(self, bts, server):
        obj = self.session.query(BTSInfo).\
              filter(BTSInfo.name == bts).first()
        if obj is None:
            return 10e9 # A large number
        elif obj.server_id == server:
            return 0
        else:
            rtt = self.query_rtt(obj.server_id, server)
            logging.debug("bts_to_server_rtt {}-{}={}".
                format(bts, server, rtt))
            #return self.query_rtt(obj.server_id, server)
            return rtt

    def query_process_delay(self, user, bts, server, size=10):
        results = self.session.query(EndUserService.proc_delay).\
                  filter(EndUserService.user_id == user,
                         EndUserService.ssid == bts,
                         EndUserService.server_name == server).\
                         limit(size)
        results_proc = [i[0] for i in results]
        logging.debug("Query proc delay from {} to b-s[{}-{}]. result [ms] {}".
            format(user, bts, server, results_proc))
        if len(results_proc) > 0:
            return sum(results_proc)/len(results_proc)
        else:
            return None

    def query_server_size(self, server):
        results = self.session.query(EdgeServerInfo.disk).\
                  filter(EdgeServerInfo.name==server)
        return results.scalar()

    def query_server_memory(self, server):
        results = self.session.query(EdgeServerInfo.ram).\
                  filter(EdgeServerInfo.name==server)
        return results.scalar()

    def query_average_cpu_container(self, user):
        service = self.get_service(user)
        if service is None:
            logging.error("Cannot found service with user {}".format(user))
            return 0
        else:
            return service.cpu

    def query_size_container(self, user):
        service = self.get_service(user)
        if service is None:
            logging.error("Cannot found service with user {}".format(user))
            return 0
        else:
            return service.size

    def query_memory_container(self, user):
        service = self.get_service(user)
        if service is None:
            return 0
        else:
            return service.mem

    def query_full_capacities(self, server_name):
        server = self.get_server(server_name)
        return server.max_cpu * server.core_cpu

    def query_capacities(self, name):
        result = self.session.query(EdgeServerInfo.max_cpu).\
                 filter(EdgeServerInfo.name == name).scalar()
        return result

    def query_eu_data_size(self, user, size=10):
        results = self.session.query(EndUserService.request_size).\
                 filter(EndUserService.user_id == user).\
                 order_by(sqlalchemy.desc(EndUserService.timestamp)).\
                 limit(10)
        results_data = [i[0] for i in results]
        if len(results_data) > 0:
            return sum(results_data)/len(results_data)
        else:
            return None

    def get_server(self, server_name):
        return self.session.query(EdgeServerInfo).\
                    filter(EdgeServerInfo.name == server_name).first()

    def query_phi(self, server):
        server = self.get_server(server)
        return server.phi

    def query_rho(self, server):
        server = self.get_server(server)
        return server.rho

    def query_cur_assign(self, user):
        """
        This function query the lastest state of an user.
        """
        result = self.session.query(EndUserInfo).\
                  filter(EndUserInfo.name == user,
                         EndUserInfo.status == True).first()
        if result is None:
            return None
        if result.service is None:
            server = None
        else:
            server = result.service.server_name
        return (result.bts, server)

    def update_cur_assign(self, user, bts, server):
        result = self.session.query(EndUserInfo).\
                 filter(EndUserInfo.name == user).first()
        result.bts=bts
        result.service.server_name = server
        self.session.commit()

    def update_server_monitor(self, name, cpu_max, cpu_cores, mem_total,
                              mem_free, disk_total, disk_free):
        obj = self.session.query(EdgeServerInfo).\
              filter(EdgeServerInfo.name==name).first()
        if obj is None:
            return None
        obj.core_cpu = cpu_cores
        obj.max_cpu = cpu_max
        obj.ram = mem_total
        obj.ram_free = mem_free
        obj.disk = disk_total
        obj.disk_free = disk_free

    def update_network_monitor_ip(self, src_ip, dest_ip, latency,
                                  bandwidth):
        source = self.session.query(EdgeServerInfo.name).\
                 filter(EdgeServerInfo.ip == src_ip).scalar()
        dest = self.session.query(EdgeServerInfo.name).\
               filter(EdgeServerInfo.ip == dest_ip).scalar()
        if source is None or dest is None:
            return False
        self.update_network_monitor(source, dest, latency, bandwidth)
        return True

    def update_network_monitor(self, source, dest, latency, bandwidth):
        obj = NetworkRecord(timestamp=get_time(),
                            src_node=source, dest_node=dest,
                            latency=latency, bw=bandwidth)
        self.insert_obj(obj)

    def update_container_monitor(self, **kwargs):
        container = kwargs.get('container', None)
        obj = self.session.query(ServiceInfo).\
              filter(ServiceInfo.name == container).first()
        if obj is None:
            return None
        container_size = kwargs.get('size', None)
        if container_size is None:
            return None
        # convert to int to make sure it's int number instead of str
        container_size = int(container_size)
        delta_memory_size = int(kwargs.get('delta_memory', None))
        pre_checkpoint_size = int(kwargs.get('pre_checkpoint', None))
        time_checkpoint = int(kwargs.get('time_checkpoint', None))
        time_xdelta = int(kwargs.get('time_xdelta', None)) # xdelta diff at source
        obj.status = kwargs.get('status', None)
        max_cpu_server = obj.edge_server.max_cpu
        if max_cpu_server is None:
            logging.error("Update container monitor too soon.\
                Not enough info from server {}".format(obj.server_name))
            return
        avg_cont_cpu = int(kwargs.get('cpu', None)) / 100.0
        avg_cont_cpu = avg_cont_cpu * max_cpu_server
        last_avg_cont_cpu = obj.cpu
        obj.cpu = get_exp_moving_average(avg_cont_cpu, last_avg_cont_cpu)
        obj.mem = int(kwargs.get('mem', None))
        obj.size = container_size
        obj.delta_memory =  delta_memory_size
        obj.pre_checkpoint = pre_checkpoint_size
        obj.time_checkpoint = time_checkpoint
        obj.time_xdelta = time_xdelta
        # update estimate times
        planner = kwargs.get('plan', Constants.NEAREST_PLAN)
        if planner == Constants.OPTIMIZED_PLAN:
            cur_s = obj.server_name
            end_user = obj.user.name
            phi_s = obj.edge_server.phi
            cpu_max_s = obj.edge_server.max_cpu
            cpu_cores_s = obj.edge_server.core_cpu
            t_checkpoint = phi_s * container_size / (cpu_max_s * cpu_cores_s) # in second
            neighbor_servers = self.session.query(EdgeServerInfo).\
                filter(EdgeServerInfo.name != obj.edge_server.name).all()
            for dest in neighbor_servers:
                dest_s = dest.name
                bw_sd = self.query_bw(cur_s, dest_s)
                # Multiple 10^6 to convert bytes to MB
                t_transfer = ((delta_memory_size/1000000)*8) / bw_sd # in second
                t_restore = dest.rho * (container_size + \
                    (pre_checkpoint_size + delta_memory_size)/10**6) /\
                    (dest.core_cpu * dest.max_cpu) # in second
                t_transfer_pre= (max(delta_memory_size, pre_checkpoint_size)*8)/\
                    (10**6*bw_sd) # in second
                logging.debug("t_transfer_pre = max({},{})*8/(10**6*{})".\
                              format(delta_memory_size, pre_checkpoint_size,
                              bw_sd))
                t_pre_mig = t_checkpoint + t_transfer_pre + time_xdelta # in second
                logging.debug("T_pre_mig of {}->{}: {} + {} + {} = {}".\
                              format(container, dest.name, t_checkpoint, t_transfer_pre,
                              time_xdelta, t_pre_mig))
                t_mig = t_checkpoint + t_transfer + t_restore + time_xdelta # in second
                logging.debug("update t_cp ={}, t_trf={}, t_xd={}, T_pre_mig={}, T_mig={}".
                    format(t_checkpoint, t_transfer_pre, time_xdelta, t_pre_mig, t_mig))
                self.est_time_users[end_user].update_time(cur_s, dest_s,
                    t_pre_mig, t_mig)
        self.session.commit()
        return obj

    def query_rssi_predictor(self, user, bs):
        infos = self.session.query(RSSIMonitor).\
              filter(RSSIMonitor.user_id==user, RSSIMonitor.bts==bs).\
              order_by(sqlalchemy.desc(RSSIMonitor.timestamp)).first()
        logging.debug("eta2={}, eta1={}, eta0={}".format(infos.eta2,
                                                         infos.eta1,
                                                         infos.eta0))
        return infos.eta2, infos.eta1, infos.eta0

    def get_est_rssi_bts(self, user, bts, delta_time, model='log'):
        # Delta time is in second
        eta2, eta1, eta0 = self.query_rssi_predictor(user, bts)
        if model == 'linear':
            # Deprecated, TODO: change get_time() to time.time()
            est_rssi = get_estimated_linear_model(eta1, eta0, get_time() + delta_time)
        else:
            est_rssi = get_estimated_log_model(eta2, eta1, eta0,
                                               time.time() + delta_time,
                                               t_offset=self.t0)
        return est_rssi


    def get_est_pre_mig_time(self, user, source, dest):
        return self.est_time_users[user].get_est_pre_mig_time(source, dest)

    def get_est_mig_time(self, user, source, dest):
        if source == dest:
            return 0
        # T_mig is in second
        return self.est_time_users[user].get_est_mig_time(source, dest)

    def query_avg_t_pre_mig(self, user):
        T_pre_mig_avg = self.est_time_users[user].get_avg_est_pre_mig_time()
        logging.debug("T_pre_mig_avg[{}](s)={}".format(user, T_pre_mig_avg))
        return T_pre_mig_avg

    def query_max_t_pre_mig(self, user):
        T_pre_mig_max = self.est_time_users[user].get_max_est_pre_mig_time()
        logging.debug("T_pre_mig_max[{}]={}".format(user, T_pre_mig_max))
        return T_pre_mig_max

    def query_max_t_mig(self, user):
        return self.est_time_users[user].get_max_est_mig_time()

    def query_neighbor(self, user, timeout=300000000):
        """Gets all BS in the user's vicinity.

        Args:
            user (str): user name
            timeout (int): in microseconds. The default value is 5
                minutes
        """
        min_time = get_time() - timeout
        bts_list = self.session.query(RSSIMonitor).\
                   filter(RSSIMonitor.user_id == user,
                          RSSIMonitor.timestamp > min_time).\
                   group_by(RSSIMonitor.bts).\
                   order_by(sqlalchemy.desc(RSSIMonitor.timestamp)).\
                   all()
        logging.debug("Query neighbor: {}".format(bts_list))
        return bts_list

    def query_estimated_neighbor(self, user, thresh, time):
        r"""Queries suitable BS for optimization.

        This function returns all BSs that sastisfy the condition:

        .. math::
            \max{\{ \text{RSSI}_{ub'}^{t}, \widehat{\text{RSSI}}_{ub'}^{t'} \} }
            < \text{RSSI}_{\min}

        Args:
            user (str): user name
            thresh (float): :math:`\text{RSSI}_{\min}`
            time (float): estimated time in seconds

        Returns:
            A list of BTS objects.
        """
        bts_list = [ i.bts for i in self.query_neighbor(user)]
        user_obj = self.get_user(user)
        new_pos = estimator.estimate_new_position(
            (user_obj.x, user_obj.y),
            (user_obj.velocity_x, user_obj.velocity_y),
            time)
        # Calculates distance for each BTS
        distances = [estimator.estimate_new_position((b.bts.x,b.bts.y),
                                                     new_pos)
                     for b in bts_list]
        # Calculates RSSI for each BTS
        rssi = [path_loss(d) for d in distances]
        # Filters the result
        return [ i[1].bts for i in zip(rssi, bts_list)
                 if max(i[0], i[1].rssi) > thresh ]

    def get_est_handover_time(self, user, src_bs, dst_bs):
        if src_bs == dst_bs:
            return 0
        # TODO: find a reference for the number WiFi
        T_ho = 0.5 #s
        return T_ho

    def get_handover_time_distance(self, user, src_bs, dst_bs, hys=7.0,
                                   n=3, A=-30):
        eta2_src, eta1_src, eta0_src = \
            self.query_rssi_predictor(user, src_bs)
        eta2_dst, eta1_dst, eta0_dst = \
            self.query_rssi_predictor(user, dst_bs)
        if eta2_src is None or eta2_dst is None:
            return None
        try:
            omega = 10**(hys/(5*n))
            coeff = [eta2_src - omega*eta2_dst,
                     eta1_src - omega*eta1_dst,
                     eta0_src - omega*eta0_dst]
            roots = np.roots(coeff)
            logging.debug("The equation {} has roots:{}".format(coeff,
                                                                roots))
            # Select the correct root: the smallest number lager than
            # current time
            if not all(np.isreal(roots)):
                logging.debug("Cannot found real solution")
                return None
            roots = sorted(roots) # Sort roots in accending order
            t_ho = next((i for i in roots if i > 0), None)
            if t_ho is None:
                t_ho = roots[0]
                logging.debug("Cannot found a future solution, "
                              "return a past solution {}".format(t_ho))
                return None
            # t_ho = (R_usrc-R_udst+hys)/(eta_udst - eta_usrc)
            till_handover = t_ho - get_time()/10**6 + self.t0
            logging.debug("est elapsed time u-s-d [{}-{}-{}], "
                          "hys={} till handover {}".\
                          format(user, src_bs, dst_bs, hys,
                                 till_handover))
            return till_handover # second
        except ZeroDivisionError:
            logging.error("Division by zero")
            return None

    def get_handover_time(self, user, src_bs, dst_bs, hys=7.0, n=3,
                          A=-30):
        """Finds the time to start handover of a user.

        Args:
            user (str): user name
            src_bs (str): name of the current base station.
            dst_bs (str): name of the destination base station
            hys (float): the threshold of signal strength at which the
                use start to handover.

        Returns:
            Time before handover in seconds.
        """
        user_obj = self.get_user(user)
        src_bs_obj = self.get_bts(src_bs)
        dst_bs_obj = self.get_bts(dst_bs)
        points = estimator.find_handover_points(
            user_obj.a, user_obj.b,
            (src_bs_obj.x, src_bs_obj.y),
            (dst_bs_obj.x, dst_bs_obj.y),
            hys, n, A)
        if points is None:
            # Cannot found real solution
            return None
        # Selects one of two solution
        times = [estimator.find_remain_time((user_obj.x, user_obj.y),
                                              point,
                                              (user_obj.velocity_x,
                                               user_obj.velocity_y))
                 for point in points]
        times = sorted(times)
        if times[0] >= 0:
            t_ho = times[0]
        elif times[1] >= 0:
            t_ho = times[1]
        else:
            logging.debug("Cannot found any future solution, "
                          "past solutions: {}".format(times))
            return None
        logging.debug("est elapsed time u-s-d [{}-{}-{}], "
                      "hys={} till handover {}".\
                      format(user, src_bs, dst_bs, hys,
                             t_ho))
        return t_ho

    def add_service(self, service):
        self.insert_obj(service)

    def update_end_user_info(self, end_user, ssid, bssid):
        user = self.get_user(end_user)
        user.bts = ssid
        user.bts_info.bssid = bssid
        self.session.commit()
        logging.debug("updated end user {}".format(user))

    def update_service(self, migrate_node, state):
        """
        Update node using migrate node object
        """
        new_service = self.get_service(migrate_node.end_user)
        if new_service is not None:
            new_service.name = migrate_node.get_container_name()
            new_service.container_img = migrate_node.get_container_img()
            new_service.server_name = migrate_node.server_name
            new_service.port = migrate_node.port
            new_service.method = migrate_node.method
            new_service.container_port = migrate_node.container_port
            new_service.dump_dir = migrate_node.dump_dir
            new_service.state = state
            new_service.no_request //= 2
            self.session.commit()
        logging.debug("updated service {}".format(new_service))

    def initialize_service(self, service_user_name, server_name, end_user):
        logging.debug("init server {}".format(server_name))
        service_info = ServiceInfo(name=service_user_name,
                                   server_name=server_name,
                                   no_request=0,
                                   state='init')
        self.insert_obj(service_info)
        end_user = self.session.query(EndUserInfo).\
                   filter(EndUserInfo.name == end_user).scalar()
        end_user.service_id = service_info.name
        end_user.server_name = service_info.server_name
        self.session.commit()
        logging.debug("initialize service {}".format(service_info))

    def register_service(self, migrate_node, state):
        try:
            service_info = ServiceInfo(name=migrate_node.get_container_name(),
                                       container_img=migrate_node.get_container_img(),
                                       container_port=migrate_node.container_port,
                                       dump_dir=migrate_node.dump_dir,
                                       port=migrate_node.port,
                                       method=migrate_node.method,
                                       server_name=migrate_node.server_name,
                                       state=state, no_request=0)
            self.insert_obj(service_info)
            end_user = self.session.query(EndUserInfo).\
                       filter(EndUserInfo.name == migrate_node.end_user).scalar()
            end_user.service_id = service_info.name
            end_user.server_name = service_info.server_name
            self.session.commit()
        except AttributeError:
            logging.error("Failed to register service {}, state={}".
                format(migrate_node, state))

    def query_number_request(self, end_user):
        service = self.get_service(end_user)
        no_request = service.no_request
        return no_request

    def get_service(self, end_user):
        user = self.session.query(EndUserInfo).\
                  filter(EndUserInfo.name == end_user).first()
        if user is None:
            return None
        else:
            return user.service

    def get_service_state(self, end_user):
        service = self.get_service(end_user)
        if service is None:
            return None
        else:
            state = service.state
            logging.debug("service state of {}={}".format(end_user, state))
            return service.state

    def get_service_with_server(self, server):
        servers = self.session.query(ServiceInfo).\
               filter(ServiceInfo.server_name == server)
        return list(servers)

    def get_server_name_from_ip(self, ip):
        return self.session.query(EdgeServerInfo.name).\
            filter(EdgeServerInfo.ip == ip).scalar()

    def add_new_server(self, server):
        self.insert_obj(server)
        self.session.commit()

    def get_server_names_with_distance(self, distance):
        query_obj = self.session.query(EdgeServerInfo.name).\
            filter(EdgeServerInfo.distance == distance).all()
        return [ s[0] for s in query_obj ]

    def get_server_names(self):
        query_obj = self.session.query(EdgeServerInfo.name)
        return [ s[0] for s in query_obj ]

    def get_server_ip(self, name):
        return self.session.query(EdgeServerInfo.ip).\
            filter(EdgeServerInfo.name == name).scalar()

    def register_bts(self, **kwargs):
        bts_name = kwargs.get('name', None)
        if bts_name is None:
            logging.error('Cannot register bts without its ID')
            return
        if self.get_bts(bts_name) is not None:
            logging.error('Cannot register an existing BTS.')
            return
        obj = BTSInfo(name=bts_name,
                      bssid=kwargs.get('bssid', None),
                      pwd = kwargs.get('passwd', ''),
                      x = kwargs.get('x', 0),
                      y = kwargs.get('y', 0))
        self.insert_obj(obj)
        self.session.commit()

    def register_server(self, **kwargs):
        # TODO Verify user before register
        name = kwargs.get('name')
        server_info = self.session.query(EdgeServerInfo).\
                      filter(EdgeServerInfo.name == name).first()
        if server_info is None:
            server_info = EdgeServerInfo(name=kwargs.get('name'),
                                         ip=kwargs.get('ip'),
                                         distance=kwargs.get('distance'),
                                         rho=kwargs.get('rho', None),
                                         phi=kwargs.get('phi', None))
        bts_name = kwargs.get('bs', None)
        # Verify bs in database:
        if bts_name is not None:
            bts = self.session.query(BTSInfo).\
                  filter(BTSInfo.name == bts_name).first()
            if bts is None:
                server_info.bts_info = BTSInfo(name=bts_name,
                                           x=kwargs.get('bs_x', 0),
                                           y=kwargs.get('bs_y', 0),
                                           bssid=kwargs.get('bssid',''))
            else:
                server_info.bts_info = bts
        else:
            server_info.bts_info = None
        self.insert_obj(server_info)
        self.session.commit()

    def get_info_all_servers(self):
        ret = []
        objs = self.session.query(EdgeServerInfo)
        for s in objs:
            s_dict = {'server_name': s.name,
                      'ip': s.ip,'distance':s.distance}
            if s.bts_info is not None:
                s_dict['bs'] = s.bts_info.name
            ret.append(s_dict)
        return ret

    def remove_server(self, name):
        server = self.session.query(EdgeServerInfo).\
                 filter(EdgeServerInfo.name == name).first()
        self.delete_obj(server)
        self.session.commit()

    def is_associated_bts(self, bts):
        btss = self.get_bts_names()
        return bts in btss

    def get_bts_names(self):
        query_obj = self.session.query(BTSInfo.name)
        return [ s[0] for s in query_obj ]

    def get_bts(self, name):
        """Gets a BTS object.

        Args:
            name (str): BTS name.
        """
        query_obj = self.session.query(BTSInfo).\
                    filter(BTSInfo.name == name).first()
        return query_obj

    def get_user_names(self):
        query_obj = self.session.query(EndUserInfo.name)
        return [ s[0] for s in query_obj ]

    def get_user(self, end_user):
        query_obj = self.session.query(EndUserInfo).\
                    filter(EndUserInfo.name == end_user).first()
        return query_obj

    def register_user(self, **kwargs):
        # Verify user before register
        end_user = kwargs.get('name')
        user = self.session.query(EndUserInfo).\
               filter(EndUserInfo.name == end_user).first()
        if user is None:
            user_info = EndUserInfo(name=kwargs.get('name'), bts=kwargs.get('bts'),
                                status=True)
            self.insert_obj(user_info)
        else:
            user.bts = kwargs.get('bts')
        self.session.commit()
        if self.est_time_users.get(end_user, None) is None:
            self.est_time_users[end_user] = EstimateTime(end_user)
            # otherwises, inherit old estimations.

    def update_eu_position(self, user_name, x, y, vx, vy, a, b):
        user = self.session.query(EndUserInfo).\
                filter(EndUserInfo.name == user_name).first()
        if user is None:
            logging.error("Empty user, cannot update")
        else:
            user.x = x
            user.y = y
            user.velocity_x = vx
            user.velocity_y = vy
            user.a = a
            user.b = b
        self.session.commit()

    def update_eu_service_monitor(self, eu_service):
        """Updates service monitor.

        Example::

            {'startTime[ns]':3799849462390626,
            'endTime[ns]':3799849817351511,
            'processTime[ms]':301.27978515625,
            'sentSize[B]':5765,
            'end_user':'Userd8e999d3c22e8f60',
            'service_name':'openface',
            'ssid':'edge01',
            'bssid':'52:3e:aa:49:98:cb'}

       .. todo::

            Define SLA properly

        """

        violate_sla = False
        t = get_time() # us
        # TODO: how to define SLA properly
        SLA_E2E_DELAY = 700 #ms
        try:
            end_user = eu_service[Constants.END_USER]
            e2e_delay = (eu_service['endTime[ns]'] - eu_service['startTime[ns]'])\
                    / (10.0**6)
            proc_delay = eu_service['processTime[ms]']
            running_service = self.get_service(end_user)
            if running_service is None:
                return violate_sla
            trans_delay = e2e_delay - proc_delay
            # TODO:
            # if e2e_delay > SLA_E2E_DELAY: #ms
            if trans_delay > 50: #ms
                logging.info("Service {} is violated SLA, E2E d={}, trans_delay={}".
                    format(running_service, e2e_delay, trans_delay))
                violate_sla = True
            request_size = eu_service['sentSize[B]']
            # handle the case mobile EU leaves ungraceful, but the monitoring service
            # msg lately arrives to the centralized_controller.
            server_name = running_service.server_name
            service_id = '{}{}'.format(eu_service[Constants.SERVICE_NAME], end_user)
            obj = EndUserService(timestamp=t, user_id=end_user,
                service_id = service_id, ssid=eu_service[Constants.ASSOCIATED_SSID],
                bssid=eu_service[Constants.ASSOCIATED_BSSID], server_name=server_name,
                proc_delay=proc_delay, request_size=request_size, e2e_delay=e2e_delay)
            self.insert_obj(obj)
            # increase no request
            service = self.get_service(end_user)
            if service is not None:
                service.no_request += 1
            else:
                logging.warn("Mismatch service None and end user {}".
                    format(end_user))
        except:
            logging.error("Wrong report monitor service message {}".format(eu_service))
            logging.error(traceback.format_exc())
        return violate_sla

    def query_last_position(self, user, bts, p=5):
        infos = self.session.query(RSSIMonitor).\
              filter(RSSIMonitor.user_id==user, RSSIMonitor.bts==bts).\
              order_by(sqlalchemy.desc(RSSIMonitor.timestamp)).\
              limit(p).all()
        ts = [i.timestamp for i in infos[::-1]]
        x = [i.x for i in infos[::-1]]
        y = [i.y for i in infos[::-1]]
        return ts, x, y

    def query_last_eRSSIs(self, user, bts, p=5):
        infos = self.session.query(RSSIMonitor).\
              filter(RSSIMonitor.user_id==user, RSSIMonitor.bts==bts).\
              order_by(sqlalchemy.desc(RSSIMonitor.timestamp)).\
              limit(p).all()
        #logging.debug("rssis = {}".format(infos))
        ts = [i.timestamp for i in infos[::-1]]
        erssi = [i.erssi for i in infos[::-1]]
        return ts, erssi

    def get_current_bts(self, end_user):
        user = self.session.query(EndUserInfo).\
                      filter(EndUserInfo.name == end_user).first()
        logging.debug("User {} connect to {}".format(user, user.bts_info))
        return user.bts_info

    def get_current_bts_ssid(self, end_user):
        current_bts_ssid = self.session.query(EndUserInfo.bts).\
                      filter(EndUserInfo.name == end_user).scalar()
        return current_bts_ssid

    def get_current_server(self, end_user):
        service = self.get_service(end_user)
        return service.server_name

    def get_user_location(self, user_name):
        user = self.get_user(user_name)
        return user.x, user.y

    def get_user_velocity(self, user_name):
        user = self.get_user(user_name)
        return user.velocity_x, user.velocity_y

    def get_user_trajectory(self, user_name):
        user = self.get_user(user_name)
        # y = ax + b
        return user.a, user.b

    def find_user_location(self, aps):
        """Finds user location.

        Input: at lest three RSSI values from three nearby BSs

        Actions:
            1. find distances between user and BSs
            2. find a location of user
        """
        # Choose thoree strongest RSSIs
        three_aps = sorted(aps, key=lambda x: x['level'])[-3:]
        x, y = 0, 0
        if len(three_aps) == 3:
            r1 = comm.distance(three_aps[0][Constants.RSSI])
            bts1 = self.get_bts(three_aps[0][Constants.SSID])
            x1 = bts1.x
            y1 = bts1.y
            r2 = comm.distance(three_aps[1][Constants.RSSI])
            bts2 = self.get_bts(three_aps[1][Constants.SSID])
            x2 = bts2.x
            y2 = bts2.y
            r3 = comm.distance(three_aps[2][Constants.RSSI])
            bts3 = self.get_bts(three_aps[2][Constants.SSID])
            x3 = bts3.x
            y3 = bts3.y
            A = np.array([
                [2*(x2-x1), 2*(y2-y1)],
                [2*(x3-x1), 2*(y3-y1)]
                 ])
            b = np.array([(x2**2-x1**2)+(y2**2-y1**2)-(r2**2-r1**2),
                          (x3**2-x1**2)+(y3**2-y1**2)-(r3**2-r1**2)])
            x, y = np.linalg.solve(A, b)
        logging.info('location x={}, y={}'.format(x, y))
        return x, y

    def update_rssi_monitor(self, **kwargs):
        """
        1. calculate filtered RSSI with exponential moving average
        2. Build linear regression model with recent p filtered RSSIs
        3. Store all measured rssi, filtered rssi, and linear regression model
        """
        user = kwargs['user']
        aps = kwargs['aps']
        current_rssi = 0
        current_bts = self.get_current_bts_ssid(user)
        if current_bts is None:
            return current_rssi
        x, y = self.find_user_location(aps)
        ts, last_x, last_y = self.query_last_position(user, current_bts, 5)
        last_x.append(x)
        last_y.append(y)
        ts.append(get_time())
        # find a trajectory approximation
        a, b = build_linear_regression(last_x, last_y)
        # find velocity
        vx = find_velocity(last_x, ts)
        vy = find_velocity(last_y, ts)
        # store to the EndUserInfo table
        self.update_eu_position(user, x, y, vx, vy, a, b)
        # Store nearby RSSI values to RSSIMonitor table
        for ap in aps:
            timestamp = get_time()
            rssi = ap[Constants.RSSI]
            if rssi < RSSI_LIMIT:
                continue
            if current_bts == ap[Constants.SSID]:
                current_rssi = rssi
            bts = ap[Constants.SSID]
            if not self.is_associated_bts(bts):
                logging.debug("The bts {} does not belong to edge system.".
                    format(bts))
                continue
            p = 10
            ts, last_eRSSIs = self.query_last_eRSSIs(user, bts, p)
            if len(last_eRSSIs) < p:
                erssi = rssi
                obj = RSSIMonitor(timestamp=timestamp,
                              user_id=user,
                              x=x,
                              y=y,
                              bts=bts,
                              #TODO: bssid=ap[Constants.BSSID],
                              rssi=rssi,
                              erssi=erssi)
            else:
                #print("last_eRSSIs {}, last_eRSSIs[0]={}".format(last_eRSSIs,last_eRSSIs[0]))
                erssi = get_exp_moving_average(rssi, last_eRSSIs[-1])
                ts.append(timestamp)
                last_eRSSIs.append(erssi)
                #print("ts={}, last_eRSSIs={}".format(ts, last_eRSSIs))
                #eta1, eta0 = build_linear_regression(ts, last_eRSSIs) # eta, R
                eta2, eta1, eta0 = build_log_regression(ts, last_eRSSIs, t_offset=self.t0)
                obj = RSSIMonitor(timestamp=timestamp,
                                  user_id=user,
                                  bts=bts,
                                  x=x,
                                  y=y,
                                  #TODO: bssid=ap[Constants.BSSID],
                                  rssi=rssi,
                                  erssi=erssi,
                                  eta2=eta2,
                                  eta1=eta1,
                                  eta0=eta0)
            self.insert_obj(obj)
        #self.session.commit()
        return current_rssi

    def update_migrate_record_source(self, **kwargs):
        obj = MigrateRecord(timestamp=get_time(), **kwargs)
        obj.restore = None
        self.insert_obj(obj)

    def update_migrate_record_dest(self, timeout=60000000, **kwargs):
        # The default timeout is 1 minutes
        source = kwargs['source']
        dest = kwargs['dest']
        service = kwargs['service']
        now = get_time()
        obj = self.session.query(MigrateRecord).\
              filter(MigrateRecord.source == source,
                     MigrateRecord.dest == dest,
                     MigrateRecord.service == service,
                     MigrateRecord.restore.is_(None)).\
                     order_by(sqlalchemy.desc(MigrateRecord.timestamp)).\
                     first()
        if obj is not None:
            if obj.timestamp < (now - timeout):
                return None
            obj.restore = kwargs.get('restore', 0)
            obj.xdelta_dest = kwargs.get('xdelta_dest', None)
            return obj
        return None

    def update_t_pre_mig(self, service_user, source, dest, T_pre_mig):
        service  = self.session.query(ServiceInfo).\
                  filter(ServiceInfo.name == service_user).first()
        end_user = service.user.name
        self.est_time_users[end_user].update_t_pre_mig(source, dest, T_pre_mig)

    def update_phi(self, server_name, size=20):
        checkpoints = self.session.query(MigrateRecord).\
            filter(MigrateRecord.source == server_name).\
                  order_by(sqlalchemy.desc(MigrateRecord.timestamp)).\
                  limit(size)
        try:
            checkpoints_data = [
                (i.src_server.max_cpu*i.src_server.core_cpu*i.checkpoint)/
                (i.service_obj.size) for i in checkpoints]
            if len(checkpoints_data) > 0:
                phi = sum(checkpoints_data)/len(checkpoints_data)
                logging.debug("phi of server {}: {}".format(server_name, phi))
                server = self.get_server(server_name)
                server.phi = phi
        except AttributeError:
            logging.error("service is stopped, no need update phi for {}".
                format(server_name))

    def update_rho(self, server_name, size=20):
        restores = self.session.query(MigrateRecord).\
                  filter(MigrateRecord.dest == server_name).\
                  order_by(sqlalchemy.desc(MigrateRecord.timestamp)).\
                  limit(size)
        try:
            restores_data = [
                (i.dst_server.max_cpu*i.dst_server.core_cpu*i.restore)/\
                (i.service_obj.size +
                (i.size_rsync+i.size_pre_rsync+i.size_final_rsync)/1000000)
                # Convert to MB
                for i in restores]
            if len(restores_data) > 0:
                rho = sum(restores_data)/len(restores_data)
                logging.debug("rho of server {}: {}".format(server_name, rho))
                server = self.get_server(server_name)
                server.rho = rho
        except AttributeError:
            logging.error("service is stopped, no need update rho for {}".
                format(server_name))

    def get_max_rssi_threshold_bts(self, user, timeout=60*10**6,
                                   thresh=Constants.RSSI_THRESHOLD):
        """Get the max RSSI BTS if the current BTS's RSSI is below threshold.

        """

        cur_bts = self.get_current_bts(user)
        if cur_bts is None:
            return None
        cur_bts_ssid = cur_bts.name
        cur_rssi = self.query_newest_rssi_bts(user, cur_bts_ssid, timeout)
        logging.debug("Current RSSI {}".format(cur_rssi))
        if cur_rssi < thresh:
            return self.get_max_rssi_bts(user, timeout)
        else:
            return None

    def get_max_rssi_bts(self, user, timeout=60*10**6):
        # The default timeout is 1 minutes, timeout is in microsecond
        self.session.commit()
        bts_list = self.query_neighbor(user, timeout)
        logging.debug("BTS list: {}".format(bts_list))
        if len(bts_list) != 0:
            record = max(bts_list, key=lambda x: x.rssi)
            return record.bts_info
        else:
            return None

    def query_newest_rssi_bts(self, user, bts, timeout=60*10**6):
        self.session.commit()
        bts_list = self.query_neighbor(user, timeout)
        return next((i.rssi for i in bts_list if i.bts == bts), None)

    def get_bts_info(self, name, bssid):
        # Now, we don't care about BSSID but we will add bssid filter later
        ap = self.session.query(BTSInfo).filter(BTSInfo.name==name).first()
        return ap

    def valid_info(self):
        # Check container information
        obj = self.session.query(ServiceInfo).\
            filter(ServiceInfo.size.is_(None)).first()
        if obj is None:
            logging.debug("List {}".\
                          format(self.session.query(ServiceInfo).all()))
            return True
        else:
            logging.debug("Missing information on: {}".\
                          format(self.session.query(ServiceInfo).all()))
            return False
