import RPi.GPIO as GPIO
import os
import json
import time
import math
import Adafruit_DHT
import datetime
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
#from config import configs

# Here goes the connection to AWS
#stage = configs[os.environ.get("STAGE")]

# Parameters
host = "akelw02gb2zom-ats.iot.us-east-1.amazonaws.com"
root_ca_path = "/home/pi/Desktop/Programacion/MCP3208/keys/terraform-iot-air-pollution-prod-root-certificate.pem.crt"
certificate_path = "/home/pi/Desktop/Programacion/MCP3208/keys/terraform-iot-air-pollution-prod.pem.crt"
private_key_path = "/home/pi/Desktop/Programacion/MCP3208/keys/keys.txt"
client_id = "air-pollution"
topic = "topic/air-pollution"
location = "home"

# Custom MQTT message callback
def on_message(client: AWSIoTMQTTClient, data: dict, message) -> None:
    print("Received a new message: ")
    print(message.payload)
    print("from topic: ")
    print(message.topic)
    print("--------------\n\n")


def get_mqtt_client() -> AWSIoTMQTTClient:
    """Connect to Mqtt"""
    mqtt_client = None
    mqtt_client = AWSIoTMQTTClient(client_id)
    mqtt_client.configureEndpoint(host, 8883)
    mqtt_client.configureCredentials(root_ca_path, private_key_path, certificate_path)
    mqtt_client.configureAutoReconnectBackoffTime(1, 32, 20)
    mqtt_client.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
    mqtt_client.configureDrainingFrequency(2)  # Draining: 2 Hz
    mqtt_client.configureConnectDisconnectTimeout(10)  # 10 sec
    mqtt_client.configureMQTTOperationTimeout(5)  # 5 sec
    mqtt_client.connect()
    return mqtt_client


def send_message(client: AWSIoTMQTTClient, data: dict) -> None:
    message_json = json.dumps(data)
    client.publish(topic, message_json, 1)
    
# change these as desired - they're the pins connected from the
# SPI port on the ADC to the Cobbler
SPICLK = 11
SPIMISO = 9
SPIMOSI = 10
SPICS = 8
mq2_apin = 0
mq5_apin = 1
mq7_apin = 2
mq135_apin = 3
RL = 1
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4

#Here we inicialize the GPIO, so we can use the connectors of the raspberry to the MCP
def init():
         GPIO.setwarnings(False)
         GPIO.cleanup()         #clean up at the end of your script
         GPIO.setmode(GPIO.BCM)     #to specify whilch pin numbering system
         # set up the SPI interface pins
         GPIO.setup(SPIMOSI, GPIO.OUT)
         GPIO.setup(SPIMISO, GPIO.IN)
         GPIO.setup(SPICLK, GPIO.OUT)
         GPIO.setup(SPICS, GPIO.OUT)

#read SPI data from MCP3008(or MCP3208) chip,8 possible adc's (0 thru 7)
#Also this functions provides analog reading to the arduino
def readadc(adcnum, clockpin, mosipin, misopin, cspin):
        if ((adcnum > 7) or (adcnum < 0)):
                return -1
        GPIO.output(cspin, True)    

        GPIO.output(clockpin, False)  # start clock low
        GPIO.output(cspin, False)     # bring CS low

        commandout = adcnum
        commandout |= 0x18  # start bit + single-ended bit
        commandout <<= 3    # we only need to send 5 bits here
        for i in range(5):
                if (commandout & 0x80):
                        GPIO.output(mosipin, True)
                else:
                        GPIO.output(mosipin, False)
                commandout <<= 1
                GPIO.output(clockpin, True)
                GPIO.output(clockpin, False)

        adcout = 0
        # read in one empty bit, one null bit and 10 ADC bits
        for i in range(12):
                GPIO.output(clockpin, True)
                GPIO.output(clockpin, False)
                adcout <<= 1
                if (GPIO.input(misopin)):
                        adcout |= 0x1

        GPIO.output(cspin, True)
        
        adcout >>= 1       # first bit is 'null' so drop it
        return adcout
    
#main loop
def calculateRS(analogRead):
    try:
        return (RL * ((1023 - analogRead) / analogRead))
    except ZeroDivisionError:
        print("---")

def calculatePromRS(analogRead):
    rs = 0.0
    for i in range(100):
        try:
            rs += calculateRS(analogRead)
        except TypeError:
            print("---")
    rs = rs/100
    return rs

def obtainPPM(ratio_rs_ro, id_mq):
    try:
        if id_mq == 0:
            return (pow(10, ( (math.log(ratio_rs_ro)-MQ2Curve[1]) / MQ2Curve[2]) + MQ2Curve[0]))
        elif id_mq == 1:
            return (pow(10, ( (math.log(ratio_rs_ro)-MQ5Curve[1]) / MQ5Curve[2]) + MQ5Curve[0]))
        elif id_mq == 2:
            return (pow(10, ( (math.log(ratio_rs_ro)-MQ7Curve[1]) / MQ7Curve[2]) + MQ7Curve[0]))
        elif id_mq == 3:
            return (pow(10, ( (math.log(ratio_rs_ro)-MQ135Curve[1]) / MQ135Curve[2]) + MQ135Curve[0]))
        else:
            return 0
    except ValueError:
        print("---")
    
def main():
    init()
    print("Initializing")
    time.sleep(3)
    f = open("lecturasPPM.txt", "+w")
    
    while True:
        # Using the DHT22 sensor
        humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
        
        # This instances are the analogReads, in other words, their values are between 0 to 1023
        MQ2 = readadc(mq2_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
        MQ5 = readadc(mq5_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
        MQ7 = readadc(mq7_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
        MQ135 = readadc(mq135_apin, SPICLK, SPIMOSI, SPIMISO, SPICS)
    
        # Now we calculte only the RS, the RO has already been calculated
        MQ2rs = calculatePromRS(MQ2)
        MQ5rs = calculatePromRS(MQ5)
        MQ7rs = calculatePromRS(MQ7)
        MQ135rs = calculatePromRS(MQ135)
        
        # Now after we have the RS and RO, we start calculating the PPM values of each sensor
        ppm_mq2 = obtainPPM(MQ2rs/MQ2ro, mq2_apin)
        ppm_mq5 = obtainPPM(MQ5rs/MQ5ro, mq5_apin)
        ppm_mq7 = obtainPPM(MQ7rs/MQ7ro, mq7_apin)
        ppm_mq135 = obtainPPM(MQ135rs/MQ135ro, mq135_apin)
        
        # Now we print the data
        #if humidity is not None and temperature is not None:
        #    print("Temperature: {0:0.1f}*C".format(temperature))
        #    print("Humidity: {}%".format(humidity))
        print("SMOKE: " + str(ppm_mq2) + " ppm")
        print("LPG: " + str(ppm_mq5) + " ppm")
        print("CO: " + str(ppm_mq7) + " ppm")
        print("NH4: " + str(ppm_mq135) + " ppm")
        print(datetime.datetime.now())
        print("***************************")
        
        # Here we add the information in the text file
        f.write("SMOKE: " + str(ppm_mq2) + " ppm")
        f.write("LPG: " + str(ppm_mq5) + " ppm")
        f.write("CO: " + str(ppm_mq7) + " ppm")
        f.write("NH4: " + str(ppm_mq135) + " ppm")
        f.write("***************************")
        
        message = {
            "device": client_id,
            "location": location,
            "mq2": int(ppm_mq2),
            "mq5": int(ppm_mq5),
            "mq7": int(ppm_mq7),
            "mq135": int(ppm_mq135),
            "dht22": {"temperature": temperature, "humidity": humidity},
            "issued_date": datetime.datetime.now().timestamp(),
            "metadata": {"other": "value"},
        }
        send_message(client=mqtt_client, data=message)
        print("Published topic %s: %s\n" % (topic, message))
        
        time.sleep(1.0)

# Each sensor (MQ2,5,7 and 135) has their own sensibility to a controlled area, this one is air. Also you can see the values on the datasheets
air = [9.83, 6.50, 26.95, 3.12] #Used to calculate RO

MQ2Curve = [2.30,0.53,-0.44]
MQ5Curve = [2.30,-0.15,-0.37]
MQ7Curve = [1.70,0.24,-0.677]
MQ135Curve = [1.00,0.46,-0.235]

MQ2ro = 12.91
MQ5ro = 10.36
MQ7ro = 0.63
MQ135ro = 19.37

if __name__ =='__main__':
    """Execute send payload."""
    mqtt_client = get_mqtt_client()
    try:
        main()
        f.close()
        pass
    except KeyboardInterrupt:
        pass

GPIO.cleanup()
