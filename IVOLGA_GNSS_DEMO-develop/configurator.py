import json
from pyubx2 import UBXReader
import re
import binascii
import socket

#from ubx import parseUBXPayload, parseUBXMessage


class Configurator:

    def __init__(self):
        adapterPreambula = ["b5", "66"]
        self.sync_1 = int(adapterPreambula[0], 16).to_bytes(1, byteorder="little")
        self.sync_2 = int(adapterPreambula[1], 16).to_bytes(1, byteorder="little")


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


    #  creates binary-represent of given ip in format xxx.xxx.xxx.xxx
    def iptobincmd(self, ip:str):
        filter = r"[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}"
        if re.fullmatch(filter, ip):
            asciiip = bytes(ip.encode("ascii"))
            return asciiip
        else:
            raise ValueError("Unable tp convert unicode ip represent {} to its bin ascii eq. Wrong symbols on input".format(ip))

    def checkRev(self, letters):
        result = ""
        for llet in letters:
            result += chr(llet)
        print(result)
        return result


    def setIpCommand(self, ip: str):
        ascciip = self.iptobincmd(ip)
        message = self.sync_1+self.sync_2
        message += 0x00.to_bytes(length=1, byteorder="little", signed=False)
        message += 0x21.to_bytes(length=1, byteorder="little", signed=False)
        lenb = len(ascciip).to_bytes(2, byteorder="little", signed=False)
        message += lenb
        message += ascciip
        crc = self.calculateCrc(message[2:])
        message += crc
        return message

    def saveSettings(self):
        command = bytearray()
        command += 0xb5.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x66.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x00.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x15.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x01.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x00.to_bytes(length=1, byteorder="little", signed=False)
        command += 0x01.to_bytes(length=1, byteorder="little", signed=False)
        command += self.calculateCrc(command[2:])
        return command



if __name__ == "__main__":
    cfger = Configurator()
    current_ip = "192.168.0.55"
    target_ip = "192.168.30.10"
    current_port = 5500
    cmdsetip = cfger.setIpCommand(target_ip)
    print("cmd to set ip ", cmdsetip)
    gpsSensorSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conparam = (current_ip, current_port)
    gpsSensorSocket.connect(conparam)
    gpsSensorSocket.send(cmdsetip)
    saveCmd = cfger.saveSettings()
    gpsSensorSocket.send(saveCmd)
    gpsSensorSocket.close()
    print("command to change ip from {} to {} was send.".format(current_ip, target_ip))