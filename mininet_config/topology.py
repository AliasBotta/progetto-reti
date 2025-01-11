from mininet.topo import Topo

class TestTopology(Topo):
    """Topologia di test per il progetto."""

    def build(self):
        h1, h2 = self.addHost('h1'), self.addHost('h2')
        s1 = self.addSwitch('s1')

        self.addLink(h1, s1)
        self.addLink(s1, h2)


class ProjectTopology(Topo):
    """Topologia assegnata per il progetto da realizzare."""

    def build(self):
        # Subnet 1
        h1 = self.addHost('h1', ip='10.0.0.1/24')
        h2 = self.addHost('h2', ip='10.0.0.2/24')
        sw1 = self.addSwitch('sw1')
        for host in (h1, h2):
            self.addLink(host, sw1, bw=100, delay='0.05ms')

        # Subnet 2
        h3 = self.addHost('h3', ip='11.0.0.1/24')
        sw2 = self.addSwitch('sw2')
        self.addLink(h3, sw2, bw=1, delay='0.5ms')

        # Subnet 3
        h4 = self.addHost('h4', ip='192.168.1.1/24')
        sw3 = self.addSwitch('sw3')
        self.addLink(h4, sw3, bw=100, delay='0.05ms')

        # Subnet 4
        h5 = self.addHost('h5', ip='10.8.1.1/24')
        sw4 = self.addSwitch('sw4')
        self.addLink(h5, sw4, bw=100, delay='0.05ms')

        # Switch 5 interposto fra il 2 e 4
        sw5 = self.addSwitch('sw5')

        # Link per collegare i diversi switch fra di loro
        self.addLink(sw1, sw2, bw=20, delay='2ms')
        self.addLink(sw1, sw3, bw=1,  delay='2ms')
        self.addLink(sw2, sw5, bw=20, delay='2ms')
        self.addLink(sw3, sw4, bw=5,  delay='2ms')
        self.addLink(sw4, sw5, bw=20, delay='2ms')
    

# Mininet si aspetta che sia presente un dizionario `topos`
# nello scope globale del proprio file di configurazione,
# contenente tutte le topologie custom che si desidera utilizzare.
topos = {
    "test": TestTopology,
    "project": ProjectTopology,
}
