const mqtt = require('mqtt');
const WebSocket = require('ws');
const http = require('http');
const fs = require('fs');
const path = require('path');

// Configuration
// Override with: MQTT_BROKER=mqtt://<broker-ip> npm start
const MQTT_BROKER = process.env.MQTT_BROKER || 'mqtt://localhost';
const TEAM_ID = 'dragonfly';
const MQTT_TOPIC_VS = `vision/${TEAM_ID}/movement`;
const MQTT_TOPIC_SNAP = `vision/${TEAM_ID}/snapshot`;   // face snapshot (base64 JPEG)
const MQTT_TOPIC_HB = `vision/${TEAM_ID}/heartbeat`;    // PC + ESP8266 heartbeats
const WS_PORT = 9002;
const HTTP_PORT = 8080; // Port for Dashboard HTML

// --- MQTT Client ---
console.log(`Connecting to MQTT Broker: ${MQTT_BROKER}...`);
const mqttClient = mqtt.connect(MQTT_BROKER);

mqttClient.on('connect', () => {
    console.log(`Connected to MQTT Broker.`);
    mqttClient.subscribe([MQTT_TOPIC_VS, MQTT_TOPIC_SNAP, MQTT_TOPIC_HB], (err) => {
        if (!err) {
            console.log(`Subscribed to: ${MQTT_TOPIC_VS}, ${MQTT_TOPIC_SNAP}, ${MQTT_TOPIC_HB}`);
        } else {
            console.error('MQTT Subscription Error:', err);
        }
    });
});

mqttClient.on('message', (topic, message) => {
    const msgString = message.toString();
    // Snapshot payloads embed a base64 JPEG -- don't dump them to the console
    const preview = msgString.length > 200
        ? `${msgString.slice(0, 200)}... (${msgString.length} bytes)`
        : msgString;
    console.log(`MQTT IN [${topic}]: ${preview}`);

    // Broadcast to all WS clients
    broadcast(msgString);
});

// --- WebSocket Server ---
const wss = new WebSocket.Server({ port: WS_PORT });

console.log(`WebSocket Server started on port ${WS_PORT}`);

wss.on('connection', (ws) => {
    console.log('New WebSocket Client connected');

    // Send initial status
    ws.send(JSON.stringify({ type: 'STATUS', message: 'Connected to Vision Backend' }));

    ws.on('close', () => {
        console.log('Client disconnected');
    });
});

function broadcast(data) {
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(data);
        }
    });
}

// --- HTTP Server for Dashboard ---
const server = http.createServer((req, res) => {
    if (req.url === '/' || req.url === '/index.html') {
        fs.readFile(path.join(__dirname, '../../dashboard/index.html'), (err, data) => {
            if (err) {
                res.writeHead(500);
                res.end('Error loading dashboard');
                return;
            }
            res.writeHead(200, { 'Content-Type': 'text/html' });
            res.end(data);
        });
    } else {
        res.writeHead(404);
        res.end('Not Found');
    }
});

server.listen(HTTP_PORT, () => {
    console.log(`HTTP Dashboard running on http://localhost:${HTTP_PORT}`);
});
