# MQTT BRIDGE TO THINGSPEAK
# - Subscribe to local MQTT Broker containing data from local sensors
# - Filter data to the subset to send to ThingSpeak Cloud service
# - Publish filtered data to our ThingSpeak channel

from __future__ import print_function
import sys
# Use Paho MQTT library to connect to local MQTT broker
# Main methods of the paho mqtt library are:
# - publish, subscribe, unsubscribe, connect, disconnect
import paho.mqtt.client as mqtt
import time
import math
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json
import configparser
import argparse

class Setting(object):

    def __init__(self, cfg_path):
        self.cfg = configparser.ConfigParser()
        self.cfg.read(cfg_path)

    def get_setting(self, section, my_setting):
        try:        
            ret = self.cfg.get(section, my_setting)
        except configparser.NoOptionError:
            ret = None
        return ret

    def get_topics(self):
        try:
            # get topics defined in section with this name
            ret = self.cfg['MQTT_TOPICS']
        except configparser.NoOptionError:
            ret = None
        return ret

def http_request():
    # Function to send the POST request to ThingSpeak channel for bulk update.
    global messageBuffer
    data_dict = {'write_api_key': writeApiKey, 'updates': messageBuffer}
    # Format json data as string rather than Python dict, then byte encode.
    json_data = json.dumps(data_dict).encode('utf-8')
    eprint("data: %s" % (json_data, ))
    request_headers = {"User-Agent": "mw.doc.bulk-update (Raspberry Pi)", \
                       "Content-Type": "application/json", \
                       "Content-Length": str(len(json_data))}
    req = Request(url=url, data=json_data, headers=request_headers, method='POST')
    eprint("sending URL request to ThingSpeak")
    try:
        response = urlopen(req) # Make the request
        eprint(response.read().decode())
        eprint(response.getcode())  # A 202 indicates success
    except Exception as inst:
        eprint(type(inst))  # the exception instance
        eprint(inst.args)  # arguments stored in .args
        eprint(inst)  # __str__ allows args to be printed directly
        pass
    messageBuffer = []  # Reinitialize the message buffer


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    global topicList
    eprint("Connected with result code " + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(topicList)


def on_disconnect(client, userdata, rc):
    eprint("disconnecting reason " + str(rc))


def on_log(client, userdata, level, buf):
    # print("on_log")
    eprint("log: %s" % (buf, ))


# The callback for when a PUBLISH message is received
# from the server that matches our subscription.
# Note: msg is of message class with members: topic, qos, payload, retain
def on_message(client, userdata, msg):
    global lastThingspeakTime
    global thingspeakMaxInterval
    global thingspeakMinInterval
    global messageBuffer
    global topics

    message = {}

    # Lookup dictionary of topics to find which Thingspeak field to publish as.
    if msg.topic in topics:
        # delta_t = 0 is not allowed, so use ceiling math function
        message['delta_t'] = int(math.ceil(time.time() - lastThingspeakTime))
        # e.g. message['field1'] = float(msg.payload.decode("utf-8"))
        message[topics.get(msg.topic)] =float(msg.payload.decode("utf-8"))

        # update the messageBuffer with the current message
        messageBuffer.append(message)
        if len(messageBuffer) >= len(topicList) and ((time.time() - lastThingspeakTime) >= thingspeakMinInterval) or ((time.time() - lastThingspeakTime) >= thingspeakMaxInterval):
            # Now all fields are in messageBuffer, send to ThingSpeak using REST API (https post)
            http_request()
            lastThingspeakTime = time.time()

# ////////////////////////////////////////////
# Start of main
# ////////////////////////////////////////////
if __name__ == '__main__':
    # define an easy way to print to stderr
    def eprint(*args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)

    # handle command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='configuration file for the program, default iotitan.conf')
    args = parser.parse_args()

    lastThingspeakTime = time.time()
    thingspeakMinInterval = 15  # Thingspeak only allows data to be posted once every 15 seconds
    thingspeakMaxInterval = 600 # wait up to 10 minutes for new data to come. 

    # ----------  Start of user configuration ----------
    if args.config:
        conf=Setting(args.config)
    else:
        conf=Setting('iotitan.conf')

    # ThingSpeak Channel Settings.  Set here or in config file.
    channelID = conf.get_setting('THINGSPEAK', 'channelID')
    if channelID == None:
        channelID = "YOUR THINGSPEAK CHANNEL ID"
    eprint('ThingSpeak channelID is : ' + channelID)
    writeApiKey = conf.get_setting('THINGSPEAK', 'writeApiKey')
    if writeApiKey == None:
        writeApiKey = "YOUR THINGSPEAK WRITE API KEY"

    url = "https://api.thingspeak.com/channels/" + channelID + "/bulk_update.json"
    messageBuffer = []

    # Hostname of the MQTT service
    mqtt_host = conf.get_setting('MQTT', 'mqtt_host')
    if mqtt_host == None:
        mqtt_host = "YOUR MQTT SERVICE IP ADDRESS, e.g. your Raspberry Pi IP"
    tPort = 0
    # MQTT topics
    topics = {}
    topics = conf.get_topics()
    for key in topics:
        print(key)
        print(topics[key])

    # Make a list of these topics suitable for the MQTT client API
    # e.g. for two topics, format is: client.subscribe([("$SYS/#",0),("/#",0)])
    topicList = []
    for key in topics:
        # to the list, append a tuple consisting of topic name and zero to indicate MQTT mode.
        topicList.append((key, 0))

    # MQTT Connection Methods
    # use default MQTT port 1883 (low system cost)
    use_unsecured_TCP = True
    # use unsecured websocket on port 80 (useful when 1883 blocked)
    use_unsecured_websockets = False
    # use secure websocket on port 443 (most secure)
    use_SSL_websockets = False
    # ---------- End of user configuration ----------

    # Set up the connection parameters based on the connection type
    if use_unsecured_TCP:
        tTransport = "tcp"
        tPort = 1883
        tTLS = None

    if use_unsecured_websockets:
        tTransport = "websockets"
        tPort = 80
        tTLS = None

    if use_SSL_websockets:
        import ssl
        tTransport = "websockets"
        tTLS = {'ca_certs': "/etc/ssl/certs/ca-certificates.crt", \
                'tls_version': ssl.PROTOCOL_TLSv1}
        tPort = 443

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_log = on_log

    # eprint("Connecting to local MQTT broker")
    # params are: hostname, port, keepalive, bind_address
    client.connect(mqtt_host, tPort, 60)

    # eprint("Subscribing to channels")
    client.subscribe(topicList)

    # eprint("Looping for callbacks")
    # Blocking call that processes network traffic, dispatches callbacks and
    # handles reconnecting.
    # Other loop*() functions are available that give a threaded interface and a
    # manual interface.
    client.loop_forever()
    eprint("End of loop")
