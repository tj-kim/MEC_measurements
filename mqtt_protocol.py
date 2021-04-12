import logging
import paho.mqtt.client as mqtt

class MqttClient(object):
    def __init__(self, **kwargs):
        self.client_id = kwargs.get('client_id', '')
        self.clean_session = kwargs.get('clean_session', True)
        self.broker_ip = kwargs.get('broker_ip', '')
        self.broker_port = kwargs.get('broker_port', 9999)
        self.keepalive = kwargs.get('keepalive', 60)
        self.lwt_topic = kwargs.get('lwt_topic', None)
        self.lwt_payload = kwargs.get('lwt_payload', 'Unexpected exit')
        self.lwt_qos = kwargs.get('lwt_qos', 1)
        self.lwt_retain = kwargs.get('lwt_retain', False)

        self.client = mqtt.Client(client_id=self.client_id,
            clean_session=self.clean_session)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_subscribe = self.on_subscribe
        self.client.on_publish = self.on_publish
        if self.lwt_topic is not None:
            self.client.will_set(self.lwt_topic, self.lwt_payload,
                self.lwt_qos, self.lwt_retain)
        self.client.connect(self.broker_ip, self.broker_port, self.keepalive)
        # self.client.enable_logger(logging.getLogger(__name__))

    def on_connect(self, client, userdata, flags, rc):
        pass
        #raise NotImplementedError

    def subscribe(self, topic_qoss):
        return self.client.subscribe(topic_qoss)

    def on_subscribe(self, client, userdata, mid, granted_qos):
        logging.info("Subscribed mid = {} granted_qos={}".format(mid, granted_qos))

    def unsubscribe(self, topics):
        return self.client.unsubscribe(topics)

    def publish(self, topic, payload=None, qos=1, retain=False):
        rc = self.client.publish(topic, payload, qos, retain)
        return rc

    def on_publish(self, client, userdata, mid):
        pass
        #return self.client.on_publish(self.client, userdata, mid)

    def message_callback_add(self, sub, callback):
        self.client.message_callback_add(sub, callback)

    def on_message(self, client, userdata, msg):
        logging.warn("Unhandled message {} on topic {} with QoS {}".format(
            msg.payload, msg.topic, msg.qos))

    def loop_start(self):
        self.client.loop_start()

    def loop_forever(self, retry_first_connection=False):
        self.client.loop_forever(retry_first_connection=retry_first_connection)

    def disconnect(self):
        self.client.disconnect()

    def loop_stop(self, force=False):
        self.client.loop_stop(force)
