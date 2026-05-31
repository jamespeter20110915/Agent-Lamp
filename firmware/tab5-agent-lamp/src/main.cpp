#include <Arduino.h>
#include <ESPmDNS.h>
#include <M5Unified.h>
#include <WebServer.h>
#include <WiFi.h>

#if __has_include("agent_lamp_secrets.h")
#include "agent_lamp_secrets.h"
#endif

#ifndef AGENT_LAMP_WIFI_SSID
#define AGENT_LAMP_WIFI_SSID ""
#endif

#ifndef AGENT_LAMP_WIFI_PASSWORD
#define AGENT_LAMP_WIFI_PASSWORD ""
#endif

#ifndef AGENT_LAMP_HOSTNAME
#define AGENT_LAMP_HOSTNAME "agent-lamp"
#endif

#ifndef AGENT_LAMP_WIFI_CONNECT_TIMEOUT_MS
#define AGENT_LAMP_WIFI_CONNECT_TIMEOUT_MS 15000
#endif

struct LampViewState {
  String state = "idle";
  String agent = "agent";
  String repo = "workspace";
  String message = "Ready";
  unsigned long updatedAtMs = 0;
};

LampViewState current;
String serialBuffer;
WebServer server(80);
bool httpServerStarted = false;

String clipText(String value, size_t maxLen) {
  value.trim();
  if (value.length() <= maxLen) {
    return value;
  }
  return value.substring(0, maxLen - 3) + "...";
}

String labelForState(const String& state) {
  if (state == "running") return "RUNNING";
  if (state == "waiting") return "NEEDS INPUT";
  if (state == "ok") return "OK";
  if (state == "error") return "ERROR";
  if (state == "idle") return "IDLE";
  return "UNKNOWN";
}

String shortLabelForState(const String& state) {
  if (state == "running") return "RUN";
  if (state == "waiting") return "WAIT";
  if (state == "ok") return "OK";
  if (state == "error") return "ERR";
  if (state == "idle") return "IDLE";
  return "UNK";
}

String subtitleForState(const String& state) {
  if (state == "running") return "Codex is working on the current turn";
  if (state == "waiting") return "Waiting for a real user decision";
  if (state == "ok") return "The last turn finished cleanly";
  if (state == "error") return "The last tool or turn reported a failure";
  return "Ready for the next prompt";
}

uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return M5.Display.color565(r, g, b);
}

uint16_t accentForState(const String& state) {
  if (state == "running") return rgb(251, 191, 36);
  if (state == "waiting") return rgb(96, 165, 250);
  if (state == "ok") return rgb(52, 211, 153);
  if (state == "error") return rgb(248, 113, 113);
  if (state == "idle") return rgb(148, 163, 184);
  return rgb(203, 213, 225);
}

uint16_t textOnAccentForState(const String& state) {
  if (state == "running" || state == "ok" || state == "idle") {
    return rgb(9, 13, 21);
  }
  return M5.Display.color565(255, 255, 255);
}

bool isValidState(const String& state) {
  return state == "idle" || state == "running" || state == "waiting" ||
         state == "ok" || state == "error";
}

String defaultMessageForState(const String& state) {
  if (state == "running") return "Agent is working";
  if (state == "waiting") return "Needs your input";
  if (state == "ok") return "Last run completed";
  if (state == "error") return "Last run failed";
  return "Ready";
}

String statusProtocolLine() {
  return "set\t" + current.state + "\t" + current.agent + "\t" + current.repo +
         "\t" + current.message;
}

String transportStatusLine() {
  if (WiFi.status() == WL_CONNECTED) {
    return "Wi-Fi " + WiFi.localIP().toString() + "  /set";
  }
  if (String(AGENT_LAMP_WIFI_SSID).length() == 0) {
    return "Wi-Fi: add agent_lamp_secrets.h";
  }
  return "Wi-Fi offline; USB fallback";
}

void drawText(String value, int x, int y, int size, uint16_t fg, uint16_t bg) {
  M5.Display.setTextColor(fg, bg);
  M5.Display.setTextSize(size);
  M5.Display.setCursor(x, y);
  M5.Display.print(value);
}

void drawCenteredText(String value, int centerX, int y, int size, uint16_t fg,
                      uint16_t bg) {
  M5.Display.setTextColor(fg, bg);
  M5.Display.setTextSize(size);
  int x = centerX - M5.Display.textWidth(value) / 2;
  if (x < 0) x = 0;
  M5.Display.setCursor(x, y);
  M5.Display.print(value);
}

void drawInfoCard(String title, String value, int x, int y, int width,
                  int height, uint16_t panel, uint16_t text,
                  uint16_t muted) {
  M5.Display.fillRoundRect(x, y, width, height, 18, panel);
  drawText(title, x + 24, y + 24, 2, muted, panel);
  drawText(clipText(value, 18), x + 24, y + 66, 3, text, panel);
}

void drawScreen() {
  const uint16_t bg = rgb(9, 13, 21);
  const uint16_t panel = rgb(18, 24, 38);
  const uint16_t panelHigh = rgb(25, 34, 52);
  const uint16_t line = rgb(54, 65, 88);
  const uint16_t text = rgb(241, 245, 249);
  const uint16_t muted = rgb(148, 163, 184);
  const uint16_t accent = accentForState(current.state);
  const uint16_t accentText = textOnAccentForState(current.state);
  const int w = M5.Display.width();
  const int h = M5.Display.height();
  const int margin = w < 640 ? 24 : 36;
  const int cardW = w - margin * 2;

  M5.Display.fillScreen(bg);
  M5.Display.fillRect(0, 0, w, 14, accent);

  M5.Display.fillRoundRect(margin, 36, cardW, 108, 22, panel);
  M5.Display.fillCircle(margin + 42, 90, 20, accent);
  drawText("Agent Lamp", margin + 78, 58, 3, text, panel);
  drawText(clipText(current.agent + " / " + current.repo, 33), margin + 78,
           98, 2, muted, panel);
  M5.Display.fillRoundRect(w - margin - 138, 64, 106, 42, 20, accent);
  drawCenteredText(shortLabelForState(current.state), w - margin - 85, 76, 2,
                   accentText, accent);

  const int heroY = 182;
  const int heroH = h > 1000 ? 382 : 320;
  M5.Display.fillRoundRect(margin, heroY, cardW, heroH, 30, panelHigh);
  M5.Display.fillRoundRect(margin, heroY, 12, heroH, 6, accent);
  drawText("CURRENT STATE", margin + 40, heroY + 38, 2, muted, panelHigh);

  String stateLabel = labelForState(current.state);
  int stateSize = stateLabel.length() > 8 ? 5 : (stateLabel.length() <= 2 ? 10 : 7);
  drawCenteredText(stateLabel, w / 2, heroY + 112, stateSize, text, panelHigh);
  drawCenteredText(subtitleForState(current.state), w / 2, heroY + heroH - 112,
                   2, muted, panelHigh);

  const int barGap = 12;
  const int barCount = 5;
  const int barW = (cardW - 80 - (barCount - 1) * barGap) / barCount;
  const int barY = heroY + heroH - 54;
  for (int i = 0; i < barCount; ++i) {
    const int barX = margin + 40 + i * (barW + barGap);
    M5.Display.fillRoundRect(barX, barY, barW, 10, 5, i == 2 ? accent : line);
  }

  const int messageY = heroY + heroH + 30;
  const int messageH = h > 1000 ? 194 : 160;
  M5.Display.fillRoundRect(margin, messageY, cardW, messageH, 24, panel);
  drawText("MESSAGE", margin + 30, messageY + 28, 2, muted, panel);
  drawText(clipText(current.message, 38), margin + 30, messageY + 78, 3, text,
           panel);

  const int metaY = messageY + messageH + 26;
  const int metaGap = 20;
  const int metaW = (cardW - metaGap) / 2;
  drawInfoCard("AGENT", current.agent, margin, metaY, metaW, 132, panelHigh,
               text, muted);
  drawInfoCard("WORKSPACE", current.repo, margin + metaW + metaGap, metaY,
               metaW, 132, panelHigh, text, muted);

  const int bottomY = h - 94;
  M5.Display.drawRoundRect(margin, bottomY, cardW, 52, 18, line);
  M5.Display.fillCircle(margin + 28, bottomY + 26, 8,
                        WiFi.status() == WL_CONNECTED ? accent : line);
  drawText(clipText(transportStatusLine(), 48), margin + 48, bottomY + 17, 2,
           muted, bg);
}

String applyState(String state, String agent, String repo, String message) {
  state.trim();
  state.toLowerCase();

  if (!isValidState(state)) {
    return "error invalid state: " + state;
  }

  agent.trim();
  repo.trim();
  message.trim();

  String nextAgent = agent.length() ? agent : "agent";
  String nextRepo = repo.length() ? repo : "workspace";
  String nextMessage = message.length() ? message : defaultMessageForState(state);
  if (current.state == state && current.agent == nextAgent &&
      current.repo == nextRepo && current.message == nextMessage) {
    return "ok " + current.state;
  }

  current.state = state;
  current.agent = nextAgent;
  current.repo = nextRepo;
  current.message = nextMessage;
  current.updatedAtMs = millis();
  drawScreen();

  return "ok " + current.state;
}

int splitTabs(const String& line, String* out, int maxParts) {
  int partCount = 0;
  int start = 0;
  while (partCount < maxParts) {
    int tab = line.indexOf('\t', start);
    if (tab < 0) {
      out[partCount++] = line.substring(start);
      break;
    }
    out[partCount++] = line.substring(start, tab);
    start = tab + 1;
  }
  return partCount;
}

String handleCommand(String line) {
  line.trim();
  if (!line.length()) {
    return "error empty command";
  }

  if (line == "ping") {
    return "pong";
  }

  String parts[5];
  int count = splitTabs(line, parts, 5);
  if (count >= 2 && parts[0] == "set") {
    return applyState(parts[1], count > 2 ? parts[2] : "",
                      count > 3 ? parts[3] : "", count > 4 ? parts[4] : "");
  }

  if (isValidState(line)) {
    return applyState(line, "", "", "");
  }

  return "error unknown command: " + line;
}

void handleHttpSet() {
  if (!server.hasArg("plain")) {
    server.send(400, "text/plain", "error empty body\n");
    return;
  }

  String response = handleCommand(server.arg("plain"));
  server.send(response.startsWith("error") ? 400 : 200, "text/plain",
              response + "\n");
}

void handleHttpPing() {
  server.send(200, "text/plain", "pong\n");
}

void handleHttpStatus() {
  server.send(200, "text/plain", statusProtocolLine() + "\n");
}

void setupWifi() {
  const String ssid = AGENT_LAMP_WIFI_SSID;
  if (!ssid.length()) {
    Serial.println("agent-lamp wifi not configured");
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(AGENT_LAMP_HOSTNAME);
  WiFi.begin(AGENT_LAMP_WIFI_SSID, AGENT_LAMP_WIFI_PASSWORD);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - startedAt < AGENT_LAMP_WIFI_CONNECT_TIMEOUT_MS) {
    M5.update();
    delay(250);
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("agent-lamp wifi connect failed");
    drawScreen();
    return;
  }

  Serial.print("agent-lamp wifi connected ");
  Serial.println(WiFi.localIP());

  if (MDNS.begin(AGENT_LAMP_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    Serial.print("agent-lamp mdns http://");
    Serial.print(AGENT_LAMP_HOSTNAME);
    Serial.println(".local");
  }
  drawScreen();
}

void setupHttpServer() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  server.on("/set", HTTP_POST, handleHttpSet);
  server.on("/ping", HTTP_GET, handleHttpPing);
  server.on("/status", HTTP_GET, handleHttpStatus);
  server.begin();
  httpServerStarted = true;
  Serial.println("agent-lamp http server ready");
}

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);

  current.updatedAtMs = millis();
  drawScreen();
  setupWifi();
  setupHttpServer();
  Serial.println("agent-lamp ready");
}

void loop() {
  M5.update();
  if (httpServerStarted) {
    server.handleClient();
  }

  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length()) {
        Serial.println(handleCommand(serialBuffer));
        serialBuffer = "";
      }
    } else if (serialBuffer.length() < 512) {
      serialBuffer += c;
    }
  }
}
