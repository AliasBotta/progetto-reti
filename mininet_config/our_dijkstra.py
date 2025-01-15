from dataclasses import dataclass
from typing import List, Dict, Tuple, Set, Optional, Union, Any
from collections import defaultdict
import json
import sys

from ryu.base import app_manager
from ryu.app.rest_router import RestRouterAPI
from ryu.app.wsgi import ControllerBase, Request, Response, route, WSGIApplication
from ryu.topology.switches import Link, Switch, Port
from ryu.topology.api import get_all_switch, get_all_link
from ryu.ofproto import ofproto_v1_3

@dataclass(frozen=True)
class DijkstraDistanceEntry():
    """
    Classe che rappresenta una singola entry nel vettore utilizzato
    dall'algoritmo di Dijkstra per identificare un singolo nodo del
    grafo su cui calcolare i percorsi minimi.
    """

    cost: float
    previous_dpid: Optional[int]
    

class NetLinkGraph():
    """
    Classe che memorizza la topologia degli switch di una rete
    contenente più subnet all'interno di una matrice delle adiacenze.
    Tale matrice ha come entrate i costi dei collegamenti fra coppie
    di switch nella topologia.

    La funzione interna `weight_function` è usata per calcolare il costo
    di ciascun collegamento sulla base del loro ritardo di trasmissione e
    capacità di banda.
    Se tali informazioni sono assenti, si assume il costo unitario.
    """    

    def __init__(self, parent_app: app_manager.RyuApp, switches: List[Switch], links: Dict[Link, float], connection_parameters={}):
        self.parent_app = parent_app
        self.switch_map: Dict[int, Switch] = { switch.dp.id: switch for switch in switches }

        def weight_function(params: Optional[Dict[str, Any]]) -> float:
            if params is None:
                return 1 # Costo Unitario
            
            ALPHA, BETA = 1, 1
            r, C = params["delay"], params["bw"]
            r = float(r[:-2]) * (10 ** -3) # delay termina in "ms", da scartare; convertito da ms -> s
            C = float(C) * (10 ** 6)       # convertito da Mbps -> bps
            return (ALPHA * r) / (BETA * C)


        # Mappa (id_src, id_dst) -> Costo fra i link
        self.node_adjacency: Dict[Tuple[int, int], float] = defaultdict(lambda: 0)
        for link in links.keys():
            src: Port = link.src
            dst: Port = link.dst

            # I seguenti corrispondono ai PESI dei collegamenti fra switch ADIACENTI
            cost = weight_function(connection_parameters.get((src.dpid, dst.dpid), None))
            print(f"cost between {src.dpid} and {dst.dpid} = {cost}")
            self.node_adjacency[src.dpid, dst.dpid] = cost
            self.node_adjacency[dst.dpid, src.dpid] = cost
        print()

        # DEBUG CODE
        for (src_dpid, dst_dpid) in (self.node_adjacency.keys()):
            print(f"Lo switch {src_dpid} raggiunge {dst_dpid}")


    def dijkstra(self, starting_switch_id: int) -> Dict[int, DijkstraDistanceEntry]:
        """
        Metodo che calcola i percorsi minimi per raggiungere ogni subnet
        della rete a partire dallo switch avente come id `starting_switch_id`.
        Restituisce un dizionario contenente tutti i risultati ottenuti.
        """

        distances: Dict[int, DijkstraDistanceEntry] = {
            id: DijkstraDistanceEntry(
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
                    distances[neighboring_switch.dp.id] = DijkstraDistanceEntry(cost=new_cost, previous_dpid=current_switch)

        return distances


class DijkstraRouter(RestRouterAPI):
    """
    Classe controller ryu che funge da router per l'API REST.
    Estende la classe `RestRouterAPI` che implementa le funzionalità del server REST
    incluso insieme al codice di libreria di ryu, introducendo due nuove rotte descritte
    in `DijkstraCommand` per consentire il routing dinamico mediante algoritmo di Dijkstra.
    """

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
    """
    Classe che implementa le rotte aggiuntive con cui estendere
    l'API REST offerta dalla classe `RestRouterAPI`.
    """

    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.__app = data["app"] # Recuperiamo l'applicazione per poter
        # fare uso dell'API ryu.topology

    def distance_dict_to_json(self, net_graph: NetLinkGraph, networks: List[Dict[str, Union[int, List[str]]]], links: List[Dict[str, Any]]):
        """
        Metodo che, dato il grafo della topologia della rete ed
        informazioni riguardanti le subnet ed i link al suo interno,
        ricostruisce il percorso ottimale verso ogni subnet per ciascuno
        switch e restituisce il risultato in formato JSON compatibile con
        una successiva chiamata alla rotta /router/{switch_id} per applicare
        la configurazione calcolata.
        """

        response: List[Dict[str, Union[int, str]]] = []
        link_map: Dict[Tuple[int, int], Any] = {
            (entry["src_switch"]["id"], entry["dst_switch"]["id"]): entry
            for entry in links
        }

        # TODO: Avrebbe senso invertire questo mapping lato-client?
        all_subnets: Dict[str, int] = {
            subnet: network["switch_id"]
            for network in networks
            for subnet in network["subnets"]
        }

        for network in networks:
            switch_id: int = network["switch_id"] 
            subnets: List[str] = network["subnets"]

            results = net_graph.dijkstra(starting_switch_id=switch_id)
            def _path(to: int, _comes_from: int = None):
                if to == switch_id:
                    return _comes_from # Ultimo switch_id non nullo
                else:
                    return _path(to=results[to].previous_dpid, _comes_from=to)

            # Per ogni switch, generare percorso ottimale verso TUTTE le subnet
            response.extend({
                    "switch_id": switch_id,
                    "destination": subnet,
                    "gateway": link_map[switch_id, _path(to=dst_switch_id)]["dst_switch"]["ip_addr"],
                } for subnet, dst_switch_id in all_subnets.items()
                if subnet not in subnets
            )
        
        return json.dumps(response) # json.dumps è necessario?


    @route(name='calc_dijkstra', path='/dijkstra', methods=['POST'], requirements={})
    def calc_dijkstra(self, req: Request, use_params: bool = True, **_kwargs) -> Response:
        """
        Rotta che riceve in POST i dati che descrivono le subnet utenti della topologia
        di rete su cui determinare le rotte ottimali mediante algoritmo di Dijkstra.
        """
        switch_list: List[Switch] = get_all_switch(self.__app)
        links_dict: Dict[Link, float] = get_all_link(self.__app)

        """
        FORMATO RICHIESTA:
        {
            "networks": [
                { "switch_id": <id>, "subnets": [ <ip_net_addr>, ... ] },
                { ... }
            ],
            "links": [

                # RISOLTO! Possiamo associare a ogni coppia (switch_src, switch_dst)
                # un valore di ip_addr di "reperibilità"
                # e.g. (sw1, sw3) -> "200.0.0.2" perché sw1 "pinga" sw3 su quell'indirizzo
                # NOTA: *NON* vi è simmetria!!!!!!!!!!!!!!!!!
                # e.g. (sw3, sw1) -> "200.0.0.1" perché sw3 "pinga" sw1 su un ALTRO indirizzo

                # In questa maniera, è possibile capire cosa mettere nel campo gateway del
                # valore di ritorno del metodo `dict_to_json`

                { "src_switch": { "id": id_switch_1, "ip_addr": <ip_addr_1> }, "dst_switch": { "id": id_switch_2, "ip_addr": <ip_addr_2> }, "ritardo": ..., "capacità": ... },
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
            { "switch_id": id_switch, "destination": ip_rete_destinazione, "gateway": ip_switch_neighbor },
            { <gli stessi dati, ma per un'altra rotta su un altro switch> },
            ...
            <ogni switch dovrebbe avere una rotta per ciascuna subnet nota>
        ]
        """
        request = json.loads(req.body)
        print(request)

        connection_parameters = {
            (int(link["src_switch"]["id"]), int(link["dst_switch"]["id"])): {
                "bw": link["bw"],
                "delay": link["delay"]
            }
            for link in request["links"]
        } if use_params else {}

        net_graph = NetLinkGraph(parent_app=self.__app, switches=switch_list, links=links_dict, connection_parameters=connection_parameters)
        json_response = self.distance_dict_to_json(net_graph=net_graph, networks=request["networks"], links=request["links"])
        return Response(status=200, content_type="application/json", body=json_response)
        

    @route(name='calc_dijkstra', path='/dijkstra_unit', methods=['POST'], requirements={})
    def calc_dijkstra_unit(self, req: Request, **_kwargs) -> Response:
        """
        Una rotta aggiuntiva per applicare l'algoritmo di Dijkstra
        con costo unitario, senza considerare eventuali parametri di banda e delay.
        """
        return self.calc_dijkstra(req=req, use_params=False)
