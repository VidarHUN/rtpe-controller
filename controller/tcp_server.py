import socket
import threading
import socketserver
import logging
import bencodepy
import time
import random
import string
from utils import *
from sockets import TCPSocket

bc = bencodepy.Bencode(
    encoding='utf-8'
)

rtpe_socket = None
envoy_socket = None

config = {}

class TCPRequestHandler(socketserver.BaseRequestHandler):

    def handle(self):
        global rtpe_socket
        global envoy_socket
        raw_data = str(self.request.recv(4096), 'utf-8')
        data = parse_data(raw_data)
        call_id = " "
        if "call-id" in data:
            call_id = ''.join(e for e in data['call-id'] if e.isalnum()).lower()
        logging.info(f'Received {data["command"]}')
        logging.debug(f'Received message: {raw_data}')

        if config['sidecar_type'] == 'l7mp':
            raw_response = rtpe_socket.send(raw_data)
            if raw_response:
                response = parse_bc(raw_response)
                if 'sdp' in response:
                    response['sdp'] = response['sdp'].replace('127.0.0.1', config['ingress_address'])
                self.request.sendall(bytes(data['cookie'] + " " + bc.encode(response).decode(), 'utf-8'))
                logging.debug("Response from rtpengine sent back to client")
                if data['command'] == 'delete':
                    delete_kube_resources(call_id)
                if data['command'] == 'answer':
                    query = parse_bc(rtpe_socket.send(query_message(call_id)))
                    create_resource(call_id, data['from-tag'], data['to-tag'], config, query)
        if config['sidecar_type'] == 'envoy':
            raw_response = rtpe_socket.send(raw_data)
            if raw_response:
                response = parse_bc(raw_response)
                if 'sdp' in response:
                    response['sdp'] = response['sdp'].replace('127.0.0.1', config['ingress_address'])
                self.request.sendall(bytes(data['cookie'] + " " + bc.encode(response).decode(), 'utf-8'))
                logging.debug("Response from rtpengine sent back to client")
                if data['command'] == 'answer':
                    raw_query = rtpe_socket.send(query_message(data['call-id']))
                    logging.debug(f"Query for {call_id} sent out")
                    if not raw_query:
                        logging.exception('Cannot make a query to rtpengine.')
                    else:
                        query = parse_bc(raw_query)
                        logging.debug(f"Received query: {str(query)}")
                        json_data = create_json(
                            query['tags'][data['from-tag']]['medias'][0]['streams'][0]['local port'],
                            query['tags'][data['to-tag']]['medias'][0]['streams'][0]['local port'],
                            call_id
                        )
                        logging.debug(f"Data to envoy: {json_data}")
                        envoy_socket.send(json_data, no_wait_response=True)
                        logging.debug("After envoy send")

# class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
#     pass

def serve(conf):
    global config
    global rtpe_socket
    global envoy_socket
    config = conf

    rtpe_socket = TCPSocket(conf['rtpe_address'], conf['rtpe_port'], delay=45)
    envoy_socket = TCPSocket(conf['envoy_address'], conf['envoy_port'])

    HOST, PORT = config['local_address'], int(config['local_port'])
    with socketserver.TCPServer((HOST, PORT), TCPRequestHandler) as server:
        server.serve_forever()
    # server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    # with server:
    #     server_thread = threading.Thread(target=server.serve_forever)
    #     try:
    #         server_thread.daemon = True
    #         server_thread.start()
    #         logging.info(f"Server loop running in thread: {server_thread.name}")
    #         server_thread.run()
    #     except KeyboardInterrupt:
    #         server.shutdown()