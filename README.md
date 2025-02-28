# Technical Report
**Network Experiments with Mininet**

**Authors:**  
- **Alessandro Botta [0752081]**  
- **Domenico Puglisi [0750729]**  

**Academic Year 2024/2025 – Bachelor’s Degree in Computer Science**  
**Date:** 16/01/2025  
**Supervisor:** Prof. Fabrizio Giuliano  

---

## Abstract
This document describes the development and implementation of a network communication system based on **Software Defined Networking (SDN)**, carried out by Alessandro Botta and Domenico Puglisi. The project leverages **Mininet** to emulate a network with multiple switches, routers, and hosts, and uses the **Ryu** controller to dynamically configure IP addresses and flow tables through a Dijkstra-based routing algorithm. A key feature of the project is the development of an HTTP server (using **Flask**) to measure the Round Trip Time (RTT) between different network nodes and record the results in an **SQLite** database.  

All technical details, including source code, are provided in the GitHub repository. This report offers a detailed overview of the network architecture and analyzes the measured RTT values in light of the theoretical performance expectations.

---

## Project Structure

Within the repository, the most relevant folders and files are organized as follows:

```
.
├── mininet_config
│   ├── our_dijkstra.py         # Ryu-based SDN controller with Dijkstra routing
│   ├── pyproject.toml          # Dependencies and project setup configuration
│   ├── topology.py             # Python script for creating the Mininet network topology
│   └── uv.lock                 # Lock file for reproducible environment installs
├── README.md                   # Main project documentation
└── server_http
    ├── app.py                  # Flask application to measure and display RTT
    ├── static/                 # CSS and JS dependencies (Bootstrap, Chart.js, etc.)
    │   ├── css
    │   │   └── bootstrap.min.css
    │   └── js
    │       ├── bootstrap.min.js
    │       ├── chart.js
    │       ├── chartjs-plugin-annotation
    │       └── jquery.slim.min.js
    └── templates/              # HTML templates for the Flask front end
        ├── base.html
        ├── history.html
        ├── index.html
        └── results.html
```

- **mininet_config**: Contains all code related to network topology and the Dijkstra-based SDN controller in Ryu, as well as project dependencies.  
- **server_http**: Contains the Flask application that measures RTT and displays results in real time or from historical data.  

---

## Network Implementation

### 1. Development Environment Configuration
An essential first step involved creating a consistent **Python** environment for **Mininet**, **Ryu**, and **Flask** to run seamlessly. Given that **Ryu** requires compatibility with **Python 3.9**, our choice was fixed to this version. The files `pyproject.toml` and `uv.lock` within `mininet_config` list the dependencies, enabling a reproducible setup.

Key points:
- **Mininet** is typically run on an **Ubuntu Server 20.04** image.  
- Installation of Ryu often requires:
  ```bash
  pip install ryu
  ```
  inside a Python **3.9** virtual environment.  
- We used the tool **uv** (or standard `venv`) to manage the isolated environment, ensuring no conflicts with other system packages.

### 2. Network Topology
The topology is defined in **`mininet_config/topology.py`**. The network consists of:
- **Four subnets** (each /24) with multiple hosts:
  - Each subnet’s **gateway** IP is the .254 address.
  - Host addresses start from .1 up to .253.
- **Five switches** interconnected by multiple /30 subnets to simulate point-to-point connections:
  - Each /30 subnet has exactly two usable IP addresses, one per switch interface.
- **Bandwidth (`bw`)** and **latency (`delay`)** parameters are assigned to each link for realistic simulation.
- **Default gateways** for hosts are the IP addresses of their corresponding subnet switch.  
- Switches are in **OpenFlow** mode (specifically `OpenFlow13`) so that the Ryu controller can program flow tables.

During initialization, each switch is provided an IP address by sending **POST** requests to the REST API exposed by the Ryu controller (running on a known port, usually `8080`), thus allowing remote configuration of routing parameters.

### 3. OpenFlow Controller
We use a **custom Ryu controller** to configure dynamic routing based on **Dijkstra’s algorithm**. The relevant code can be found in **`mininet_config/our_dijkstra.py`**, which extends Ryu’s **RestRouterAPI** to:
- Set up IP addresses on each switch interface automatically.
- Create static routes in the switch flow tables, reflecting the best paths computed by Dijkstra.  
- Expose specialized endpoints (`/dijkstra` and `/dijkstra_unit`) where the user can choose the cost model:
  - **Unit cost** (simple hop count).
  - **Weighted cost** (factoring in bandwidth and delay).

### 4. HTTP Server for RTT Measurement
The Flask server is in **`server_http/app.py`**:
1. **Web Interface (HTML Templates)** in `templates/`:
   - **index.html**: Basic form to select the target host and measurement duration.  
   - **results.html**: Displays current RTT data in near real-time.  
   - **history.html**: Lists historical measurements, retrieved from the SQLite database.  

2. **Endpoint REST**:
   - **`/start_measurement`**: Initiates a separate thread that repeatedly pings a specified host.  
   - **`/get_current_data`**: Returns JSON of ongoing measurement data.  
   - **`/get_history_data`**: Queries SQLite for past measurements.  

---

## Final Considerations
This project provided hands-on insights into **SDN architectures** and network emulation with Mininet. Key achievements:
- **Detailed Dijkstra Implementation**: By extending Ryu’s `RestRouterAPI`, we unified IP assignment, flow-table configuration, and route calculation under one controller.
- **Comprehensive Measurements**: The Flask-based HTTP server proved effective for gathering and visualizing RTT data.
- **Software Compatibility**: We overcame challenges with **Python 3.9** vs. Ryu dependencies, ensuring a reproducible environment.

