
"""
ublox protocol docs
https://pypi.org/project/ublox/
https://github.com/mayeranalytics/pyUBX

структура сообщения состоят из
* 2 байт преамбулы,
* 1 байта класса сообщения (id типа сообщения)
* 1 байта ид сообщения (id тип поля в сообщении)
* 2 байт длинны (число без знака в little endian) задает длину тела сообщения
* ТЕЛО СООБЩЕНИЯ
* хеш байт А
* хеш байт Б
байты для расчета хеш суммы начинаются с класса включительно до конца ТЕЛА суммы
хеш байты должны быть типа uint8 1 байтовое без знака
в случае переполнения накладывайте маску 0x00FF для обрезания байтов выше первого !!!
"""


import json
import socket
import threading
import queue
import logging
import traceback
import os
import sys
logging.basicConfig(filename="gps_connector.log", level=logging.DEBUG)

import NotifierAndLogger

#import ubx
#from ubx import UBX
import datetime

from pyubx2 import UBXReader

import pickle

#for terminating frontend process when main.py's being stopped
import multiprocessing as mp
from testFrontend.FlaskConsumer import Test

import shutil

#from ubx import parseUBXPayload, parseUBXMessage

class UbxCrcCalculator:

    """
    message structure
    head - 2 bytes
    class id - 1 bytes
    message id  - 1 bytes
    length - 2 bytes, byteorder=little, unsigned
    BODY
    crc_a - 1 bytes
    crc_b - 1 bytes
    """

    def __init__(self):
        self.configName = self.confName = "gnssConfig.json"
        with open(self.confName, "r") as config:
            self.arConfig = json.loads(config.read())
        self.sync_1 = int(self.arConfig["SYNC_1"], 16).to_bytes(1, byteorder="little")
        self.sync_2 = int(self.arConfig["SYNC_2"], 16).to_bytes(1, byteorder="little")


    def serialize(self, message):
        binMsg = bytearray()
        binMsg += self.sync_1
        binMsg += self.sync_2
        lenb = len(message)
        lenb = lenb.to_bytes(length=2, byteorder="little", signed=False)
        binMsg += lenb
        binMsg += message
        summable=binMsg[2:]
        crcs = self.calculateCrc(summable)
        binMsg += crcs


    def calculateCrc(self, binmessage):
        crc_a = 0x00
        crc_b = 0x00
        mask = 0x00FF
        for ob in binmessage:
            #print(">> ",type(ob))
            #ib = ob.to_bytes(ob, byteorder="little", signed=False)
            crc_a += ob
            crc_a = crc_a & mask
            crc_b += crc_a
            crc_b = crc_b & mask
        crcs = bytearray()
        crcs += crc_a.to_bytes(length=1, byteorder="little", signed=False)
        crcs += crc_b.to_bytes(length=1, byteorder="little", signed=False)
        return crcs


class UbxBinCfgCommand:

    def disableCommandPayload(self):
        disableCommand = bytearray()
        disableCommand.append(0x00)
        disableCommand.append(0x00)
        disableCommand.append(0x00)
        disableCommand.append(0x00)
        disableCommand.append(0x00)
        disableCommand.append(0x00)
        return disableCommand


    def enableCommandPayload(self):
        enableCommand = bytearray()
        enableCommand.append(0x00)
        enableCommand.append(0x00)
        enableCommand.append(0x00)
        enableCommand.append(0x00)
        enableCommand.append(0x01)
        enableCommand.append(0x00)
        return enableCommand



class MessageTypeDetector():
    """
    Этот класс используется для определения типа данных
    Имя состоит из id класса и id поля (сообщения)
    например NAV-CLOCK это часы по спутнику
    например RXM-PMREQ это запрос текущего режима работы передатчика
    бывают типы без поля, например INF
    Составной класс (тип данных) обозначен в конфиге как MESSAGE_CLASS_IDS
    Id сообщений в составе типа данных обозначены в конфиге тут UBX_MESSAGE_IDS
    Обращаю внимание что не у всех классов есть ид сообщений !
    Но у каждого из  UBX_MESSAGE_IDS обязательно есть родительский класс (тип)
    класс и поле определяются первым и вторым байтами после преамбулы
    """


    def __init__(self):
        self.configName = self.confName = "gnssConfig.json"
        self.messageClassConfigArray = "MESSAGE_CLASS_IDS"
        self.messageIdsConfigArray = "UBX_MESSAGE_IDS"
        self.messageClasses = dict()
        self.messageIds = dict()
        with open(self.confName, "r") as config:
            arConfig = json.loads(config.read())
            # reading message classes and ids from config
            for messageClassName, messageClassStValue in arConfig[self.messageClassConfigArray].items():
                self.messageClasses[messageClassName] = int(messageClassStValue, 16)
                self.messageIds[messageClassName] = dict()
                if messageClassName in arConfig[self.messageIdsConfigArray].keys():
                    for messageIdName, messageIdstVal in arConfig[self.messageIdsConfigArray][messageClassName].items():
                        self.messageIds[messageClassName][messageIdName] = int(messageIdstVal, 16)
                print("Class {} configured {} message sub-types".format(messageClassName, len(self.messageIds[messageClassName])))



    def detectMessageType(self, typebytes: bytearray):
        detectedType = ""
        td = False
        if len(typebytes) == 2:
            for className, classId in self.messageClasses.items():
                if typebytes[0] == classId:
                    detectedType = className
                    td = True
                    if className in self.messageIds.keys():
                        for messageName, messageId in self.messageIds[className].items():
                            if typebytes[1] == messageId:
                                detectedType += "-" + messageName
                                break
        else:
            raise RuntimeError("Type bytes must contain 2 bytes, got {} {}".format(len(typebytes), typebytes))
        if td:
            return detectedType
        else:
            return None


    def getTypeBytes(self, typename):
        if "-" in typename: # combined typename LIKE TIME-CLOCK
            typebytes = bytearray()
            typeparts = str(typename).split("-")
            classId = typeparts[0]
            messageId = typeparts[1]
            for className, classVal in self.messageClasses.items():
                if classId in className:
                    typebytes.append(classVal)
                for msgName, msgval in self.messageIds[className].items():
                    if messageId == msgName:
                        typebytes.append(msgval)
            return typebytes



class GnssConnector:

    def __init__(self):
        self.crcCalculator = UbxCrcCalculator()
        self.ubxCfgHelper = UbxBinCfgCommand()
        self.notificationsQueue = queue.SimpleQueue()
        #self.parserRegistry = ParsersRegistrator.ParserPull(self.notificationsQueue)
        #self.notificator = NotifierAndLogger.NotifierAndLogger(self.notificationsQueue)
        self.confName = "gnssConfig.json"
        with open(self.confName, "r") as config:
            self.arConfig = json.loads(config.read())
        self.SYNC_1 = int(self.arConfig["SYNC_1"], 16).to_bytes(length=1, byteorder="little")
        self.SYNC_2 = int(self.arConfig["SYNC_2"], 16).to_bytes(length=1, byteorder="little")
        #print("SYNCS ", self.SYNC_1, " ", self.SYNC_2)
        self.gpsSensorSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conparam = (self.arConfig["host"], self.arConfig["port"])
        self.crcMask = int(self.arConfig["CRC_MASK"], 16)
        self.messageTypeDetector = MessageTypeDetector()
        self.stopAllEvent = threading.Event()
        self.stopAllEvent.clear()
        self.messageHandlers = dict()
        self.dump = None
        self.countLinesDumped = 0
        self.maxCountLines = 1000
        #self.messageHandlers["MON"] = self.MonHandler
        self.messagesCounter = dict()
        self.messagesCounter["NAV-RELPOSNED"] = 0
        #self.messagesCounter["NAV-PYT"] = 0
        self.messagesCounter["ACK-ACK"] = 0
        self.messagesCounter["ACK-NAC"] = 0
        self.messagesCounter["NAV-PVT"] = 0
        self.messagesCounter["NAV-POSECEF"] = 0
        self.messagesCounter["NAV-HPPOSECEF"] = 0
        self.loggableMessages = ["NAV-PYT", "NAV-POSECEF", "NAV-HPPOSECEF"]
        self.pickle_path = "testFrontend"



    def connect(self):
        self.gpsSensorSocket.connect(self.conparam)

    def disableMonMessagesType31(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False) # length of cfg command = 8 bytes
        disableCommand = int(0x0a).to_bytes(length=1, byteorder="little", signed=True) + int(0x31).to_bytes(length=1, byteorder="little", signed=True) +self.ubxCfgHelper.disableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        #return message


    def disableMonMessagesType04(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False) # length of cfg command = 8 bytes
        disableCommand = int(0x0a).to_bytes(length=1, byteorder="little", signed=True) + int(0x04).to_bytes(length=1, byteorder="little", signed=True) +self.ubxCfgHelper.disableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs

        self.gpsSensorSocket.send(message)
        #return message

    def disableMonMessages(self):
        #self.disableMonMessagesType04()
        self.disableMonMessagesType31()
        #logging.info("MON DISABLED")

    def enableHppos(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False)  # length of cfg command = 8 bytes
        disableCommand = int(0x01).to_bytes(length=1, byteorder="little", signed=True) + int(0x13).to_bytes(
            length=1, byteorder="little", signed=True) + self.ubxCfgHelper.enableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        # return message

    def disableHppos(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False)  # length of cfg command = 8 bytes
        disableCommand = int(0x01).to_bytes(length=1, byteorder="little", signed=True) + int(0x13).to_bytes(
            length=1, byteorder="little", signed=True) + self.ubxCfgHelper.disableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        # return message

    def enablePvt(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False)  # length of cfg command = 8 bytes
        disableCommand = int(0x01).to_bytes(length=1, byteorder="little", signed=True) + int(0x07).to_bytes(
            length=1, byteorder="little", signed=True) + self.ubxCfgHelper.enableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        # return message

    def enableSllh(self):
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False)  # length of cfg command = 8 bytes
        disableCommand = int(0x01).to_bytes(length=1, byteorder="little", signed=True) + int(0x14).to_bytes(
            length=1, byteorder="little", signed=True) + self.ubxCfgHelper.enableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        # return message

    def enablePoseEcEf(self):
        #NAV-POSECEF
        message = bytearray()
        message.append(0xb5)
        message.append(0x62)
        message.append(0x06)
        message.append(0x01)
        message += int(8).to_bytes(length=2, byteorder="little", signed=False)  # length of cfg command = 8 bytes
        disableCommand = int(0x01).to_bytes(length=1, byteorder="little", signed=True) + int(0x01).to_bytes(
            length=1, byteorder="little", signed=True) + self.ubxCfgHelper.enableCommandPayload()
        message += disableCommand
        crcs = self.crcCalculator.calculateCrc(message[2:])
        message += crcs
        self.gpsSensorSocket.send(message)
        # return message



    def stopAll(self):
        self.gpsSensorSocket.close()
        self.stopAllEvent.set()
        print("Stop signal send")

    def getNextLogName(self):
        logfolder = "logs" #self.arConfig["dump_root"]
        logname = "gnss_" + datetime.datetime.now().isoformat().replace(":", "-").replace(" ", "") + ".txt"
        logpath = os.path.join(logfolder, logname)
        return logpath


    def reopenLog(self):
        print("reopening log")
        nextLog = self.getNextLogName()
        self.dump = open(nextLog, "a")
        self.countLinesDumped = 0


    def run(self):
        print("GNSS CONNECTOR STARTED")
        headDataPortion = 6 # count bytes to read
        expectedLength = 0  # package length parsed from head
        message = bytearray()
        crcs = bytearray()
        etalonPreambula = self.SYNC_1+self.SYNC_2

        while not self.stopAllEvent.is_set():
            headCandidat = self.gpsSensorSocket.recv(headDataPortion)
            preCandidat = headCandidat[0:2]
            if preCandidat == etalonPreambula:
                #logging.debug("PREAMBULA")
                expectedLength = headCandidat[-2:]
                expectedLength = int.from_bytes(expectedLength, byteorder="little", signed=False)
                #print("EXP PACKAGE SIZE: ", expectedLength)
                if expectedLength > 0:
                    message = self.gpsSensorSocket.recv(expectedLength)
                crcs = self.gpsSensorSocket.recv(2)
                try:
                    detectedType = self.messageTypeDetector.detectMessageType(headCandidat[2:4])
                    if detectedType in self.loggableMessages:
                        #logging.info("MESSAGE TYPE: "+detectedType)
                        datapack = (headCandidat + message + crcs)
                        parsedPack = UBXReader.parse(datapack)
                        pdict = parsedPack.__dict__
                        # removing all binary fields
                        for kn in list(pdict.keys()):
                            if isinstance(pdict[kn], bytes):
                                pdict.pop(kn)
                                #print("field {} removed".format(kn))
                        pdict["MessageType"] = detectedType # marking human-friendly message type name
                        if detectedType == "NAV-PYT":
                            self.logMessage(json.dumps(self.parse_row(pdict)))
                except BaseException as AnyError:
                    print(str(AnyError))
                    #logging.error(str(AnyError))
                    continue

    def logMessage(self, message):
        if (self.dump is None) or (self.countLinesDumped > self.maxCountLines):
            self.reopenLog()
        self.dump.write(message+"\n")
        self.countLinesDumped += 1
        print("LOG: ", self.countLinesDumped, message)


    def parse_row(self, d):
        p = (10**-3) # mm -> m
        message = {}
        if d['MessageType'] == 'NAV-PYT':
            time_seconds = int(datetime.datetime.strptime(' '.join([str(d['year']), 
                    str(d['month']), str(d['day']), str(d['hour']), str(d['min']), str(d['second'])]), 
                                                                '%Y %m %d %H %M %S').timestamp())
            message['timestamp'] = time_seconds
            message['coords'] = (d['lon'], d['lat'])
            message['heading'] = round(d['headMot'], 2)
            message['velocity'] = round(d['gSpeed']*p*3.6, 2)
            message['accuracy'] = (round(d['hAcc']*p, 2), round(d['vAcc']*p, 2))

            try:
                print(os.path.exists(self.pickle_path))
                with open(self.pickle_path + "/shared.pkl", "wb") as fp:
                    pickle.dump(message, fp)
            except Exception as e:
                print(message)
                traceback.print_tb(e.__traceback__)
                print(traceback.format_exc())
        
        return message

        
# SELF TESTS FUNCTIONS


def typeDetectorTest():
    print("\nTesting NAV-CLOCK type")
    mtd = MessageTypeDetector()
    typebytes = bytearray()
    typebytes.append(0x01)
    typebytes.append(0x22)
    # expected NAV-CLOCK response
    messageType = mtd.detectMessageType(typebytes)
    #print("Message type: ", messageType)
    if messageType == "NAV-CLOCK":
        print("Type NAV-CLOCK detetced, test done")
    else:
        print("Type NAV-CLOCK was not detected")

def unexistTypeDetectorTest():
    print("\nTesting wrong type")
    mtd = MessageTypeDetector()
    typebytes = bytearray()
    typebytes.append(0xff)
    typebytes.append(0xfe)
    # expected NAV-CLOCK response
    messageType = mtd.detectMessageType(typebytes)
    #print("Message type: ", messageType)
    if messageType is None:
        print("Unexisted type was not recognized, test done")
    else:
        print("Test failed, unexisted type returns: ", messageType)

def someInfTypeDetect():
    print("\nTesting INF type")
    mtd = MessageTypeDetector()
    typebytes = bytearray()
    typebytes.append(0x04)
    typebytes.append(0x01)
    # expected NAV-CLOCK response
    messageType = mtd.detectMessageType(typebytes)
    # print("Message type: ", messageType)
    if messageType == "INF":
        print("INF type was recognized, test done")
    else:
        print("Test failed, INF was not recogniuzed: ", messageType)

def typeDetectorTests():
    typeDetectorTest()
    unexistTypeDetectorTest()
    someInfTypeDetect()



if __name__ == "__main__":
    if not os.path.exists("logs"):
        os.mkdir("logs") 
    else: 
        shutil.rmtree("logs") 
        os.mkdir("logs") 
    p1 = mp.Process(target = Test)
    p1.start()
    children = mp.active_children()
    print(f'Active Children Count: {len(children)}')
    for child in children:
        print(child)
    gnss = GnssConnector()
    gnss.connect()
    try:
        gnss.disableMonMessages()
        gnss.enableHppos()
        gnss.enableSllh()
        #gnss.disableHppos()
        gnss.enablePvt()
        gnss.enablePoseEcEf()
        gnss.run()
    except KeyboardInterrupt:
        gnss.stopAll()
    except BaseException as anyEror:
        traceback.print_last()
        gnss.stopAll()
        print(str(anyEror))

