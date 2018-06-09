from model import Data, State, Callback
from manager import Manager
import json
import socket
import threading
import struct
import os
import logging
import sys

# Secret token
SECRET_TOKEN = '86de0ff4-3115-4385-b485-b5e83ae6b890'
manager = Manager()

# logging
def setup_custom_logger(name):
    formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    handler = logging.FileHandler('log.txt', mode='w')
    handler.setFormatter(formatter)
    screen_handler = logging.StreamHandler(stream=sys.stdout)
    screen_handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.addHandler(screen_handler)
    return logger

# Callback
def callbackFunction(data: Data, callback: Callback):

    if type(callback.payload) is socket.socket:
        client: socket = callback.payload;

        # if no data (subscribe failed)
        if data is None:
            send_msg(client, json.dumps({'status': 'error', 'description': 'Session not found', 'code': '9'}))
            return

        # else send data
        try:
            msg = json.dumps({'status': 'ok', 'new_data' : data.dictValue()})
            send_msg(client, msg)
        except: 
            manager.unsubscribe(callback)



# Socket messages

def send_msg(sock, msg):
    msg = msg + '<EOF>'
    msg = msg.encode("utf-8")
    sock.sendall(msg)

def recv_msg(sock):
    BUFF_SIZE = 4096 # 4 KiB
    data = b''
    while True:
        
        try:
            part = sock.recv(BUFF_SIZE)
        except:
            return None

        data += part
        if len(part) < BUFF_SIZE:
            # either 0 or end of data
            break
    return data.decode("utf-8")

# Client thread
def on_new_client(clientsocket, addr):
    
    logger.info('Client connected: ' + str(addr))

    identifer = None #session identifer
    token = None #access token
    subscribeCallback = None

    while True:

        msg = recv_msg(clientsocket)

        # Check connection
        if(msg is None or len(msg) == 0):
            break

        coomnds = msg.split('<EOF>')
        for command in coomnds:

            # skip empty command
            if(len(command) == 0):
                continue

            # Parse
            try:
                responce = json.loads(msg)
            except ValueError:
                send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'Not valid JSON', 'code': '1'}))
                continue
        
            # Access variables
            if 'token' in responce:
                token = responce['token']

            if 'identifer' in responce:
                identifer = responce['identifer']

            if token is None:
                send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No token', 'code': '2'}))
                continue

            if identifer is None:
                send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No identifer', 'code': '3'}))
                continue

            if token != SECRET_TOKEN:
                send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'Wrong token', 'code': '4'}))
                continue

            # Commands
            if 'command' in responce:
                command = responce['command']

                # Get info
                if(command == 'get'):
                     logger.info('Client ' + str(addr) + " get ifo about " + identifer)
                     data =  manager.get(identifer)
                     if data is None:
                         send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'Session not found', 'code': '9'}))
                     else:
                        send_msg(clientsocket, json.dumps({'status': 'ok', 'new_data' : data.dictValue()}))


                # Subscribe
                if(command == 'subscribe' or command == 'host'):
                    
                    #remove old callback
                    if(subscribeCallback is not None):
                        manager.unsubscribe(identifer, subscribeCallback)

                    subscribeCallback = Callback(callbackFunction, clientsocket) 
                    manager.subscribe(identifer, subscribeCallback, (command == 'host'))
                    logger.info('Client ' + str(addr) + " subscribed " + identifer)
                    send_msg(clientsocket, json.dumps({'status': 'ok', 'code': '0'}))

                # Set info
                if(command == 'set'):

                    if 'file' in responce:
                         file = responce['file']
                    else:
                         send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No file', 'code': '5'}))
                         continue

                    if 'duration' in responce:
                         duration = float(responce['duration'])
                    else:
                         send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No duration', 'code': '6'}))
                         continue

                    if 'position' in responce:
                         position = float(responce['position'])
                    else:
                         send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No position', 'code': '7'}))
                         continue

                    if 'state' in responce:
                         state = int(responce['state'])
                    else:
                         send_msg(clientsocket, json.dumps({'status': 'error', 'description': 'No state', 'code': '8'}))
                         continue

                    logger.info('Client ' + str(addr) + " set info " + identifer)
                    manager.set(identifer, Data(file, duration, position, state))
                    send_msg(clientsocket, json.dumps({'status': 'ok', 'code': '0'}))

    logger.info('Client disconnected: ' + str(addr))

    # Force unsubscribe
    if(subscribeCallback is not None):
        manager.unsubscribe(identifer, subscribeCallback)

    clientsocket.close()

if __name__ == '__main__':

    # Logging
    logger = setup_custom_logger('myapp')

    # Update token from env
    if "SECRET_TOKEN" in os.environ:
        SECRET_TOKEN = os.environ.get('SECRET_TOKEN')
        logger.info('Update token from env')
    

    # Get port
    if "PORT" in os.environ:
        port = int(os.environ.get('PORT'))
    else:
        port = 5000

    s = socket.socket()
    host = socket.gethostname()
    s.bind((host, port)) 
    s.listen(500)

    logger.info('Listen on ' + str(port))

    while True:
       c, addr = s.accept()     # Establish connection with client.
       threading.Thread(target = on_new_client, args = (c,addr)).start()

    s.close()
