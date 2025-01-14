from dataclasses import dataclass
from typing import List, Dict, Tuple, Set, Optional, Union
from collections import defaultdict
import json
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

@dataclass(frozen=True)
class DistanceEntry():
    cost: int
    previous_dpid: Optional[int]
    

class NetLinkGraph():
    def __init__(self, parent_app: app_manager.RyuApp, switches: List[Switch], links: Dict[Link, float], connection_parameters={}):
        self.parent_app = parent_app
        self.switch_map: Dict[int, Switch] = { switch.dp.id: switch for switch in switches }

        # Mappa (id_src, id_dst) -> Costo fra i link
        self.node_adjacency: Dict[Tuple[int, int], float] = defaultdict(lambda: 0)
        for link in links.keys():
            src: Port = link.src
            dst: Port = link.dst

            def weight_function(params):
                # r, C = params["r"], params["C"]
                return 1

            # I seguenti corrispondono ai PESI dei collegamenti fra switch ADIACENTI
            self.node_adjacency[src.dpid, dst.dpid] = weight_function(connection_parameters.get((src.dpid, dst.dpid), None))
            self.node_adjacency[dst.dpid, src.dpid] = 1 # Superfluo, credo

        # DEBUG CODE
        for (src_dpid, dst_dpid) in (self.node_adjacency.keys()):
            print(f"Lo switch {src_dpid} raggiunge {dst_dpid}")

    def dijkstra(self, starting_switch_id: int) -> Dict[int, DistanceEntry]:
        distances: Dict[int, DistanceEntry] = {
            id: DistanceEntry(
                cost=(0 if id == starting_switch_id else sys.maxsize),
                previous_dpid=None
            )
            for id in self.switch_map.keys()
        }
        to_explore: Set[int] = set(self.switch_map.keys())
        
        # Funzione helper che, identificato lo switch con id `switch_id`,
        # restituisce tutti gli altri switch ad esso adiacente
        def yield_neighbors_of(switch_id: int):
            this_switch = self.switch_map[switch_id]
            for other_switch in self.switch_map.values():
                if other_switch != this_switch and self.node_adjacency[this_switch.dp.id, other_switch.dp.id]:
                    yield other_switch

        while to_explore:
            current_switch = min(filter(to_explore.__contains__, distances), key=lambda d: distances.get(d).cost)
            to_explore.remove(current_switch)
            for neighboring_switch in yield_neighbors_of(current_switch):
                if neighboring_switch.dp.id not in to_explore: # Già visitato!
                    continue

                new_cost = distances[current_switch].cost + self.node_adjacency[current_switch, neighboring_switch.dp.id]
                if new_cost < distances[neighboring_switch.dp.id].cost:
                    distances[neighboring_switch.dp.id] = DistanceEntry(cost=new_cost, previous_dpid=current_switch)

        return distances


class DijkstraRouter(RestRouterAPI):
    _CONTEXTS = { 'wsgi': WSGIApplication }
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        wsgi = kwargs['wsgi']
        wsgi.register(DijkstraCommand, {
            "app": self # Necessario per consentire al controller di
            # ricevere dati sulla topologia tramite l'API ryu.topology
        })


class DijkstraCommand(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.__app = data["app"] # Recuperiamo l'applicazione per poter
        # fare uso dell'API ryu.topology

    def distance_dict_to_json(self, net_graph: NetLinkGraph, networks: List[Dict[str, Union[int, List[str]]]]):
        response: List[Dict[str, Union[int, str]]] = []
        all_subnets: Dict[str, int] = {
            subnet: network["switch_id"]
            for network in networks
            for subnet in network["subnets"]
        }

        for network in networks:
            switch_id: int = network["switch_id"] 
            subnets: List[str] = network["subnets"]

            results = net_graph.dijkstra(starting_switch_id=switch_id)
            def _path(to: int, __comes_from: int = None):
                if to == switch_id:
                    return __comes_from # Ultimo switch_id non nullo
                else:
                    return _path(to=results[to].previous_dpid, __comes_from=to)

            # Per ogni switch, generare percorso ottimale verso TUTTE le subnet
            response.extend({
                    "switch_id": switch_id,
                    "destination": subnet,
                    "gateway": _path(to=dst_switch_id),
                } for subnet, dst_switch_id in all_subnets
                if subnet not in subnets
            )


    @route(name='calc_dijkstra', path='/dijkstra', methods=['GET', 'POST'], requirements={})
    def calc_dijkstra(self, req: Request, **_kwargs) -> Response:
        switch_list: List[Switch] = get_all_switch(self.__app)
        links_dict: Dict[Link, float] = get_all_link(self.__app)

        # lista = json.loads(req.body)
        """
        FORMATO RICHIESTA:
        {
            # TODO: Capire come fare per risalire all'IP dell'interfaccia a cui inoltrare ...
            "networks": [
                { "switch_id": <id>, "subnets": [ <ip_net_addr>, ... ] },
                { ... }
            ],
            "links": [
                { "switch_src": id_switch_1, "switch_dst": id_switch_2, "ritardo": ..., "capacità": ... },
                { "switch_src": id_switch_2, "switch_dst": id_switch_1, "ritardo": ..., "capacità": ... },
                ...
            ]
        }
        """

        # DEBUG
        # for r, it in results.items():
            # print(f"id={r} con costo {it.cost} (Prev: id={net_graph.switch_map[it.previous_dpid].dp.id if it.previous_dpid else None})")        
        # print()

        """
        FORMATO RISPOSTA:
        [
            { "switch": id_switch, "destination": ip_rete_destinazione, "gateway": ip_switch_neighbor },
            { <gli stessi dati, ma per un'altra rotta su un altro switch> },
            ...
            <ogni switch dovrebbe avere una rotta per ciascuna subnet nota>
        ]
        """
        request = json.loads(req.body)
        net_graph = NetLinkGraph(parent_app=self.__app, switches=switch_list, links=links_dict)
        json_response = self.distance_dict_to_json(net_graph=net_graph, networks=request["networks"])
        return Response(status=200, content_type="application/json", body=json_response)
        
