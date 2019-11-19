import csv
import json

ingore_event_type_list = [
    'QUIC_SESSION_PACKET_AUTHENTICATED',
    'QUIC_SESSION_PADDING_FRAME_SENT',
    'QUIC_SESSION_PADDING_FRAME_RECEIVED',
    'SIGNED_CERTIFICATE_TIMESTAMPS_CHECKED',
    'CERT_VERIFIER_REQUEST',
    'CERT_VERIFIER_REQUEST_BOUND_TO_JOB',
    'QUIC_SESSION_CERTIFICATE_VERIFIED'
]


class QuicConnection:
    def __init__(self,chrome_event_list,persistant_file_path):
        self.persistant_file_path = persistant_file_path
        self.quic_chrome_event_list = []

        #extract quic event and connection start time
        for event in chrome_event_list:
            if event.source_type == 'QUIC_SESSION' and event.event_type not in ingore_event_type_list:
                self.quic_chrome_event_list.append(event)
                if event.event_type == 'QUIC_SESSION':
                    self.start_time_int = event.time_int
            else:
                #print('ignore NONE quic event,', event.get_info_list())
                pass

        #construct quic data structure
        self.packets = []
        self.frames = []
        self.stream_dict = {}
        self.packet_sent_dict = {}
        self.packet_received_dict = {}
        self.construct_quic_data_structure(self.quic_chrome_event_list)
        self.tag_packet_by_ack()

    def construct_quic_data_structure(self, event_list):
        i = 0
        event_list = event_list.copy()
        length = len(event_list)
        print('events to process: ',length)

        sent_event_buffer = []
        received_event_buffer = []
        while i < length:
            event = event_list[i]
            if event.event_type == 'QUIC_SESSION':
                print('quic session found, host: ', event.other_data['params']['host'],'port: ', event.other_data['params']['port'])
            elif event.event_type == 'QUIC_SESSION_VERSION_NEGOTIATED':
                print('quic version: ', event.other_data['params']['version'])
            elif event.event_type == 'QUIC_SESSION_PACKET_RECEIVED':
                #search the next packet received event
                for j in range(i+1,length):
                    next_event = event_list[j]
                    if ('RECEIVED' in next_event.event_type or 'READ' in next_event.event_type) and next_event.event_type != 'QUIC_SESSION_PACKET_RECEIVED' :
                        received_event_buffer.append(next_event)
                    if next_event.event_type == 'QUIC_SESSION_PACKET_RECEIVED' or j == length-1: #j==length-1 means no more events to handle, so it's an exit point
                        packet_received = PacketReceived(self, event, received_event_buffer)
                        self.add_packet(packet_received)
                        self.packet_received_dict[packet_received.packet_number] = packet_received
                        for del_event in received_event_buffer:
                            event_list.remove(del_event)
                        length -= len(received_event_buffer)
                        received_event_buffer = []
                        break
            elif event.event_type == 'QUIC_SESSION_PACKET_SENT':
                packet_sent = PacketSent(self, event, sent_event_buffer)
                self.add_packet(packet_sent)
                self.packet_sent_dict[packet_sent.packet_number] = packet_sent
                sent_event_buffer = []
            elif 'SENT' in event.event_type or 'SEND' in event.event_type:
                sent_event_buffer.append(event)
            else:
                print('WARN: ignore quic event: ', event.get_info_list())
            i += 1

        print('quic session analyzation finished')
        print('packet: ', len(self.packets))
        print('stream: ', len(self.stream_dict.keys()))
        print('frame: ', len(self.frames))

    def tag_packet_by_ack(self):
        largest_observed_packet = 0
        for frame in self.frames:
            if frame.frame_type == 'ACK' and frame.direction == 'receive':
                latest_largest_observed_packet = frame.largest_observed
                for i in range(largest_observed_packet+1, latest_largest_observed_packet+1):
                    packet = self.packet_sent_dict[i]
                    packet.ack_by_frame_id = frame.frame_id
                    frame_time_elaps = self.packet_received_dict[frame.packet_number].time_elaps
                    packet.ack_delay = frame_time_elaps - packet.time_elaps
                largest_observed_packet = latest_largest_observed_packet


    def add_packet(self,packet):
        packet.time_elaps = packet.time_int - self.start_time_int
        self.packets.append(packet)


    def add_frame(self,frame):
        self.frames.append(frame)
        stream_id = frame.stream_id
        if stream_id in self.stream_dict.keys():
            self.stream_dict[stream_id].append(frame.frame_id)
        else:
            self.stream_dict[stream_id] = [frame.frame_id]


    def save(self):
        print('saving quic_session.csv...')
        with open(self.persistant_file_path +'_quic_session.csv', 'wt') as f:
            cw = csv.writer(f)
            for event in self.quic_chrome_event_list:
                cw.writerow(event.get_info_list())

        print('saving quic_packet.csv...')
        with open(self.persistant_file_path +'_quic_packet.csv', 'wt') as f:
            cw = csv.writer(f)
            cw.writerow(['Time', 'Time Elaps', 'Type', 'Packet Number','Size'])
            for packet in self.packets:
                cw.writerow(packet.get_info_list())

        print('saving quic_frame.csv...')
        with open(self.persistant_file_path +'_quic_frame.csv', 'wt') as f:
            cw = csv.writer(f)
            cw.writerow(['Frame type', 'Direction','Stream_id'])
            for packet in self.frames:
                cw.writerow(packet.get_info_list())

        #construct json obj
        print('saving quic_connection.json...')
        json_obj = {
            'packets_sent': [],
            'packets_received': [],
            'stream_dict': self.stream_dict,
            'frame_dict': {frame.frame_id: frame.__dict__ for frame in self.frames}
        }
        for packet in self.packet_sent_dict.values():
            packet_json_obj = {
                'direction':'send',
                'time': packet.time_elaps,
                'number': packet.packet_number,
                'ack_by_frame' : packet.ack_by_frame_id,
                'ack_delay': packet.ack_delay,
                'info': packet.get_info_list(),
                'frame_ids':[frame.frame_id for frame in packet.frames]
            }
            json_obj['packets_sent'].append(packet_json_obj)

        for packet in self.packet_received_dict.values():
            packet_json_obj = {
                'direction':'receive',
                'time': packet.time_elaps,
                'number': packet.packet_number,
                'info': packet.get_info_list(),
                'frame_ids':[frame.frame_id for frame in packet.frames]
            }
            json_obj['packets_received'].append(packet_json_obj)

        with open(self.persistant_file_path +'_quic_connection.json', "w") as f:
            json.dump(json_obj, f)


class PacketReceived:
    def __init__(self, quic_connection, packet_received_event, relate_events):
        self.relate_events = relate_events.copy()
        if self.relate_events[0].event_type != 'QUIC_SESSION_UNAUTHENTICATED_PACKET_HEADER_RECEIVED':
            raise BaseException('QUIC_SESSION_PACKET_RECEIVED event followed by illigal event type: %s' % self.relate_events[0].event_type)

        self.time_int = packet_received_event.time_int
        self.time_elaps = 0
        self.type = 'PacketReceived'
        self.source_id = packet_received_event.source_id
        self.peer_address = packet_received_event.other_data['params']['peer_address']
        self.self_address = packet_received_event.other_data['params']['self_address']
        self.size = packet_received_event.other_data['params']['size']

        self.connection_id = self.relate_events[0].other_data['params']['connection_id']
        self.packet_number = self.relate_events[0].other_data['params']['packet_number']
        self.reset_flag = self.relate_events[0].other_data['params']['reset_flag']
        self.version_flag = self.relate_events[0].other_data['params']['version_flag']
        self.relate_events.pop(0)

        self.frames = []
        self.init_frame(self.relate_events)
        for i in range(len(self.frames)):
            frame = self.frames[i]
            frame.frame_id = '%s_%s_%s' % (self.type, self.packet_number, i)
            quic_connection.add_frame(frame)

    def init_frame(self, related_sent_event):
        events_buffer = []
        last_frame_received_event = None
        for event in related_sent_event:
            if 'FRAME_RECEIVED' in event.event_type or event == related_sent_event[-1]: #if current event is the last event, the last QuicFrame must be create before loop end
                if last_frame_received_event != None:
                    frame = QuicFrame(self.packet_number, last_frame_received_event, events_buffer)
                    self.frames.append(frame)
                    events_buffer = []
                last_frame_received_event = event
            else:
                events_buffer.append(event)

    def get_info_list(self):
        return [
            self.time_int,
            self.time_elaps,
            self.type,
            self.packet_number,
            self.size,
            self.peer_address,
            self.self_address,
            self.connection_id,
            self.reset_flag,
            self.version_flag,
            [frame.get_info_list() for frame in self.frames]
        ]


class PacketSent:
    def __init__(self, quic_connection, QUIC_SESSION_PACKET_SENT_event, related_event):
        self.time_int = QUIC_SESSION_PACKET_SENT_event.time_int
        self.time_elaps = 0
        self.type = 'PacketSent'
        self.source_id = QUIC_SESSION_PACKET_SENT_event.source_id
        self.packet_number = QUIC_SESSION_PACKET_SENT_event.other_data['params']['packet_number']
        self.size = QUIC_SESSION_PACKET_SENT_event.other_data['params']['size']
        self.transmission_type = QUIC_SESSION_PACKET_SENT_event.other_data['params']['transmission_type']
        self.ack_by_frame_id = 0
        self.ack_delay = 0 # ms

        self.frames = []
        self.init_frame(related_event.copy())
        for i in range(len(self.frames)):
            frame = self.frames[i]
            frame.frame_id = '%s_%s_%s' % (self.type, self.packet_number, i)
            quic_connection.add_frame(frame)

    def init_frame(self, related_sent_event):
        events_buffer = []
        for event in related_sent_event:
            if 'FRAME_SENT' in event.event_type:
                frame = QuicFrame(self.packet_number, event, events_buffer)
                self.frames.append(frame)
                events_buffer = []
            else:
                events_buffer.append(event)

    def get_info_list(self):
        return [
            self.time_int,
            self.time_elaps,
            self.type,
            self.packet_number,
            self.size,
            self.ack_delay,
            self.transmission_type,
            [frame.get_info_list() for frame in self.frames]
        ]


class QuicStream:
    def __init__(self):
        self.frames = []

    def add_frame(self,frame):
        self.frames.append(frame)


class QuicFrame:
    def __init__(self,packet_number, event, relate_events):
        relate_events = relate_events.copy()
        self.info_list = []
        self.frame_type = None
        self.frame_id = None
        self.packet_number = packet_number

        if event.event_type == 'QUIC_SESSION_STREAM_FRAME_SENT':
            self.frame_type = 'STREAM'
            self.direction = 'send'
            self.stream_id = event.other_data['params']['stream_id']
            self.length = event.other_data['params']['length']
            self.offset = event.other_data['params']['offset']
            self.info_list.extend([self.frame_type,self.direction,self.stream_id,self.length,self.offset])
        elif event.event_type == 'QUIC_SESSION_STREAM_FRAME_RECEIVED':
            self.frame_type = 'STREAM'
            self.direction = 'receive'
            self.stream_id = event.other_data['params']['stream_id']
            self.length = event.other_data['params']['length']
            self.offset = event.other_data['params']['offset']
            self.info_list.extend([self.frame_type,self.direction,self.stream_id,self.length,self.offset])
        elif event.event_type == 'QUIC_SESSION_ACK_FRAME_SENT':
            self.frame_type = 'ACK'
            self.direction = 'send'
            self.stream_id = 'NONE'
            self.largest_observed = event.other_data['params']['largest_observed']
            self.missing_packets = event.other_data['params']['missing_packets']
            self.delta_time_largest_observed_us = event.other_data['params']['delta_time_largest_observed_us']
            self.received_packet_times = event.other_data['params']['received_packet_times']
            self.info_list.extend([self.frame_type,self.direction,self.largest_observed,self.missing_packets,self.delta_time_largest_observed_us,self.received_packet_times])
        elif event.event_type =='QUIC_SESSION_ACK_FRAME_RECEIVED':
            self.frame_type = 'ACK'
            self.direction = 'receive'
            self.stream_id = 'NONE'
            self.largest_observed = event.other_data['params']['largest_observed']
            self.missing_packets = event.other_data['params']['missing_packets']
            self.delta_time_largest_observed_us = event.other_data['params']['delta_time_largest_observed_us']
            self.received_packet_times = event.other_data['params']['received_packet_times']
            self.info_list.extend([self.frame_type,self.direction,self.largest_observed,self.missing_packets,self.delta_time_largest_observed_us,self.received_packet_times])
        elif event.event_type == 'QUIC_SESSION_BLOCKED_FRAME_SENT':
            self.frame_type = 'BLOCKED'
            self.direction = 'send'
            self.stream_id = event.other_data['params']['stream_id']
            self.info_list.extend([self.frame_type,self.direction,self.stream_id])
        elif event.event_type== 'QUIC_SESSION_WINDOW_UPDATE_FRAME_RECEIVED':
            self.frame_type = 'WINDOW_UPDATE'
            self.direction = 'receive'
            self.stream_id = event.other_data['params']['stream_id']
            self.byte_offset = event.other_data['params']['byte_offset']
            self.info_list.extend([self.frame_type,self.direction,self.stream_id,self.byte_offset])
        else:
            print('WARN: unhandled sent frame',event.event_type)
        self.info_list.extend([event.get_info_list() for event in relate_events])


    def get_info_list(self):
        return self.info_list


