
import threading
import queue
import time

class NotifierAndLogger:

    def __init__(self, inputQueue: queue.SimpleQueue):
        self.notificationQueue = inputQueue
        self.notificationThread = threading.Thread(target=self.notificator)
        self.notificationThread.start()



    def notificator(self):
        print("Notification thread started")
        while True:
            try:
                notif = self.notificationQueue.get_nowait()
                sender, rType, notification = notif
                print("Sender: {} Type: {}, Text: {}".format(sender, rType, notification))
            except queue.Empty:
                time.sleep(0.1)

