import re
import sys
import json
import signal
import logging
import argparse
import traceback
import collections
from subprocess import check_output
import sys

import yaml
import sched, time
from threading import Timer

import central_database as db
from planner import RSSIPlanner, RandomPlanner, CloudPlanner
from optimization_planner import OptimizationPlanner
import stats_edge
from migrate_node import MigrateNode
from mqtt_protocol import MqttClient
from discovery_edge import DiscoveryYaml
import Constants
from utilities import check_swap_file, handle_exception

INIT_STATE           = 0b000000
RUNNING_STATE        = 0b000001
PRE_MIGRATE_STATE    = 0b000010
PRE_MIGRATED_STATE   = 0b000100
MIGRATE_STATE        = 0b001000
HANDOVER_STATE       = 0b010000
HANDOVERED_STATE     = 0b100000

def handle_timer_trigger(timeout, trigger_pre_mig_cb, args):
    Timer(timeout, trigger_pre_mig_cb, args).start()

class CentralizedController(MqttClient):
    def __init__(self, broker_ip, broker_port, database, **kwargs):
        """
        Planner type:
        - rssi
        - random
        - optimal
        """
        super(CentralizedController, self).__init__(
            client_id='centralizedcontroller',
            clean_session=True,
            broker_ip=broker_ip,
            broker_port=broker_port,
            keepalive=60,
            lwt_topic=Constants.LWT_CENTRE)
        self.message_callback_add(Constants.REGISTER,
                                  self.process_edge_register)
        self.message_callback_add(Constants.MONITOR_EU_ALL,
                                  self.process_monitor_eu)
        self.message_callback_add(Constants.MONITOR_SERVICE_ALL,
                                  self.process_monitor_service)
        self.message_callback_add(Constants.MONITOR_SERVER_ALL,
                                  self.process_monitor_server_status)
        self.message_callback_add(Constants.MONITOR_CONTAINER_ALL,
                                  self.process_monitor_container)
        self.message_callback_add(Constants.MONITOR_EDGE_ALL,
                                  self.process_edge_monitor)
        self.message_callback_add(Constants.MIGRATE_REPORT_ALL,
                                  self.process_migrate_report)
        self.message_callback_add(Constants.DISCOVER,
                                  self.process_discovery)
        self.message_callback_add(Constants.ALLOCATED_ALL,
                                  self.process_allocated)
        self.message_callback_add(Constants.PRE_MIGRATED_ALL,
                                  self.process_pre_migrated)
        self.message_callback_add(Constants.MIGRATED_ALL,
                                  self.process_migrated)
        self.message_callback_add(Constants.HANDOVERED_ALL,
                                  self.process_handovered)
        self.message_callback_add(Constants.LWT_EU_ALL,
                                  self.process_eu_notification)
        self.message_callback_add(Constants.LWT_EDGE_ALL,
                                  self.process_edge_notification)
        method = kwargs.get('planner', 'random')
        self.migrate_method = kwargs.get(Constants.MIGRATE_METHOD,
                                         Constants.PRE_COPY)
        self.db = database
        self.stats = stats_edge.StatsEdgeSql(db_control=self.db)
        if method == Constants.RANDOM_PLAN:
            logging.info("Start RSSI-threshold + random server planner")
            self.planner_type = Constants.RANDOM_PLAN
            self.planner = RandomPlanner(stats=self.stats)
        elif method == Constants.OPTIMIZED_PLAN:
            logging.info("Start predicted RSSI-hysteresis + optimized server planner")
            self.planner_type = Constants.OPTIMIZED_PLAN
            self.planner = OptimizationPlanner(stats=self.stats)
        elif method == Constants.CLOUD_PLAN:
            logging.info("Start cloud plan")
            self.planner_type = Constants.CLOUD_PLAN
            self.planner = CloudPlanner(stats=self.stats)
        else:
            logging.info("Start RSSI-threshold + nearest server planner")
            self.planner_type = Constants.NEAREST_PLAN
            self.planner = RSSIPlanner(stats=self.stats)
        # Store migrating_plan from the time pre-mig till finish handover-mig
        self.migration_state = {}
        self.migrating_plan = {}
        self.handover_plan = {}

    def on_connect(self, client, userdata, flag, rc):
        logging.info("Connected to broker with result code {}".format(rc))
        # subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe([(Constants.REGISTER, 1), (Constants.MONITOR_ALL, 1),
            (Constants.DISCOVER, 1), (Constants.ALLOCATED_ALL, 1),
            (Constants.MIGRATED_ALL, 1), (Constants.LWT_ALL, 1),
            (Constants.PRE_MIGRATED_ALL, 1), (Constants.HANDOVERED_ALL, 1),
            (Constants.MIGRATE_REPORT_ALL, 1)])
        self.publish_list_servers()

    def update_user_monitor_info(self, user_info):
        logging.info("Update user info {}".format(user_info))
        user = user_info[Constants.END_USER]
        aps=user_info[Constants.NEARBY_AP]
        return self.db.update_rssi_monitor(user=user, aps=aps)

    def publish_list_servers(self):
        all_servers = self.db.get_info_all_servers()
        topic = Constants.UPDATED_SERVERS
        payload = json.dumps(all_servers)
        self.publish(topic, payload)
        logging.info('Publish topic {} payload {}'.format(topic, payload))

    def process_edge_register(self, client, userdata, message):
        """Processes a register message from a edge node.

        Edge node register to centralized controller with msg:

        Example::

            {"server_name":edge01,"ip":172.18.37.105,"port":9889,
             "bs":edge01, "bs_x":100.0,"bs_y":125.0}
        """
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            msg_json = yaml.safe_load(msg)
            self.db.register_server(name=msg_json['server_name'],
                                    ip=msg_json['ip'],
                                    bs=msg_json.get('bs', None),
                                    bs_x=msg_json.get('bs_x', None),
                                    bs_y=msg_json.get('bs_y', None),
                                    distance=msg_json['distance'],
                                    rho=msg_json.get('rho', None),
                                    phi=msg_json.get('phi', None))
            self.publish_list_servers()
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_edge_monitor(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        server_in_topic = re.sub("^{}\/".format(Constants.MONITOR_EDGE.replace("/","\/")),
                                 "", topic)
        logging.info("Process topic {}, payload: {}".format(topic, msg))
        try:
            msg_json = yaml.safe_load(msg)
            src_ip = msg_json['src_node']
            dst_ip = msg_json['dest_node']
            server = self.db.get_server_name_from_ip(src_ip)
            dst_server = self.db.get_server_name_from_ip(dst_ip)
            logging.debug("Measure from {} to {}".format(server, dst_server))
            if server_in_topic == server:
                self.db.update_network_monitor(server,
                                               dst_server,
                                               msg_json['latency'],
                                               msg_json['bw'])
            else:
                logging.error('Invalid source node')
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_discovery(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        payload = {}
        try:
            service_json = yaml.safe_load(msg)
            service_json[Constants.MIGRATE_METHOD] = self.migrate_method
            end_user = service_json[Constants.END_USER]
            ssid = service_json[Constants.ASSOCIATED_SSID]
            bts = self.db.get_bts(ssid)
            if bts is None:
                # reject the discovery request
                logging.debug("Unknown client {} at BTS {}".
                    format(end_user, ssid))
                return
            service_name = service_json[Constants.SERVICE_NAME]
            lookup_service = self.db.get_service(end_user)
            # TODO: Improve this code
            formated_service_name ='{}{}'.format(service_name, end_user)
            if lookup_service is not None:
                logging.debug("Found service {}".format(lookup_service.name))
                if lookup_service.name == formated_service_name:
                    if lookup_service.state == 'init':
                        # No need to do anything, wait for edge return result
                        logging.info("Service {} is being deployed".format(service_name))
                        return
                    elif lookup_service.state == 'migration':
                        logging.info("Service {} is under migration".format(service_name))
                        return
                    else:
                        # Re-deploy without optimization
                        topic = '{}/{}'.format(Constants.DEPLOY, lookup_service.server_name)
                        payload = '{}'.format(service_json)
                        self.publish(topic, payload)
                        logging.info('Publish topic {} payload {}'.format(topic, payload))
                        return
                else:
                    # Destroy the old app
                    self.destroy_service(lookup_service)
            # 1. run optimization,
            deployed_server_name = \
                self.planner.place_service(end_user, formated_service_name,
                    service_json.get(Constants.ASSOCIATED_SSID),
                    service_json.get(Constants.ASSOCIATED_BSSID))
            end_user = service_json.get('end_user')
            self.db.register_user(name=end_user,
                    bts=service_json.get(Constants.ASSOCIATED_SSID))
            self.db.initialize_service(formated_service_name,
                                       deployed_server_name,
                                       end_user)
            self.migration_state[end_user] = INIT_STATE
            logging.info("deploy service {} to server {}".
                format(service_json, deployed_server_name))
            topic = '{}/{}'.format(Constants.DEPLOY, deployed_server_name)
            payload = json.dumps(service_json)
            self.publish(topic, payload)
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def trigger_other_planners(self):
        self.db.session.commit()
        migrate_plans = self.planner.compute_plan()
        logging.debug("New plan: {}".format(migrate_plans))
        for plan in migrate_plans:
            service = self.db.get_service(plan.user)
            end_user = plan.user
            source_mig_server_name = service.server_name
            if service is None:
                logging.error("Wrong plan with None service. plan: {}".format(plan))
                continue
            m_state = self.migration_state.get(end_user, None)
            if m_state is None:
                logging.error("Wrong enduser {} trigger optimization".
                    format(end_user))
                return
            # schedule for final migration of the plan.user
            if plan.next_bts != service.user.bts:
                handover_json = {}
                bts = self.db.get_bts(plan.next_bts)
                handover_json[Constants.NEXT_SSID] = bts.name
                handover_json[Constants.NEXT_BSSID] = bts.bssid
                handover_json[Constants.NEXT_PASSWORD] = bts.pwd
                elapsed_time = 0 # convert s to ms
                handover_json[Constants.ELAPSED_TIME] = elapsed_time # in ms
                logging.debug("Trigger handover for user {} msg {}".
                    format(end_user, handover_json))
                # store plan for calling trigger_handover later
                self.handover_plan[end_user] = handover_json
                self.trigger_handover(end_user, handover_json)
                self.migration_state[end_user] |= HANDOVER_STATE
            if plan.next_server != service.server_name:
                if service.state in ['init', Constants.PRE_MIGRATE,
                    Constants.PRE_MIGRATED, Constants.MIGRATE]:
                    logging.warn("Service is ongoing {}. No need to pre_migration".
                        format(service.state))
                    continue
                service.state = Constants.PRE_MIGRATE
                self.migration_state[end_user] |= PRE_MIGRATE_STATE
                # we will modify service_json, keep the service as the old server
                service_json = service.get_json()
                if service_json is None:
                    continue
                logging.info("Pre-migrate user={} to server:{} for service: {}".
                    format(end_user, plan.next_server, service_json))
                # Modify service
                service_json[Constants.SERVER_NAME] = plan.next_server
                service_json['ip'] = self.db.get_server_ip(plan.next_server)
                service_json[Constants.ASSOCIATED_SSID] = plan.next_bts
                payload = json.dumps(service_json)
                topic = '{}/{}'.format(Constants.PRE_MIGRATE, source_mig_server_name)
                self.publish(topic, payload)
                logging.info("*************Publish topic: {}, payload: {}*************".
                    format(topic, payload))
                # store plan for calling trigger_migration later
                store_obj = {'plan':plan, 'service': service_json}
                self.migrating_plan[end_user] = store_obj
                self.trigger_migration(plan, source_mig_server_name, service_json)

    def run_optimization_planner(self, delta_time):
        # This is used for OPTIMIZED_PLAN only
        self.db.session.commit()
        migrate_plans = self.planner.compute_plan(delta_time)
        logging.debug("New plan: {}".format(migrate_plans))
        for plan in migrate_plans:
            service = self.db.get_service(plan.user)
            source_mig_server_name = service.server_name
            if service is None:
                logging.error("Wrong plan with None service. plan: {}".format(plan))
                continue
            # schedule for final migration of the plan.user
            end_user = plan.user
            time_to_pre_mig = self.planner.lifetime_to_pre_mig(end_user,
                plan.next_server, plan.next_bts)
            lifetime_to_mig = self.planner.lifetime_to_mig(end_user,
                plan.next_server, plan.next_bts)
            # Schedule for final-migration and/or handover
            logging.debug("RUN OPTIMIZATION at delta time {}"
                "Estimate ubs[{}/{}/{}] time_to_pre_mig ={}, time_to_mig={}".
                format(delta_time, plan.user, plan.next_bts, plan.next_server,
                    time_to_pre_mig, lifetime_to_mig))
            m_state = self.migration_state.get(end_user, None)
            if m_state is None:
                logging.error("Wrong enduser {} trigger optimization".
                    format(end_user))
                return
            if not (m_state & PRE_MIGRATE_STATE or m_state & PRE_MIGRATED_STATE or\
                m_state & MIGRATE_STATE):
                if plan.next_server != service.server_name:
                    service_json = service.get_json()
                    if service_json is None:
                        continue
                    logging.info("Pre-migrate user={} to server:{} for service: {}".
                    format(end_user, plan.next_server, service_json))
                    # Modify service
                    service_json[Constants.SERVER_NAME] = plan.next_server
                    service_json['ip'] = self.db.get_server_ip(plan.next_server)
                    service_json[Constants.ASSOCIATED_SSID] = plan.next_bts
                    if time_to_pre_mig is not None and time_to_pre_mig < 60:
                        Timer(time_to_pre_mig, self.trigger_pre_migration,
                                (source_mig_server_name, service_json,)).start()
                        # store plan for calling trigger_migration when PRE_MIGRATED
                        store_obj = {'plan':plan, 'service': service_json}
                        self.migrating_plan[end_user] = store_obj
                        if plan.next_bts != service.user.bts:
                            handover_json = {}
                            bts = self.db.get_bts(plan.next_bts)
                            handover_json[Constants.NEXT_SSID] = bts.name
                            handover_json[Constants.NEXT_BSSID] = bts.bssid
                            handover_json[Constants.NEXT_PASSWORD] = bts.pwd
                            elapsed_time = lifetime_to_mig * 1000 # convert s to ms
                            handover_json[Constants.ELAPSED_TIME] = elapsed_time # in ms
                            logging.debug("Store handover plan for user {} msg {}, time to mig {}".
                                format(end_user, handover_json, lifetime_to_mig))
                            # store plan for calling trigger_handover when PRE_MIGRATED
                            self.handover_plan[end_user] = handover_json
                    else:
                        logging.warn("For u-s-nexts [{}-{}-{}] time_to_pre_mig={} > 60s".
                            format(end_user, source_mig_server_name,
                                plan.next_server, lifetime_to_mig))

                # Handover
                elif plan.next_bts != service.user.bts:
                    if lifetime_to_mig is not None and lifetime_to_mig < 2: # less than 5s
                        handover_json = {}
                        bts = self.db.get_bts(plan.next_bts)
                        handover_json[Constants.NEXT_SSID] = bts.name
                        handover_json[Constants.NEXT_BSSID] = bts.bssid
                        handover_json[Constants.NEXT_PASSWORD] = bts.pwd
                        elapsed_time = lifetime_to_mig * 1000 # convert s to ms
                        handover_json[Constants.ELAPSED_TIME] = elapsed_time # in ms
                        logging.debug("Trigger HANDOVER for user {} msg {}, time_to_mig {}".
                            format(end_user, handover_json, lifetime_to_mig))
                        # store plan for calling trigger_handover later
                        self.handover_plan[end_user] = handover_json
                        Timer(lifetime_to_mig, self.trigger_handover,
                            (end_user, handover_json,)).start()
                    else:
                        logging.warn("lifetime_to_mig for u-s-nexts [{}-{}-{}]={} > 2s".
                            format(end_user, source_mig_server_name,
                                plan.next_server, lifetime_to_mig))
            else:
                logging.warn("Service is ongoing {}. No need to pre_migration".
                    format(service.state))

    def trigger_handover(self, end_user, handover_json):
        stored_handover_json = self.handover_plan.get(end_user, None)
        if stored_handover_json is None:
            logging.debug("Plan has been done: {}".format(handover_json))
            return
        m_state = self.migration_state.get(end_user, None)
        if m_state is None:
            logging.error("Wrong trigger handover for uer {}".format(end_user))
            return
        if m_state & HANDOVER_STATE or m_state & HANDOVERED_STATE:
            logging.debug("HANDOVER has been triggered for service {}".
                format(handover_json))
            return
        self.migration_state[end_user] = m_state | HANDOVER_STATE
        topic = '{}/{}'.format(Constants.HANDOVER, end_user)
        payload = json.dumps(handover_json)
        self.publish(topic, payload)
        logging.debug("*******Handover user {}: {}**************".
            format(end_user, handover_json))
        logging.info("Publish topic: {}, payload: {}".format(topic, payload))
        # remove migrating plan
        if self.handover_plan.get(end_user, None) is not None:
            del(self.handover_plan[end_user])

    def trigger_pre_migration(self, source_mig_server_name, service_json):
        end_user = service_json[Constants.END_USER]
        m_state = self.migration_state.get(end_user, None)
        if m_state is None:
            logging.error("Wrong trigger pre_migration")
            return
        if m_state & PRE_MIGRATE_STATE or m_state & MIGRATE_STATE:
            logging.debug("Pre-migration has been triggered for service {}".
                format(service_json))
            return
        self.migration_state[end_user] |= PRE_MIGRATE_STATE
        payload = json.dumps(service_json)
        topic = '{}/{}'.format(Constants.PRE_MIGRATE, source_mig_server_name)
        self.publish(topic, payload)
        logging.debug("*******PRE_MIGRATION source server {}, service: {}**************".
            format(source_mig_server_name, service_json))
        logging.info("*************Publish topic: {}, payload: {}***************".
            format(topic, payload))

    def trigger_migration(self, plan, source_server_name, service_json):
        end_user = plan.user
        m_state = self.migration_state.get(end_user, None)
        if m_state is None:
            logging.error("Wrong trigger")
            return
        if m_state & MIGRATE_STATE:
            logging.debug("Pre-migration has been triggered for service {}".
                format(service_json))
            return
        if m_state == RUNNING_STATE:
            logging.warn("Service is ongoing well State={}. No need to migrate.".
                format(m_state))
            # remove migrating plan
            if self.migrating_plan.get(end_user, None) is not None:
                del(self.migrating_plan[end_user])
            return
        self.migration_state[end_user] |= MIGRATE_STATE
        logging.debug("*******Migrating plan user {}: {}**************".
            format(end_user, plan))
        payload = json.dumps(service_json)
        topic = '{}/{}'.format(Constants.MIGRATE, source_server_name)
        self.publish(topic, payload)
        logging.info("Publish topic: {}, payload: {}".format(topic, payload))
        # remove migrating plan
        if self.migrating_plan.get(end_user, None) is not None:
            del(self.migrating_plan[end_user])

    def process_monitor_eu(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.debug("process topic {}, payload: {}".format(topic, msg))
        try:
            user_info = yaml.safe_load(msg)
            current_rssi = self.update_user_monitor_info(user_info)
            end_user = user_info[Constants.END_USER]
            m_state = self.migration_state.get(end_user, None)
            if m_state is None:
                logging.error("Wrong enduser {} trigger optimization".
                    format(end_user))
                return
            if not (m_state & PRE_MIGRATE_STATE or m_state & PRE_MIGRATED_STATE or\
                m_state & MIGRATE_STATE):
                if self.planner_type == Constants.OPTIMIZED_PLAN:
                    (T_pre_mig_avg, time_to_avg_pre_mig) = \
                        self.planner.lifetime_to_average_pre_mig(end_user)
                    logging.debug("time_to_pre_mig [{}]={}, T_pre_mig_avg[{}]={}".
                        format(end_user, time_to_avg_pre_mig, end_user, T_pre_mig_avg))
                    if time_to_avg_pre_mig is not None:
                       if time_to_avg_pre_mig < 60:
                            #service_state = self.db.get_service_state(end_user)
                            # No trigger pre migration for user doing pre-migrate
                            #if service_state != Constants.PRE_MIGRATE:
                            self.run_optimization_planner(T_pre_mig_avg)
                else: # random or rssi_closest planer trigger by threshold
                    if current_rssi <= Constants.RSSI_THRESHOLD:
                        logging.debug("RSSI={} is bellow threshold, trigger pre-mig".
                        format(current_rssi))
                        self.trigger_other_planners()
            else:
                logging.warn("Service is being migrated. No need to trigger planner.")
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_monitor_service(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.debug("process topic {}, payload: {}".format(topic, msg))
        try:
            service_info = yaml.safe_load(msg)
            violate_sla = self.db.update_eu_service_monitor(service_info)
            if self.planner_type == Constants.OPTIMIZED_PLAN and violate_sla:
                end_user = service_info[Constants.END_USER]
                m_state = self.migration_state.get(end_user, None)
                if m_state is None:
                    logging.error("Wrong enduser {} trigger optimization".
                        format(end_user))
                    return
                if not (m_state & PRE_MIGRATE_STATE or\
                    m_state & PRE_MIGRATED_STATE or\
                    m_state & MIGRATE_STATE):
                    logging.debug("SLA of {} is violated, trigger OPTIMIZATION".
                        format(end_user))
                    #service_state = self.db.get_service_state(end_user)
                    ## No trigger pre migration for user doing pre-migrate
                    #if service_state != Constants.PRE_MIGRATE:
                    self.run_optimization_planner(0)
                else:
                    logging.warn("SLA of {} is violated, service is being migrated.".
                        format(end_user))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_monitor_server_status(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.debug("process topic {}, payload: {}".format(topic, msg))
        try:
            server_info = yaml.safe_load(msg)
            server_name = topic.split('/')[2]
            self.db.update_server_monitor(server_name,
                                          server_info.get('cpu_max', None),
                                          server_info.get('cpu_cores', None),
                                          server_info.get('mem_total', None),
                                          server_info.get('mem_free', None),
                                          server_info.get('disk_total', None),
                                          server_info.get('disk_free', None))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_allocated(self, client, userdata, message):
        """Processes an allocated message from an edge server.

        A sample payload looks like this:

        Example::

            {'container_img': 'ngovanmao/openface:12', 'end_user': 'testdiscover',
            'ssid': 'docker1', 'bssid': '51:3e:aa:49:98:cb', 'ip': '10.0.99.10',
            'container_port': 9999, 'method': 'delta', 'snapshot': 'snapshot',
            'registry': 'ngovanmao', 'dump_dir': '/tmp', 'service_name': 'openface',
            'server_name':'Edge01xxx','debug': True, 'port': 9900, 'user': 'root'}
        """
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            edge_service_json = yaml.safe_load(msg)
            if edge_service_json is not None:
                end_user = edge_service_json[Constants.END_USER]
                # Verify a user only have 1 service
                service = self.db.get_service(end_user)
                node = MigrateNode(**edge_service_json)
                self.migration_state[end_user] = RUNNING_STATE
                logging.debug("Allocating with state[{}]={}".format(end_user,
                    self.migration_state[end_user]))
                if service is not None:
                    state='running'
                    self.db.update_service(node, state)
                else:
                    state='running'
                    self.db.register_service(node, state)
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_pre_migrated(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            service_json = yaml.safe_load(msg)
            if service_json is not None:
                end_user = service_json[Constants.END_USER]
                dest_server = service_json[Constants.SERVER_NAME]
                dest_bts = service_json[Constants.ASSOCIATED_SSID]
                service = self.db.get_service(end_user)
                if service is None:
                    logging.error("Pre-migrated a None service for user {}".
                        format(end_user))
                    return
                service.state = Constants.PRE_MIGRATED
                if self.planner_type != Constants.OPTIMIZED_PLAN:
                    # trigger migration
                    stored_obj = self.migrating_plan.get(end_user, None)
                    if stored_obj is None:
                        logging.error("Lost migrating plan")
                    else:
                        logging.warn("Trigger migration now!!!")
                        plan = stored_obj['plan']
                        stored_json = stored_obj['service']
                        if plan.next_server == dest_server and\
                            plan.next_bts == dest_bts:
                            source_server = service.server_name
                            self.trigger_migration(plan, source_server, stored_json)
                else:
                    m_state = self.migration_state.get(end_user, None)
                    if m_state is None:
                        logging.error("Wrong receive pre_migrated")
                        return
                    self.migration_state[end_user] = m_state | PRE_MIGRATED_STATE
                    lifetime_to_mig = self.planner.lifetime_to_mig(end_user,\
                        dest_server, dest_bts)
                    if lifetime_to_mig is None:
                        logging.error("time_to_mig for usb[{}/{}/{}] is None".
                            format(end_user, dest_server, dest_bts))
                        return
                    logging.debug("PRE_MIGRATED time_to_mig for usb[{}/{}/{}]={}, m_state={}".
                        format(end_user, dest_server, dest_bts, lifetime_to_mig, m_state))
                    if lifetime_to_mig > 200:
                        # Keep running in the same old server
                        service.state = 'running'
                        self.migration_state[end_user] = RUNNING_STATE
                        # remove handover plan
                        if self.handover_plan.get(end_user, None) is not None:
                            del(self.handover_plan[end_user])
                        # remove migrating plan
                        if self.migrating_plan.get(end_user, None) is not None:
                            del(self.migrating_plan[end_user])
                        return
                    if not (m_state & HANDOVER_STATE):
                        handover_json = self.handover_plan.get(end_user, None)
                        if handover_json is not None:
                            logging.warn("The handover was not triggered."
                                "Trigger or schedule now!!!")
                            # update time to mig before planning for handover
                            if lifetime_to_mig > 0:
                                handover_json[Constants.ELAPSED_TIME] =\
                                    lifetime_to_mig * 1000 # convert to ms
                                # offset 0.1s to handover after the service is down.
                                Timer(lifetime_to_mig + 0.1, self.trigger_handover,
                                    (end_user, handover_json,)).start()
                            else:
                                handover_json[Constants.ELAPSED_TIME] = 0
                                Timer(0.1, self.trigger_handover,
                                    (end_user, handover_json,)).start()
                        else:
                            logging.debug("No handover plan")
                    if not (m_state & MIGRATE_STATE):
                        stored_obj = self.migrating_plan.get(end_user, None)
                        if stored_obj is not None:
                            logging.warn("The migration was not triggered."
                                "Trigger or schedule now!!!")
                            plan = stored_obj['plan']
                            stored_json = stored_obj['service']
                            if plan.next_server == dest_server and\
                                plan.next_bts == dest_bts:
                                source_server = service.server_name
                                Timer(lifetime_to_mig, self.trigger_migration,
                                    (plan, source_server, stored_json,)).start()
                        else:
                            logging.debug("No migration plan")
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_migrated(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        try:
            migrated_service_json= yaml.safe_load(msg)
            #migrated_service_json = yaml.safe_load(m_service_str)
            logging.info("migrated service {}".format(migrated_service_json))
            if migrated_service_json is not None:
                migrated_service = MigrateNode(**migrated_service_json)
                state = 'running'
                self.db.update_service(migrated_service, state)
                end_user = migrated_service.end_user
                m_state = self.migration_state.get(end_user, None)
                if m_state is None:
                    logging.error("Wrong receive migrated")
                    return
                self.migration_state[end_user] = RUNNING_STATE
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_handovered(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        end_user = topic.split('/')[1]
        try:
            handovered_json= yaml.safe_load(msg)
            if handovered_json is not None:
                ssid = handovered_json[Constants.ASSOCIATED_SSID]
                bssid = handovered_json[Constants.ASSOCIATED_BSSID]
                self.db.update_end_user_info(end_user, ssid, bssid)
                m_state = self.migration_state.get(end_user, None)
                if m_state is None:
                    logging.error("Wrong receive HANDOVERED")
                    return
                if m_state != RUNNING_STATE:
                    self.migration_state[end_user] = m_state | HANDOVERED_STATE
                    # if only handover involve
                    if not (m_state & PRE_MIGRATE_STATE):
                        self.migration_state[end_user] = RUNNING_STATE
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def destroy_service(self, service):
        topic = '{}/{}'.format(Constants.DESTROY, service.server_name)
        if service.edge_server is None:
            logging.debug("No need to destroy a service in a dead server")
            return
        payload = json.dumps(service.get_json())
        self.publish(topic, payload)
        logging.info("publish topic {}, payload: {}".format(topic, payload))
        end_user = service.user.name
        self.db.delete_obj(service.user)
        self.db.delete_obj(service)
        self.db.session.commit()
        # Intentional leave est_time_users[end_user] for later use
        # self.db.delete_est_time(end_user)

    def process_eu_notification(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        end_user = topic.split('/')[2]
        service = self.db.get_service(end_user)
        if service is not None:
            self.destroy_service(service)

    def process_edge_notification(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("process topic {}, payload: {}".format(topic, msg))
        self.db.session.commit()
        server_name = topic.split('/')[2]
        # remove server and re-deploy service
        redeploying_services = self.db.get_service_with_server(server_name)
        for s in redeploying_services:
            logging.debug('Redeploy: {}'.format(s))
            # find a better place to run these apps
            deployed_server_name = \
                            self.planner.place_service(s.user.name, s.name,
                                                       s.user.bts_info.name,
                                                       s.user.bts_info.bssid)
            service_json = s.get_json()
            topic = '{}/{}'.format(Constants.DEPLOY, deployed_server_name)
            payload = '{}'.format(service_json)
            self.publish(topic, payload)
            logging.info("Publish topic: {}, payload: {}".
                format(topic, payload))
        self.db.remove_server(server_name)

    def process_migrate_report(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("Process topic {}, payload: {}".format(topic, msg))
        report_type = topic.split('/')[1]
        server_name = topic.split('/')[2]
        try:
            msg_json = yaml.safe_load(msg)
            source = msg_json['source']
            dest = msg_json['dest']
            if report_type == 'source':
                if source != server_name:
                    logging.error("Invalid source node")
                    return
                self.db.update_migrate_record_source(**msg_json)
                if self.planner_type == Constants.OPTIMIZED_PLAN:
                    self.db.update_phi(server_name)
                    service_user = msg_json.get('service')
                    T_pre_mig = float(msg_json.get('prepare'))
                    self.db.update_t_pre_mig(service_user, source, dest, T_pre_mig)
            elif report_type == 'dest':
                if dest != server_name:
                    logging.error("Invalid destination node")
                    return
                self.db.update_migrate_record_dest(**msg_json)
                if self.planner_type == Constants.OPTIMIZED_PLAN:
                    self.db.update_rho(server_name)
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

    def process_monitor_container(self, client, userdata, message):
        topic = message.topic
        msg = message.payload
        logging.info("Process topic {}, payload: {}".format(topic, msg))
        try:
            msg_json = yaml.safe_load(msg)
            obj = self.db.update_container_monitor(plan=self.planner_type, **msg_json)
            if obj is None:
                logging.warn("Cannot find the container")
            else:
                logging.debug("Update service: {}".format(obj))
        except yaml.YAMLError:
            logging.error("Error parsing YAML msg {}".format(msg))

def my_exception_handler(exc_type, value, tb):
    logging.error("".join(traceback.format_exception(exc_type, value, tb)))
    logging.error("Uncaught: {} {}".format(value,
                                           traceback.format_exception(exc_type,
                                                                      value,
                                                                      tb)))
    sys.__excepthook__(exc_type, value, tb)
    sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--verbose',
        help="Verbose print debug.",
        action='store_true')
    parser.add_argument(
        '--database_file',
        type=str,
        help="Profile file contains IP, bandwidth, delay between edge servers.",
        required=True)
    parser.add_argument(
        '--log',
        type=str,
        help="Log file",
        default="centre_edge.log")
    parser.add_argument(
        '--log_level',
        type=str,
        help="Log level: INFO (Default), DEBUG.",
        default='INFO')
    parser.add_argument(
        '--profile_file',
        type=str,
        help="Profile file contains IP, bandwidth, delay between edge servers.",
        default="./edge_nodes.yml")
    parser.add_argument(
        '--migrate_method',
        type=str,
        help="Migrate method, either non_live_migration, or pre_copy.",
        default=Constants.PRE_COPY)
    parser.add_argument(
        '--planner',
        type=str,
        help="Planner types: {}, {} (default), {}".
            format(Constants.OPTIMIZED_PLAN, Constants.NEAREST_PLAN,
                Constants.RANDOM_PLAN),
        default=Constants.NEAREST_PLAN)
    args = parser.parse_args()

    edge_nodes = DiscoveryYaml(args.profile_file)

    FORMAT = '%(asctime)-15s [%(levelname)s] [%(filename)s %(lineno)s] %(message)s'
    if args.log_level == 'DEBUG':
        LOG_LVL = logging.DEBUG
    else:
        LOG_LVL = logging.INFO

    check_swap_file(args.log)
    logging.basicConfig(level=LOG_LVL, format=FORMAT, filename=args.log)

    if args.verbose:
        print("Output to stdout")
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logging.Formatter(FORMAT))
        consoleHandler.setLevel(LOG_LVL)
        logging.getLogger('').addHandler(consoleHandler)

    cmd = ["git", "rev-parse", "--short", "HEAD"]
    version = check_output(cmd)
    broker_ip = edge_nodes.get_centre_ip()
    logging.info("Start centralized_controller version {}".format(version))
    check_swap_file(args.database_file, "-l")
    database = db.DBCentral(database=args.database_file)
    server = CentralizedController(broker_ip, Constants.BROKER_PORT, database, \
        planner=args.planner, migrate_method=args.migrate_method)
    sys.excepthook = my_exception_handler
    def quit_gracefully(*args):
        logging.info("Receive SIGTERM signal")
        server.loop_stop(force=True)
        server.db.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, quit_gracefully)

    try:
        server.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        server.loop_stop(force=True)
        print("Saving database")
        server.db.close()
