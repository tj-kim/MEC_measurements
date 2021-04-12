import pytest
import time
from ..mqtt_protocol import MqttClient

t1 = 'testMqttTopic1'
t2 = 'testMqttTopic2'

class MyMqttClient(MqttClient):
    def __init__(self, **kwargs):
        super(MyMqttClient, self).__init__(**kwargs)
        self.message_callback_add(t1, self.simple_callback1)
        self.message_callback_add(t2, self.simple_callback2)
        self.test1 = False
        self.test2 = False

    def my_publish(self, topic, payload, qos=1, retain=False):
        self.start_ = time.time()
        self.publish(topic, payload, qos, retain)

    def on_connect(self, client, userdata, flag, rc):
        client.subscribe([(t1,1), (t2,1)])

    def simple_callback1(self, client, userdata, msg):
        print("delay[s] = {}".format(time.time() - self.start_))
        print("***msg {} on topic {} with QoS {}".format(
            msg.payload, msg.topic, msg.qos))
        if msg.payload == 'hello1':
            self.test1 = True
        else:
            pytest.fail('wrong received msg {}'.format(msg.payload))
            self.test1 = False

    def simple_callback2(self, client, userdata, msg):
        print("delay[s] = {}".format(time.time() - self.start_))
        print("***msg {} on topic {} with QoS {}".format(
            msg.payload, msg.topic, msg.qos))
        if msg.payload == 'hello2':
            self.test2 = True
        else:
            pytest.fail('wrong received msg {}'.format(msg.payload))
            self.test2 = False

def test_mqtt_protocol(select_server):
    mqttClient = MyMqttClient(client_id='testMqtt',
        clean_session=True,
        broker_ip= select_server.ip,
        broker_port= select_server.port,
        keepalive=60,
        lwt_topic='LWT/test',
        lwt_payload='Unexpected exit')
    mqttClient.loop_start()
    time.sleep(0.5)
    mqttClient.my_publish(t1, 'hello1')
    time.sleep(0.5)
    mqttClient.my_publish(t2, 'hello2')
    time.sleep(0.5)
    assert mqttClient.test1 == True
    assert mqttClient.test2 == True
