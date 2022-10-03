import queue
import threading
import time
import datetime
import logging
import sys


#import pyUBXLibrary.pyUBX.ubx

#from pyUBXLibrary.pyUBX.ubx import parseUBXPayload, parseUBXMessage

from ubx import UBX
from ubx import parseUBXPayload, parseUBXMessage



class AbstractParser:

    def __init__(self, inputQueue:queue.SimpleQueue, notifierQueue: queue.SimpleQueue, name="Universal"):
        self.parserName = name
        self.notifierQueue = notifierQueue
        self.input = inputQueue
        self.processingThread = threading.Thread(target=self.process)
        self.processingThread.start()
        logging.debug("AbstractParser initialized")

    def parse(self, message):
        try:
            print(type(message), str(message))
            return True, str(message)
        except BaseException as anyError:
            return False, str(anyError)


    def process(self):
        while True:
            try:
                message = self.input.get_nowait()
                print("MESSAGE TYPE ", type(message))
                if message is not None:
                    logging.debug("Parser {} got new work".format(self.parserName))
                    wasParsed, parseResult = self.parse(message)
                    if wasParsed is not None:
                        datapack = ("parser-result", wasParsed, parseResult)
                        self.notifierQueue.put(datapack)
            except queue.Empty:
                time.sleep(0.1)


class BinaryRecorder(AbstractParser):

    def parse(self, message):
        name = self.parserName+"_"+str(datetime.datetime.now().isoformat()).replace(":", "-").replace(".", "-")+".bin"
        print("Writing dump ", name)
        with open(name, "wb") as binfile:
            binfile.write(message)

class UbxNavHpposecefParser(AbstractParser):

    def parse(self, message):
        parseResult = message.__dict__
        print(parseResult)
        datapack = ("ubx-NavHpposecef-Parser-result", wasParsed, parseResult)
        self.notifierQueue.put(datapack)


class UbxNavRelPosNedParser(AbstractParser):

    def parse(self, message):
        parseResult = message.__dict__
        print(parseResult)
        datapack = ("ubx-NavRelposned-Parser-result", wasParsed, parseResult)
        self.notifierQueue.put(datapack)

