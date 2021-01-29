from utils import send, ffmpeg, generate_sdp
from commands import Commands
import sdp_transform
import time
import json
from kube_api import KubernetesAPIClient
from pprint import pprint

class GenerateCall():

    def __init__(self, address, port, sdp_address, audio_file, token, host):
        self.address = address
        self.port = port
        self.sdp_address = sdp_address
        self.audio_file = audio_file
        self.token = token
        self.host = host
        self.apis = []
        self.calls = []
        self.commands = Commands()

    def generate_calls(self, cnt):
        ''' Generate a given number of calls.

        The first call will have these ports: offer - 3002 and answer - 
        3004 and it will increase always by two. This is important to debug
        if somethin went wrong. 

        It will use the ffmpeg command to create subprocesses which runs 
        almost side-by-side. 

        Watch out for the cnt because it can produce a huge load cause the 
        ffmpeg memory usage. 

        Args:
        cnt: Number of concurrent calls. 
        '''

        start_port = 3000
        offers = []; answers = []
        
        for _ in range(cnt):
            # Offer
            start_port += 2
            sdp_offer = self.commands.offer(
                generate_sdp('127.0.0.1', start_port),
                # generate_sdp(self.sdp_address, start_port),
                str(start_port) + "-" + str(start_port + 2),
                "from-tag" + str(start_port),
                ICE="remove",
                label="caller",
            )

            offer = send(
                self.address, self.port, sdp_offer,
                self.sdp_address, start_port
            )

            self.calls.append({
                'call_id': str(start_port) + "-" + str(start_port + 2), 
                'from-tag': "from-tag" + str(start_port)
            })

            # Answer
            start_port += 2
            sdp_answer = self.commands.answer(
                generate_sdp('127.0.0.1', start_port),
                # generate_sdp(self.sdp_address, start_port),
                str(start_port - 2) + "-" + str(start_port),
                "from-tag" + str(start_port - 2), "to-tag" + str(start_port - 2),
                ICE="remove",
                label="callee"
            ) 
            answer = send(
                self.address, self.port, sdp_answer,
                self.sdp_address, start_port
            )

            # self.calls.append({
            #     'call_id': str(start_port-2) + "-" + str(start_port), 
            #     'from-tag': "from-tag" + str(start_port)
            # })

            query = send(
                self.address, self.port, 
                self.commands.query(str(start_port - 2) + "-" + str(start_port)),
                self.sdp_address, 2998
            )

            parsed_offer = sdp_transform.parse(offer.get('sdp'))
            parsed_answer = sdp_transform.parse(answer.get('sdp'))

            # pprint(parsed_offer)
            # pprint(parsed_answer)
            
            # offer_rtp_port = parsed_offer.get('media')[0].get('port')
            # answer_rtp_port = parsed_answer.get('media')[0].get('port')

            # offer_rtcp_port = parsed_offer.get('media')[0].get('rtcp').get('port')
            # answer_rtcp_port = parsed_answer.get('media')[0].get('rtcp').get('port')

            offer_rtp_port = query['tags']["from-tag" + str(start_port - 2)]['medias'][0]['streams'][0]['local port']
            answer_rtp_port = query['tags']["to-tag" + str(start_port - 2)]['medias'][0]['streams'][0]['local port']
            
            offer_rtcp_port = query['tags']["from-tag" + str(start_port - 2)]['medias'][0]['streams'][1]['local port']
            answer_rtcp_port = query['tags']["to-tag" + str(start_port - 2)]['medias'][0]['streams'][1]['local port']

            print(f'Offer RTP port: {offer_rtp_port}, RTCP port {offer_rtcp_port}!')
            print(f'Answer RTP port: {answer_rtp_port}, RTCP port {answer_rtcp_port}!')

            offers.append(f'rtp://{self.address}:{str(offer_rtp_port)}?localrtpport={str(start_port - 2)}')
            answers.append(f'rtp://{self.address}:{str(answer_rtp_port)}?localrtpport={str(start_port)}')

            api_offer = KubernetesAPIClient(
                self.token, self.host,
                call_id=str(start_port - 2) + "-" + str(start_port),
                tag="from-tag" + str(start_port - 2),
                # local_ip='127.0.0.1',
                local_ip=self.sdp_address,
                local_rtp_port=start_port - 2,
                local_rtcp_port=start_port - 1,
                remote_rtp_port=offer_rtp_port,
                remote_rtcp_port=offer_rtcp_port
            )

            api_answer = KubernetesAPIClient(
                self.token, self.host,
                call_id=str(start_port - 2) + "-" + str(start_port),
                tag="to-tag" + str(start_port - 2),
                # local_ip='127.0.0.1',
                local_ip=self.sdp_address,
                local_rtp_port=start_port,
                local_rtcp_port=start_port + 1,
                remote_rtp_port=answer_rtp_port,
                remote_rtcp_port=answer_rtcp_port
            )

            api_offer.create_resources()
            api_answer.create_resources()

            self.apis.append(api_offer)
            self.apis.append(api_answer)

        time.sleep(1)
        ffmpeg(self.audio_file, cnt, offers, answers)

    def get_apis(self):
        return self.apis

    def delete_calls(self):
        for call in self.calls:
            deleted_call = send(
                self.address, self.port, 
                self.commands.delete(call['call_id'], call['from-tag']), 
                self.sdp_address, 3000
            )
            pprint(deleted_call)