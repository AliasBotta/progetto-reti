from mininet.topo import Topo

class TestTopology(Topo):
    """Topologia di test per il progetto."""

    def build(self):
        h1, h2 = self.addHost('h1'), self.addHost('h2')
        s1 = self.addSwitch('s1')

        self.addLink(h1, s1)
        self.addLink(s1, h2)


# Mininet si aspetta che sia presente un dizionario `topos`
# nello scope globale del proprio file di configurazione,
# contenente tutte le topologie custom che si desidera utilizzare.
topos: dict[str, Topo] = {
    "test": TestTopology,
}
