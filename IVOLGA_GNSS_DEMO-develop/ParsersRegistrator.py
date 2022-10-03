"""
Данный класс реализует пул парсеров
предназначен для параллельной обрабьотки сообщений каждым парсером для каждого типа сообщений

Для работы необходимо
* прогрузить конфиг чтобы знать какие типы данных возможны
* зарегистрировать функцию обработчик для каждого имени типа например

parserPull.registerParser("NAV-CLOCK", gpsClockParser)
или
parserPull.registerParser("MON", gpsDeviceStatusParser)

* во время получения данных из сокета сообщение прошедшее проверку на контрольной сумме отправляется вот так
parserPull.processMessage("MON", messagebytes (!no class and id))
при этом у ранее указанного класса будет вызываться метод process которому будет передаваться набор данных
"""

from DataParsers import AbstractParser
import queue

class ParserPull:

    def __init__(self, notifierQueue: queue.SimpleQueue):
        self.notifierQueue = notifierQueue
        self.registeredParsers = dict()
        self.registeredParsersQueues = dict()
        self.preConfiguredParsers()

    def preConfiguredParsers(self):
        #self.registerParser("MON", AbstractParser.UbxMonParser)
        self.registerParser("NAV-HPPOSECEFF", AbstractParser.UbxNavHpposecefParser)
        self.registerParser("NAV-RELPOSNED", AbstractParser.UbxNavHpposecefParser)
        print("Pre-configured Parsers created: "+str(self.registeredParsersQueues.keys()))


    def registerParser(self, typename, ParserClass):
        if typename not in self.registeredParsers.keys():
            newQueue = queue.SimpleQueue()
            self.registeredParsersQueues[typename] = newQueue
            self.registeredParsers[typename] = ParserClass(newQueue, self.notifierQueue, typename)
            print("NEW PARSER FOR {} registered".format(typename))


    def processMessage(self, typename, message):
        print("WORK CONF ", typename, self.registeredParsersQueues.keys(), self.registeredParsers.keys())
        if typename in self.registeredParsersQueues.keys():
            print("INFO: Message of {} bytes from {} to be parsed".format(len(message), typename))
            self.registeredParsersQueues[typename].put(message)
            return True
        else:
            print("Error: Message for unconfigured input ", typename)
            return False