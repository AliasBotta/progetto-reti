from typing import List, Dict, Tuple
import sys

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.topology import event
from ryu.topology.switches import Link, Switch, Port
from ryu.topology.api import get_all_switch, get_all_link
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3


class NetLinkGraph():
    def __init__(self, links: Dict[Link, float]):
        self.node_adjacency: Dict[Tuple[str, str], int] = {}
        for link in links.keys():
            src: Port = link.src
            dst: Port = link.dst

            # Mappa (id_src, id_dst) -> Costo fra i link
            self.node_adjacency[src.hw_addr, dst.hw_addr] = 1
            self.node_adjacency[dst.hw_addr, src.hw_addr] = 1 # Superfluo, no?

        # DEBUG CODE
        for (src_port, dst_port) in sorted(self.node_adjacency.keys()):
            print(f"La porta {src_port} raggiunge {dst_port}")
        print()



"""
def dijkstra(graph, source):
    dist, prev = {}, {}
    queue = []

    for node in graph:
        dist[node] = sys.maxsize
        prev[node] = None
        queue.append(node)
    dist[source] = 0
    
    while queue:
        u = queue.pop(0) # Prendere nodo con distanza minima
        
        for v in neighbors(u):
            if v not in Q:
                continue

            alt = dist[u] + graph[u][v]
            if alt < dist[v]:
                dist[v] = alt
                prev[v] = u

    return dist, prev
"""

class L2Switch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    EVENTS = [
        event.EventSwitchEnter,
        event.EventSwitchLeave, event.EventPortAdd,
        event.EventPortDelete, event.EventPortModify,
        event.EventLinkAdd, event.EventLinkDelete
    ]

    def __init__(self, *args, **kwargs):
        super(L2Switch, self).__init__(*args, **kwargs)

    @set_ev_cls(EVENTS, dispatchers=MAIN_DISPATCHER)
    def switch_handler(self, ev):
        switch_list: List[Switch] = get_all_switch(self)
        links_dict: Dict[Link, float] = get_all_link(self)

        obj = NetLinkGraph(links=links_dict)

        
