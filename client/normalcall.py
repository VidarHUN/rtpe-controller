import random
import sdp_transform
import time
import logging
from callbase import CallBase
from commands import Commands

class NormalCall(CallBase):

    def __init__(self, start, end, **kwargs):
        super().__init__(
            local_address=kwargs.get('local_address', None),
            protocol=kwargs.get('protocol', None),
            rtpe_address=kwargs.get('rtpe_address', None),
            rtpe_port=kwargs.get('rtpe_port', None)
        )
        self.start = start
        self.end = end
        self.call_id = f'{str(self.start)}-{str(self.end)}'
        self.from_tag = f'from-tag{str(self.start)}'
        self.to_tag = f'to-tag{str(self.start)}'
        self.sender_method = kwargs.get('sender_method', None)
        self.file = kwargs.get('file', None)

    def generate_sdp(self, address, port):
        sdp_dict = {
            'version': 0,
            'origin': {
                'address': address,
                'ipVer': 4,
                'netType': 'IN',
                'sessionId': random.randint(1000000000, 9999999999),
                'sessionVersion': 1,
                'username': '-'
            },
            'name': 'tester',
            'connection': {'ip': address, 'version': 4},
            'timing': {'start': 0, 'stop': 0},
            'media': [
                {
                    'direction': 'sendrecv',
                    'fmtp': [],
                    'payloads': 0,
                    'port': port,
                    'protocol': 'RTP/AVP',
                    'rtp': [],
                    'type': 'audio'
                }
            ]
        }
        return sdp_transform.write(sdp_dict)

    def offer(self):
        options = {"ICE": "remove", "label": "caller"}
        command = Commands.offer(
            self.generate_sdp('127.0.0.1', self.start),
            self.call_id, self.from_tag, **options
        )
        data = super().ws_send(command) if super().__getattribute__('protocol') == 'ws' else super().send(command, self.start)
        if not data:
            logging.error("No data come back from rtpengine. (offer)") 
            return None
        sdp_data = sdp_transform.parse(data["sdp"])
        return sdp_data['media'][0]['port']

    def answer(self):
        options = {"ICE": "remove", "label": "callee"}
        command = Commands.answer(
            self.generate_sdp('127.0.0.1', self.end),
            self.call_id, self.from_tag, self.to_tag, **options
        )
        data = super().ws_send(command) if super().__getattribute__('protocol') == 'ws' else super().send(command, self.end)
        if not data:
            logging.error("No data come back from rtpengine (answer)")
            return None
        sdp_data = sdp_transform.parse(data["sdp"])
        return sdp_data['media'][0]['port']

    def delete(self):
        super().delete(self.call_id, self.from_tag, self.start)

    def generate_call(self):
        rtpe_address = super().__getattribute__('rtpe_address')
        start_time = time.time()

        o_rtp = self.offer()
        if not o_rtp: return None
        
        a_rtp = self.answer()
        if not a_rtp: return None
        
        end_time = time.time()
        logging.info(f'Call with callid: {self.call_id} created in {int((end_time - start_time) * 1000)} ms')

        if self.sender_method == 'ffmpeg':
            return [
                f'ffmpeg -re -i {self.file} -ar 8000 -ac 1 -acodec pcm_mulaw -f rtp rtp://{rtpe_address}:{o_rtp}?localrtpport={self.start}',
                f'ffmpeg -re -i {self.file} -ar 8000 -ac 1 -acodec pcm_mulaw -f rtp rtp://{rtpe_address}:{a_rtp}?localrtpport={self.end}'
            ]
        if self.sender_method == 'rtpsend':
            return [
                f'rtpsend -s {self.start} -f {self.file} {rtpe_address}/{o_rtp}',
                f'rtpsend -s {self.end} -f {self.file} {rtpe_address}/{a_rtp}'
            ]
        if self.sender_method == 'wait':
            return ['sleep 600']