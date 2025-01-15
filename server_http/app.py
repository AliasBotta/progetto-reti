import sqlite3
import subprocess
import time
import threading
import socket
from datetime import datetime
from statistics import mean, stdev

from flask import Flask, render_template, request, jsonify 
# jsonfy è una funzione di Flask che converte i dati di input in una risposta formattata come JSON

app = Flask(__name__)

DATABASE = 'rtt_measurements.db'
PING_INTERVAL = 1

# Variabili globali per gestire lo stato della misurazione
measurement_thread = None #contiene il riferimento al thread che esegue la funzione di misurazione del RTT
stop_flag = False # segnale di interruzione per il thread di misurazione
current_measurements = [] # lista atta a memorizzare i risultati temporanei delle misurazioni RTT
start_time = None # memorizza il timestamp di inizio della misurazione corrente, serve a determinare la durata della misurazione
current_ip_dest = None # ip dell'host da pingare
test_duration = 0 # durata del test in secondi
measurement_start_dt = None # come start_time, serve però a memorizzare la timestamp sul database

def init_db():
    """
    Inizializza il database SQLite e crea la tabella measurements se non esiste.
    """
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor() # crea un cursore che funge da intermediario tra python e il db
    c.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            ip_dest TEXT NOT NULL,
            ip_src TEXT NOT NULL,
            rtt REAL NOT NULL,
            duration INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_measurement(timestamp, ip_dest, ip_src, rtt, duration):
    """
    Inserisce una singola misurazione RTT nel database.
    """
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO measurements (timestamp, ip_dest, ip_src, rtt, duration)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, ip_dest, ip_src, rtt, duration))
    conn.commit()
    conn.close()

def get_ip_src():
    """
    Rileva l'indirizzo IP sorgente della macchina (server) aprendo
    una connessione fittizia verso 8.8.8.8 per capire l'interfaccia usata.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip_src = sock.getsockname()[0]
        sock.close()
    except:
        ip_src = "127.0.0.1" # !!! mettere qui l'indirizzo di default
    return ip_src

def ping_once(ip_dest):
    """
    Esegue 'ping -c 1 -W 1 ip_dest' e ritorna l'RTT in ms (float),
    oppure None se non riesce.
    """
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip_dest],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if "time=" in line:
                    rtt_str = line.split("time=")[1].split(" ")[0]
                    return float(rtt_str)
    except Exception as e:
        print("Errore ping:", e)
    return None

def measure_rtt(ip_dest, duration):
    """
    Thread che esegue un ping ogni PING_INTERVAL secondi, salvando i risultati
    nel DB e in current_measurements. Si interrompe se stop_flag è True
    o se è trascorsa la durata.
    """
    global stop_flag, current_measurements, start_time # specifico che utilizzerò queste variabili globali
    ip_src = get_ip_src() 
    start_time = time.time()
    end_time = start_time + duration

    while True:
        if stop_flag:
            break
        if time.time() > end_time:
            break

        rtt_ms = ping_once(ip_dest)
        if rtt_ms is not None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elapsed = time.time() - start_time
            insert_measurement(now, ip_dest, ip_src, rtt_ms, duration)
            current_measurements.append((elapsed, rtt_ms))
        time.sleep(PING_INTERVAL)

@app.route('/')
def index():
    """
    Pagina principale: form per inserire IP/Hostname + durata,
    e pulsante per avviare misurazione o vedere lo storico.
    """
    return render_template('index.html')

@app.route('/start_measurement', methods=['POST'])
def start_measurement():
    """
    Avvia una nuova misurazione RTT in un thread separato.
    """
    global measurement_thread, stop_flag, current_measurements
    global current_ip_dest, test_duration, start_time, measurement_start_dt

    stop_flag = False
    current_measurements = []

    current_ip_dest = request.form.get('ip_dest')  # IP o hostname
    test_duration = int(request.form.get('duration', 10))

    measurement_start_dt = datetime.now()

    measurement_thread = threading.Thread(
        target=measure_rtt,
        args=(current_ip_dest, test_duration)
    )
    measurement_thread.start()

    return render_template('results.html', ip_dest=current_ip_dest)

@app.route('/stop_measurement', methods=['POST'])
def stop_measurement():
    """
    Ferma la misurazione corrente impostando stop_flag.
    """
    global stop_flag
    stop_flag = True
    return jsonify({"status": "stopped"}) 

@app.route('/get_current_data', methods=['GET'])
def get_current_data():
    """
    Restituisce i dati (elapsed, rtt) della sessione corrente + stat (media, std).
    Se non ci sono misurazioni, ritorna un array vuoto.
    """
    global current_measurements
    if not current_measurements:
        return jsonify([])

    rtt_vals = [m[1] for m in current_measurements]
    if len(rtt_vals) > 1:
        avg_rtt = mean(rtt_vals)
        std_rtt = stdev(rtt_vals)
    else:
        avg_rtt = rtt_vals[0] if rtt_vals else 0
        std_rtt = 0

    return jsonify({
        "measurements": current_measurements,
        "avg_rtt": avg_rtt,
        "std_rtt": std_rtt
    })

@app.route('/get_history_data', methods=['GET'])
def get_history_data():
    """
    Restituisce i dati storici (old_data e new_data) FILTRATI per l'host corrente,
    in modo che il grafico in results.html mostri solo misure relative a current_ip_dest.
    """
    global measurement_start_dt, current_ip_dest

    # 1) Recupera l'host della misurazione corrente via query param (o fallback a current_ip_dest)
    host = request.args.get('ip_dest', current_ip_dest)
    if not host:
        return jsonify({})  # se manca, ritorna vuoto

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # 2) Seleziona TUTTE le misure per quell'host, ordinate per ID
    c.execute("""
        SELECT timestamp, rtt
        FROM measurements
        WHERE ip_dest = ?
        ORDER BY id ASC
    """, (host,))
    rows = c.fetchall()
    conn.close()

    # 3) Separa in old_vals/new_vals basandoci su measurement_start_dt
    old_vals = []
    new_vals = []
    for row in rows:
        ts_str, rtt_val = row
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        if measurement_start_dt and dt >= measurement_start_dt:
            new_vals.append(rtt_val)
        else:
            old_vals.append(rtt_val)

    # 4) Creiamo (x,y) per old e new
    old_data = [(i, old_vals[i]) for i in range(len(old_vals))]
    base_index = len(old_vals)
    new_data = [(base_index + i, new_vals[i]) for i in range(len(new_vals))]

    # 5) Calcoliamo la media e std su tutti i rtts di quell'host
    all_rtts = old_vals + new_vals
    if len(all_rtts) > 1:
        hist_avg = mean(all_rtts)
        hist_std = stdev(all_rtts)
    elif len(all_rtts) == 1:
        hist_avg = all_rtts[0]
        hist_std = 0
    else:
        hist_avg = 0
        hist_std = 0

    return jsonify({
        "old_data": old_data,
        "new_data": new_data,
        "hist_avg": hist_avg,
        "hist_std": hist_std
    })

@app.route('/show_history', methods=['GET'])
def show_history():
    """
    Mostra una pagina di storico dedicata a un singolo host (IP/hostname).
    """
    host = request.args.get('ip_dest', None)
    if not host:
        return "Nessun host specificato", 400
    return render_template('history.html', ip_dest=host)

@app.route('/get_host_history_data', methods=['GET'])
def get_host_history_data():
    """
    Restituisce TUTTE le misurazioni fatte a uno specifico host,
    + stat (media, std) e la lista per tabella.
    """
    host = request.args.get('ip_dest', None)
    if not host:
        return jsonify({"error": "No host provided"}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, ip_dest, ip_src, rtt, duration
        FROM measurements
        WHERE ip_dest = ?
        ORDER BY id ASC
    ''', (host,))
    rows = c.fetchall()
    conn.close()

    rtt_vals = [r[3] for r in rows]
    if len(rtt_vals) > 1:
        avg_rtt = mean(rtt_vals)
        std_rtt = stdev(rtt_vals)
    elif len(rtt_vals) == 1:
        avg_rtt = rtt_vals[0]
        std_rtt = 0
    else:
        avg_rtt = 0
        std_rtt = 0

    # Costruzione dati x,y per il grafico
    data_for_chart = []
    for i, r in enumerate(rows):
        data_for_chart.append({
            "x": i,
            "y": r[3]  # rtt
        })

    # Lista misurazioni integrale per la tabella
    measurements_list = []
    for r in rows:
        measurements_list.append({
            "timestamp": r[0],
            "ip_dest":   r[1],
            "ip_src":    r[2],
            "rtt":       r[3],
            "duration":  r[4]
        })
    measurements_list.reverse() # inverti la lista per una migliore resa visiva della tabella

    return jsonify({
        "chart_data": data_for_chart,
        "avg_rtt": avg_rtt,
        "std_rtt": std_rtt,
        "measurements": measurements_list
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)