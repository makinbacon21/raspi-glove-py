#!/usr/bin/env python
import yaml
import scaleConfig
import scaleTwitter
import argparse

'''
This is mostly from:
https://learn.adafruit.com/
   reading-a-analog-in-and-controlling-audio-volume-with-the-raspberry-pi/
   script

(git://gist.github.com/3151375.git)

With some modifications by me that should have been other
commits, but weren't, so sorry, you'll have to diff it yourself
if you want to see what changed.

I have no idea what the license is on the original, so I have no
idea what the license on this is.  Personally, I don't care, but
Adafruit might.
'''

# read SPI data from MCP3008 chip, 8 possible adc's (0 thru 7)
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

configFile = './scaleConfig.yaml'

parser = argparse.ArgumentParser()
parser.add_argument ("-d", "--debug", type=int, choices=[0,1],
		     nargs='?', const=1,
		     help="turn debugging on (1) or off (0); this overrides"+
		     "the value in the configuration file ")
parser.add_argument("-c","--config", action="store", dest="configFile",
		    help="specify a configuration file")
args = parser.parse_args()

if args.configFile:
	configFile = args.configFile

cfg = scaleConfig.readConfig(configFile)

try:
        f = open(cfg['raspberryPiConfig']['plotlyCredsFile'])
except:
        print "=========================== ERROR ==========================="
        print "I couldn't open the file '{0}'".format(cfg['raspberryPiConfig']['plotlyCredsFile'])
        print "to read the plot.ly settings, so I can't make a plot and"
        print "am giving up."
        print "(I am:", os.path.abspath(os.path.dirname(sys.argv[0]))+"/"+sys.argv[0],")"
        print "=========================== ERROR ==========================="
        exit (1)

plotlyConfig = yaml.safe_load(f)
f.close()

if args.debug == None:
	DEBUG = cfg['raspberryPiConfig']['debug']
else:
	DEBUG = args.debug

if DEBUG:
	print "Initializing."

import time
import datetime
import os
import RPi.GPIO as GPIO
import scalePlotly


GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False) # to stop the "This channel is already in use" warning

# change these as desired - they're the pins connected from the
# SPI port on the ADC to the Cobbler
# ADCPort    Cobbler
# -------- ----------
SPICLK    =    cfg['raspberryPiConfig']['ADCtoCobbler']['SPICLK']
SPIMISO   =    cfg['raspberryPiConfig']['ADCtoCobbler']['SPIMISO']
SPIMOSI   =    cfg['raspberryPiConfig']['ADCtoCobbler']['SPIMOSI']
SPICS     =    cfg['raspberryPiConfig']['ADCtoCobbler']['SPICS']
# Diagram of ADC (MCP3008) is at:
#   https://learn.adafruit.com/
#     reading-a-analog-in-and-controlling-audio-volume-with-the-raspberry-pi/
#     connecting-the-cobbler-to-a-mcp3008

# set up the SPI interface pins
GPIO.setup(SPIMOSI, GPIO.OUT)
GPIO.setup(SPIMISO, GPIO.IN)
GPIO.setup(SPICLK, GPIO.OUT)
GPIO.setup(SPICS, GPIO.OUT)

# FSR connected to adc #0
fsr_adc = cfg['raspberryPiConfig']['adcPortWithFSR']

# this keeps track of the last FSR value
last_read = 0

# to keep from being jittery we'll only change when the FSR has moved
# more than this many 'counts'
tolerance = cfg['raspberryPiConfig']['tolerance']

#
# If we will need Twitter credentials, read them now
#
if 'twitter' in cfg['raspberryPiConfig']['alertChannels'] or 'twitter' in cfg['raspberryPiConfig']['updateChannels']:
	if DEBUG:
		print "Reading Twitter credentials from ",cfg['twitterConfiguration']['twitterCredsFile']

        try:
                f = open(cfg['twitterConfiguration']['twitterCredsFile'])
                twitterCredentials = yaml.safe_load(f)
                f.close()
        except:
                if DEBUG:
                        print "=========================== ERROR ==========================="
                        print "I couldn't open the file '{0}'".format(cfg['twitterConfiguration']['twitterCredsFile'])
                        print "to read the twitter credentials, so I can't tweet."
                        print "(I am:", os.path.abspath(os.path.dirname(sys.argv[0]))+"/"+sys.argv[0],")"
                        print "=========================== ERROR ==========================="

			cfg['raspberryPiConfig']['alertChannels'].remove('twitter')
			cfg['raspberryPiConfig']['updateChannels'].remove('twitter')

if DEBUG:
	print "Ready."

oTime = cfg['raspberryPiConfig']['updateTime']

while cfg['raspberryPiConfig']['updateTime'] % cfg['raspberryPiConfig']['checkTime']:
        cfg['raspberryPiConfig']['updateTime'] += 1

if oTime != cfg['raspberryPiConfig']['updateTime'] and DEBUG:
        print "\"updateTime\" changed to ",
        cfg['raspberryPiConfig']['updateTime'],
        "so it would divide evenly by \"checkTime\"."

scaleClock = 0

while True:

        # read the analog pin
        fsr = readadc(fsr_adc, SPICLK, SPIMOSI, SPIMISO, SPICS)
        # how much has it changed since the last read?
        fsr_change = (fsr - last_read)

        scaleClock += cfg['raspberryPiConfig']['checkTime']

        if fsr_change > cfg['raspberryPiConfig']['maxChange'] and ( abs(fsr_change) > tolerance ):
                last_read = fsr
                beans = int((fsr/1024.)*100)
                if DEBUG:
                        print '{0}\tfsr: {1:4d}\tlast_value: {2:4d}\tchange: {3:4d}\tbeans: {4}'.format(datetime.datetime.now(),
                                                                                                        fsr,
                                                                                                        last_read,
                                                                                                        fsr_change,
                                                                                                        beans)
                scalePlotly.updatePlot (datetime.datetime.now(),
                                        beans,
                                        plotlyConfig['username'],
                                        plotlyConfig['apikey'])

        if scaleClock == cfg['raspberryPiConfig']['updateTime']:
                if 'plotly' in cfg['raspberryPiConfig']['updateChannels']:
                        scalePlotly.updatePlot (datetime.datetime.now(),
                                                beans,
                                                plotlyConfig['username'],
                                                plotlyConfig['apikey'])
                if 'twitter' in cfg['raspberryPiConfig']['updateChannels']:
                        scaleTwitter.tweetStatus(twitterCredentials['accessToken'],
                                                 twitterCredentials['accessSecret'],
                                                 twitterCredentials['consumerKey'],
                                                 twitterCredentials['consumerSec'],
                                                 "The current bean inventory is {}. #caen #beanbot #coffebeans".format(beans))


        time.sleep(cfg['raspberryPiConfig']['checkTime'])
