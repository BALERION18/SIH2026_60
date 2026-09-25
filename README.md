# ❄️ Himantar — SIH 2026 Project Repository

> **Digital Platform for Efficient Remote Management of Indian Antarctic Research Stations**

**Himantar** is a comprehensive **edge-to-cloud monitoring, digital twin, and synchronization system** designed for remote management of India's Antarctic research stations — **Maitri** and **Bharati**.

The system combines **Edge AI, Digital Twins, predictive analytics, offline-first architecture, IoT monitoring, and bandwidth-efficient synchronization** to operate reliably under extreme environmental conditions and severely constrained connectivity.

---

## 🏆 Project Information

| Field             | Details                                                                                |
| ----------------- | -------------------------------------------------------------------------------------- |
| **Project Title** | Himantar                                                                               |
| **Team Name**     | TEAM_LAKSHYA                                                                                 |
| **PS ID**         | SIH`26060`                                                                                |
| **PS Title**      | Digital Platform for efficient remote management of Indian Antarctic Research Stations |
| **Organization**  | Ministry of Earth Sciences (MoES)                                                      |
| **Department**    | National Centre for Polar and Ocean Research (NCPOR)                                   |
| **Category**      | Software                                                                               |
| **Theme**         | Smart Automation                                                                       |

---

## 🎯 Problem Statement

Develop a **Digital Twin framework for Maitri and Bharati stations** integrating:

* 🏗️ Infrastructure monitoring
* ⚡ Energy management
* 🚢 Logistics planning
* 🌡️ Environmental monitoring
* 🤖 Predictive analytics
* 📡 Remote station synchronization

The primary challenge is maintaining reliable station monitoring despite **extreme weather, intermittent connectivity, and severely constrained satellite bandwidth**.

---

## 💡 Proposed Solution

### Himantar — A Dual-Twin Edge-to-Cloud Framework

Himantar provides a unified digital replica of **Maitri and Bharati Antarctic research stations** through a **Dual-Twin Architecture**.

Instead of continuously transmitting the complete station state to the cloud, Himantar separates computation between the **Edge Twin** and the **Cloud Twin**.

### 🧊 Edge Twin

Runs directly at the Antarctic station.

* Operates independently during network outages
* Performs real-time anomaly detection
* Generates local life-safety alerts
* Buffers telemetry locally
* Runs predictive models close to the source
* Continues functioning without cloud connectivity

### ☁️ Cloud Twin

Runs at the central headquarters.

* Provides centralized monitoring
* Maintains long-term historical data
* Performs large-scale analytics
* Supports predictive logistics planning
* Synchronizes station data when connectivity is available

This architecture prevents the Digital Twin from becoming dependent on the unreliable satellite link.

---

# 🚀 Key Features

## 🕵️ Black-Box Incident Recording

Himantar maintains a dedicated incident data window around critical events.

```text
        INCIDENT
           │
           ▼
◄──────────┼──────────►
  5 Hours  │  5 Hours
   Before  │   After
```

The system preserves telemetry surrounding an incident to support:

* Root-cause analysis
* Incident investigation
* System diagnostics
* Post-event analysis
* AI model improvement

---

## 🔄 Dual-Twin Framework

A synchronized digital representation of **Maitri and Bharati stations** with separate Edge and Cloud intelligence.

---

## 🤖 Predictive Survival AI

The predictive engine correlates:

* Generator loads
* Historical consumption
* Weather conditions
* Environmental parameters
* Station operational patterns

to forecast **winter fuel consumption and burn-rates**, helping optimize annual ship-based resupply planning.

---

## ⚡ Zero-Latency Edge AI

Critical anomaly detection happens directly on the station.

```text
IoT Sensors
     ↓
Edge Server
     ↓
Edge AI Engine
     ↓
Anomaly Detected
     ↓
Immediate Local Alert
```

The system does **not require cloud connectivity** to detect and respond to critical local events.

---

## 📦 Payload Crushing

Satellite bandwidth is extremely limited.

Instead of transmitting bulky JSON payloads, Himantar uses **Protocol Buffers (Protobuf)** to serialize telemetry into compact binary messages.

```text
Large JSON Payload
       ↓
   Protobuf
       ↓
Compact Binary Payload
       ↓
Satellite Link
       ↓
Cloud
```

This significantly reduces the communication overhead and allows the Digital Twin to remain synchronized even under constrained connectivity.

---


## 📡 Offline Store-and-Forward

When connectivity is unavailable, station telemetry is stored locally and synchronized once the link becomes available again.

```text
          Connectivity Available
                   │
                   ▼
Sensor → InfluxDB → Sync Queue → Cloud
                   ▲
                   │
          Connectivity Lost
                   │
                   ▼
             Local Buffer
```

The Edge Twin continues operating normally while data is safely buffered locally.

---

# 🏗️ System Architecture

```text
┌──────────────────────────────┐
│      BHARATI / MAITRI        │
│          STATION              │
│            EDGE               │
├──────────────────────────────┤
│                              │
│      IoT Sensor Array        │
│              │               │
│              ▼               │
│      ┌────────────────┐      │
│      │ Rugged Edge    │      │
│      │    Server      │      │
│      │                │      │
│      │  Edge Twin     │      │
│      │  + Edge AI     │      │
│      └───────┬────────┘      │
│              │               │
│              ▼               │
│      ┌────────────────┐      │
│      │    InfluxDB    │      │
│      │ Local Buffer   │      │
│      └────────────────┘      │
│                              │
└──────────────┬───────────────┘
               │
               │ Satellite Link
               │
               │ MQTT + Protobuf
               │
               ▼
┌──────────────────────────────┐
│       NCPOR HEADQUARTERS     │
│          CLOUD / GOA         │
├──────────────────────────────┤
│                              │
│      React Web Portal        │
│              │               │
│              ▼               │
│       Cloud API / Server     │
│              │               │
│              ▼               │
│      Cloud Database          │
│              │               │
│              ▼               │
│   Predictive Analytics AI    │
│                              │
└──────────────────────────────┘
```

📖 **Detailed architecture:** `docs/architecture.md`

---

# 🛠️ Technology Stack

## Frontend

* **React.js**
* **Next.js**
* **Tailwind CSS**
* **Recharts**
* **Framer Motion**

## Backend

* **Node.js**
* **Express.js**
* **Python**
* **Socket.IO**

## AI & Predictive Analytics

* **Python**
* **Scikit-learn**
* **Pandas**
* **TensorFlow**

## Databases

* **PostgreSQL**
* **Neon**
* **InfluxDB**

## DevOps & IoT

* **Docker**
* **Kubernetes**
* **GitHub**
* **Render**
* **Mosquitto MQTT**
* **Protocol Buffers**

## Security

* **mTLS**
* **HMAC**
* **RBAC**

---

# 📁 Repository Structure

```text
Himantar/
│
├── 📁 backend/
│   ├── 📁 cloud/              # Central HQ API & cloud synchronization
│   ├── 📁 edge/               # Local station API & Edge AI engine
│   ├── 📁 proto/              # Protocol Buffer definitions
│   ├── 📁 shared/
|   ├── 📁 scripts/            #scripts for toggling 
|   ├──  📁 tests/      
│   └── 📁 simulator/          # Link outage & station simulators
│
├── 📁 frontend/
│   ├── 📁 public/              # Static assets, logos & images
│   └── 📁 src/
│       ├── 📁 components/      # Dashboards, maps & UI components
│       ├── 📁 hooks/           # Custom React hooks
|       ├── 📁 context/
|       ├── 📁 assets/          #logos
│       └── 📁 pages/           # Analytics, Energy, Logistics, etc.
│
├── 📁 assets1/
│   └── 📁 screenshots/         # UI screenshots & prototype images
│
├── 📄 README.md

```

---

# 🔗 Important Links

### 🌐 Live Application

**Himantar Web Portal**

https://sih-2026-two-xi.vercel.app/login

### 🎨 Final Presentation

**Canva Presentation**

https://www.canva.com/design/DAHU0OfrKqg/0Wo7qd8pr7rvN0hGPtC-dQ/edit

### 🎥 Demo Video

A comprehensive walkthrough of the Himantar platform, architecture, and simulation:

https://www.youtube.com/watch?v=9kXuhC71zNw

---

# 🖼️ Screenshots & Prototype

UI screenshots and prototype images are available in:

```text
assets/screenshots/
```

The collection includes interfaces for:

* 📊 Station Dashboard
* 🗺️ GIS Mapping
* ⚡ Energy Monitoring
* 🚢 Logistics Management
* 📈 Analytics
* 🌡️ Environmental Monitoring

---

# ⚙️ Installation & Setup

## 1. Clone the Repository

```bash
git clone https://github.com/YourUsername/Project-Himantar.git
cd Project-Himantar
```

---

## 2. Start the Backend

Open a terminal and run:

```bash
cd backend
python dev_server.py
```

---

## 3. Start the Frontend

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at the local development URL displayed in your terminal.

Typically:

```text
http://localhost:5173
```

---

# 🔐 Security Architecture

Himantar incorporates multiple security mechanisms to protect station telemetry and communication.

| Security Layer     | Technology                |
| ------------------ | ------------------------- |
| Authentication     | RBAC                      |
| Transport Security | mTLS                      |
| Message Integrity  | HMAC                      |
| Access Control     | Role-Based Access Control |
| Data Communication | MQTT + Protobuf           |
| Edge Isolation     | Local Edge Processing     |

---

# 🧪 Simulation

The repository includes station and connectivity simulators for testing the system under realistic Antarctic operating conditions.

The simulator can reproduce scenarios such as:

* 📡 Satellite link outages
* 🔄 Store-and-forward synchronization
* ⚡ Generator load variations
* 🌡️ Environmental changes
* 🚨 Critical incidents
* 📦 Payload transmission
* ☁️ Edge-to-cloud synchronization

This allows the complete architecture to be tested without requiring physical Antarctic hardware.

---

# 🔮 Future Scope

## 🌍 Scalability

Expand the Digital Twin framework to additional remote and polar research stations.

## 🌡️ Climate Research Integration

Integrate Himantar's environmental and predictive data with broader climate research initiatives.

## 🤖 Advanced AI

Enhance predictive models for:

* Energy consumption
* Equipment failures
* Weather impact
* Fuel requirements
* Maintenance scheduling

## 🛰️ Communication Optimization

Further improve synchronization protocols for extremely low-bandwidth and intermittent satellite communication.

## 🔧 Hardware Integration

Deploy ruggedized Edge Computing nodes with localized sensors designed for extreme cold environments.

---

# 🌟 Why Himantar?

Traditional cloud-first monitoring systems depend heavily on network availability.

Antarctic research stations cannot.

Himantar follows an **Edge-first, Cloud-assisted** philosophy:

```text
             ┌─────────────────────┐
             │     CLOUD DOWN      │
             └──────────┬──────────┘
                        │
                        ▼
              ┌──────────────────┐
              │   EDGE CONTINUES │
              │     OPERATING    │
              └────────┬─────────┘
                       │
             Local AI + Alerts
                       │
                       ▼
              Local Data Buffer
                       │
                       │
              Connectivity Restored
                       │
                       ▼
                 Cloud Sync
```

### ❄️ Built for the Edge.

### 📡 Designed for the Disconnect.

### 🤖 Powered by Intelligence.

### 🇮🇳 Built for India's Antarctic Research.

---

## 👥 Team

### VajraX

**Smart Automation | SIH 2026**

> Building resilient digital infrastructure for the world's most extreme environments.
