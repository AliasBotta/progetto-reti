from dataclasses import dataclass
from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict
import sys

from ryu.base import app_manager
from ryu.app.rest_router import RestRouterAPI
from ryu.app import rest_router
from ryu.app.wsgi import ControllerBase, Request, Response, route, WSGIApplication
from ryu.controller import ofp_event
from ryu.topology import event
from ryu.topology.switches import Link, Switch, Port, Host
from ryu.topology.api import get_all_switch, get_all_link, get_host
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3

@dataclass()
class DistanceEntry():
    cost: int
    previous_dpid: Optional[int]
    

class NetLinkGraph():
    def __init__(self, parent_app: app_manager.RyuApp, switches: List[Switch], links: Dict[Link, float]):
        self.parent_app = parent_app
        self.switch_map: Dict[int, Switch] = { switch.dp.id: switch for switch in switches }

        self.node_adjacency: Dict[Tuple[int, int], int] = defaultdict(lambda: 0)
        for link in links.keys():
            src: Port = link.src
            dst: Port = link.dst

            # Mappa (id_src, id_dst) -> Costo fra i link
            self.node_adjacency[src.dpid, dst.dpid] = 1
            self.node_adjacency[dst.dpid, src.dpid] = 1 # Superfluo, no?

        # DEBUG CODE
        for (src_dpid, dst_dpid) in (self.node_adjacency.keys()):
            print(f"Lo switch {src_dpid} raggiunge {dst_dpid}")
        # print()
        # for src_port in set(src_port for src_port, _ in self.node_adjacency.keys()):
            # switch = self.switch_map[src_port.dpid]
            # print(f"La porta {src_port.hw_addr} ha switch {switch}")

    def dijkstra(self, starting_switch_id: int) -> Dict[int, DistanceEntry]:
        distances: Dict[int, DistanceEntry] = {
            id: DistanceEntry(
                cost=(0 if id == starting_switch_id else sys.maxsize),
                previous_dpid=None
            )
            for id in self.switch_map.keys()
        }
        queue: Set[int] = set(self.switch_map.keys())
        
        def yield_neighbors_of(switch_id: int):
            this_switch = self.switch_map[switch_id]
            for other_switch in self.switch_map.values():
                if other_switch != this_switch and self.node_adjacency[this_switch.dp.id, other_switch.dp.id]:
                    yield other_switch

        while queue:
            u = min(filter(queue.__contains__, distances), key=lambda d: distances.get(d).cost)
            queue.remove(u)
            for v in yield_neighbors_of(u):
                if v.dp.id not in queue: # Già visitato!
                    continue

                new_cost = distances[u].cost + self.node_adjacency.get((u, v.dp.id))
                if new_cost < distances[v.dp.id].cost:
                    distances[v.dp.id] = DistanceEntry(cost=new_cost, previous_dpid=u)

        return distances


class DijkstraRouter(RestRouterAPI):
    _CONTEXTS = { 'wsgi': WSGIApplication }
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    EVENTS = [
        event.EventSwitchEnter,
        event.EventSwitchLeave, event.EventPortAdd,
        event.EventPortDelete, event.EventPortModify,
        event.EventLinkAdd, event.EventLinkDelete
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        wsgi = kwargs['wsgi']
        wsgi.register(DijkstraCommand, { "app": self })


class DijkstraCommand(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.__app = data["app"]

    @route(name='calc_dijkstra', path='/dijkstra', methods=['GET', 'POST'], requirements={})
    def calc_dijkstra(self, req: Request, **_kwargs) -> Response:
        switch_list: List[Switch] = get_all_switch(self.__app)
        links_dict: Dict[Link, float] = get_all_link(self.__app)

        obj = NetLinkGraph(parent_app=self.__app, switches=switch_list, links=links_dict)
        results = obj.dijkstra(starting_switch_id=switch_list[0].dp.id)

        # DEBUG
        for r, it in results.items():
            print(f"id={r} con costo {it.cost} (Prev: id={obj.switch_map[it.previous_dpid].dp.id if it.previous_dpid else None})")        
        print()

        return Response(status=200)
        
