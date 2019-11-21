#TODO:
# 1) packet on the fly in time secquence, with CFCW/SFCW size info overlay
# 2) ack distence in time and packet number（发现ack间距大，而CFCW和SFCW又没有变大的问题）
import json
import os

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

frame_dict = {}
packet_sent_dict = {}
packet_received_dict = {}

def init(original_file_path):
    global frame_dict,packet_sent_dict,packet_received_dict
    (filepath, tempfilename) = os.path.split(original_file_path)
    (filename, extension) = os.path.splitext(tempfilename)
    with open('../data_converted/' + filename+ '_quic_connection.json', 'r') as load_f:
        load_dict = json.load(load_f)
        frame_dict = load_dict['frame_dict']
        packet_sent_dict = load_dict['packet_sent_dict']
        packet_received_dict = load_dict['packet_received_dict']

    print('load general info: ', len(load_dict['general_info']))
    print('load packet_sent: ', len(packet_sent_dict))
    print('load packet_received: ', len(packet_received_dict))
    print('load stream_dict: ', len(load_dict['stream_dict']))
    print('load frame_dict: ', len(frame_dict))

def show():
    show_packet_ack_delay_all()

def show_packet_ack_delay_all():
    packet_sent_time_sequence_list = []
    ack_delay_total_list = []
    ack_delay_server_list = []

    #calculate packet ack delay
    for packet in packet_sent_dict.values():
        packet_sent_time_sequence_list.append(int(packet['time']))
        ack_delay_total = int(packet['ack_delay'])
        ack_delay_total_list.append(ack_delay_total)
        ack_frame_id = packet['ack_by_frame']
        if ack_frame_id == 'N/A':
            if packet['info'][7][0][0] == 'ACK':
                ack_delay_server_list.append(0) # the last ack packet won't be acked, manually set the ack_delay_server to 0
            else:
                print('WARN: Possible error packet: ', packet['number'], ', which is not ACKed')
        else:
            ack_frame = frame_dict[ack_frame_id]
            ack_delay_server = round(float(ack_frame['delta_time_largest_observed_us'])/1000,3)
            ack_delay_server_list.append(ack_delay_server)

    #calculate rtt
    rtt_timestamp = []
    rtt_list = []
    for frame in frame_dict.values():
        if frame['frame_type'] == 'ACK' and frame['direction'] == 'receive':
            largest_observed_packet_number = frame['largest_observed']
            largest_observed_packet_ack_delay = packet_sent_dict[str(largest_observed_packet_number)]['ack_delay']
            ack_delay_server = round(float(frame['delta_time_largest_observed_us']) / 1000, 3)
            rtt = largest_observed_packet_ack_delay - ack_delay_server
            rtt_timestamp.append(int(packet_sent_dict[str(largest_observed_packet_number)]['time']))
            rtt_list.append(rtt)

    #calculate total packet size on the fly
    ack_time_cfcw_dict = {}
    for frame in frame_dict.values():
        if frame['frame_type'] == 'ACK' and frame['direction'] == 'receive':
            ack_packet_number_list = frame['ack_packet_number_list']
            total_ack_size = 0
            for ack_packet_number in ack_packet_number_list:
                ack_packet = packet_sent_dict[str(ack_packet_number)]
                ack_packet_length = ack_packet['length']
                total_ack_size += ack_packet_length
            ack_time_cfcw_dict[frame['time_elaps']] = total_ack_size


    packet_sent_list = list(packet_sent_dict.values())
    current_receiver_windows_offset = packet_sent_list[0]['length']
    on_the_fly_packet_size_list = [current_receiver_windows_offset]
    for i in range(1, len(packet_sent_list)):
        previous_packet = packet_sent_list[i - 1]
        packet = packet_sent_list[i]
        current_receiver_windows_offset += packet['length']
        for ack_time in ack_time_cfcw_dict.keys():
            if previous_packet['time'] < ack_time and packet['time'] >= ack_time:
                current_receiver_windows_offset -= ack_time_cfcw_dict[ack_time]
        on_the_fly_packet_size_list.append(current_receiver_windows_offset)


    # receive_time_list = []
    # for frame in frame_dict.values():
    #     if frame['frame_type'] == 'ACK' and frame['direction'] == 'receive':
    #         receive_time = packet_received_dict[str(frame['packet_number'])]['time']
    #         receive_time_list.append(receive_time)
    #
    # packet_sent_index = 0
    # current_on_the_fly_packet_size = 0
    # on_the_fly_packet_size = []
    # packet_sent_list = list(packet_sent_dict.values())
    # packet_time = 0
    # for timestamp in receive_time_list:
    #     while packet_time < timestamp:
    #         packet = packet_sent_list[packet_sent_index]
    #         packet_time = int(packet['time'])
    #         current_on_the_fly_packet_size += packet['length']
    #         on_the_fly_packet_size.append(current_on_the_fly_packet_size)
    #         packet_sent_index += 1
    #     current_on_the_fly_packet_size = 0
    # for i in range(len(packet_sent_list)-packet_sent_index):
    #     on_the_fly_packet_size.append(0)  # on the connection end stage, there're no data frame on the fly, so fill with 0 to match the count of packet_sent_list, otherwise matplot will raise an error


    #packet ack delay
    plt.subplot(211)
    plt.scatter(packet_sent_time_sequence_list, ack_delay_total_list, color='g', marker='.',label='Packet ack delay')
    plt.scatter(rtt_timestamp, rtt_list, color='r',marker='.', label='RTT')
    plt.xlabel('Packet Sent Time Offset (ms)')
    plt.ylabel('Latency (ms)')
    plt.title("Packet ACK Delay")
    plt.legend()

    #packet size on the fly
    plt.subplot(212)
    plt.plot(packet_sent_time_sequence_list, on_the_fly_packet_size_list, label='RTT')
    plt.xlabel('Packet Sent Time Offset (ms)')
    plt.ylabel('Packet Length On the Fly(bytes)')
    plt.legend()

    plt.show()



if __name__ == '__main__':
    init("../data_original/quic-gh2ir.json")
    show()
