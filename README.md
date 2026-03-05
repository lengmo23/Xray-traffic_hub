# Xray Traffic Hub

A lightweight, centralized real-time traffic monitoring dashboard for multi-node Xray environments. 

## Features

* **Real-Time Monitoring:** WebSocket-based dashboard for millisecond-level traffic updates. Zero bandwidth waste when the page is closed.
* **Token-Based Authentication:** Nodes report data using dynamically generated UUID tokens instead of hardcoded node IDs, ensuring high security.
* **Peak Preservation Algorithm:** Automatically handles Xray's daily 23:59 data reset bug to preserve the actual daily peak traffic.
* **Telegram Integration:** Daily automated traffic reports and manual real-time push via the Web UI.
* **Web Management:** Add, rename, or completely delete nodes directly from the dashboard.

## Installation

Run the following command on a fresh Ubuntu/Debian/CentOS server to deploy the Master Hub:

```bash
bash <(curl -s [https://raw.githubusercontent.com/lengmo23/Xray-traffic_hub/main/install.sh](https://raw.githubusercontent.com/lengmo23/Xray-traffic_hub/main/install.sh))
