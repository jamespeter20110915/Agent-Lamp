#include <Arduino.h>
#include <M5Unified.h>

struct LampViewState {
  String state = "idle";
  String agent = "agent";
  String repo = "workspace";
  String message = "Ready";
  unsigned long updatedAtMs = 0;
};

LampViewState current;
String serialBuffer;

String clipText(String value, size_t maxLen) {
  value.trim();
  if (value.length() <= maxLen) {
    return value;
  }
  return value.substring(0, maxLen - 3) + "...";
}

String labelForState(const String& state) {
  if (state == "running") return "RUNNING";
  if (state == "waiting") return "WAITING";
  if (state == "ok") return "OK";
  if (state == "error") return "ERROR";
  if (state == "idle") return "IDLE";
  return "UNKNOWN";
}

uint16_t backgroundForState(const String& state) {
  if (state == "running") return M5.Display.color565(245, 185, 40);
  if (state == "waiting") return M5.Display.color565(255, 205, 70);
  if (state == "ok") return M5.Display.color565(24, 140, 82);
  if (state == "error") return M5.Display.color565(190, 40, 44);
  if (state == "idle") return M5.Display.color565(28, 110, 76);
  return M5.Display.color565(45, 48, 54);
}

uint16_t textForState(const String& state) {
  if (state == "running" || state == "waiting") {
    return M5.Display.color565(26, 22, 12);
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

void drawScreen() {
  const uint16_t bg = backgroundForState(current.state);
  const uint16_t fg = textForState(current.state);
  const int w = M5.Display.width();
  const int h = M5.Display.height();

  M5.Display.fillScreen(bg);
  M5.Display.drawRoundRect(28, 28, w - 56, h - 56, 28, fg);

  M5.Display.setTextColor(fg, bg);
  M5.Display.setTextSize(3);
  M5.Display.setCursor(64, 72);
  M5.Display.print("Agent Lamp");

  M5.Display.setTextSize(9);
  M5.Display.setCursor(64, 165);
  M5.Display.print(labelForState(current.state));

  M5.Display.setTextSize(3);
  M5.Display.setCursor(70, 360);
  M5.Display.print("Agent: ");
  M5.Display.print(clipText(current.agent, 24));

  M5.Display.setCursor(70, 420);
  M5.Display.print("Repo:   ");
  M5.Display.print(clipText(current.repo, 24));

  M5.Display.setCursor(70, 500);
  M5.Display.print(clipText(current.message, 46));

  M5.Display.setTextSize(2);
  M5.Display.setCursor(70, h - 90);
  M5.Display.print("USB serial: set <state> <agent> <repo> <message>");
}

void applyState(String state, String agent, String repo, String message) {
  state.trim();
  state.toLowerCase();

  if (!isValidState(state)) {
    Serial.print("error invalid state: ");
    Serial.println(state);
    return;
  }

  agent.trim();
  repo.trim();
  message.trim();

  current.state = state;
  current.agent = agent.length() ? agent : "agent";
  current.repo = repo.length() ? repo : "workspace";
  current.message = message.length() ? message : defaultMessageForState(state);
  current.updatedAtMs = millis();
  drawScreen();

  Serial.print("ok ");
  Serial.println(current.state);
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

void handleLine(String line) {
  line.trim();
  if (!line.length()) {
    return;
  }

  if (line == "ping") {
    Serial.println("pong");
    return;
  }

  String parts[5];
  int count = splitTabs(line, parts, 5);
  if (count >= 2 && parts[0] == "set") {
    applyState(parts[1], count > 2 ? parts[2] : "", count > 3 ? parts[3] : "",
               count > 4 ? parts[4] : "");
    return;
  }

  if (isValidState(line)) {
    applyState(line, "", "", "");
    return;
  }

  Serial.print("error unknown command: ");
  Serial.println(line);
}

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);

  current.updatedAtMs = millis();
  drawScreen();
  Serial.println("agent-lamp ready");
}

void loop() {
  M5.update();

  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length()) {
        handleLine(serialBuffer);
        serialBuffer = "";
      }
    } else if (serialBuffer.length() < 512) {
      serialBuffer += c;
    }
  }
}
