Chrome log is important for QUIC server developers, it's one of the few QUIC log you can get, which including detailed Quic Connection/Stream/Frame logs.

But reading the log by netlog-viewer(https://netlog-viewer.appspot.com/) is painful, so I decided to make my own tool to speed up the process.

By this tool, you can
1) read QUIC client log on the packet/frame/stream level, each packet would be tagged by important info(eg. ack_delay), along with the content of the packet itself.
2) track the CFCW and SFCW related frames, which would be hlepful for analyzing the bottleneck of the throughput.
