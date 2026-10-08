/*
  NRX2 Manchester receiver (Arduino Uno) - with machine-parseable logging

  Same decoder as rx_manchester.ino. The only addition: every completed
  frame (good or bad CRC) also prints a single-line, comma-separated
  "LOG," record meant for a PC-side script to parse automatically:

      LOG,<OK|BAD>,<millis>,<RSSI_mV>,<payload text>

  The payload text itself is whatever ASCII was sent - for the GPS
  beacon that's "<group_id>,<lat>,<lon>,<alt>,<hhmmss>", so a LOG line
  looks like:

      LOG,OK,45231,1862,5,-26.68863,27.09528,1344,022306

  A parser should split on ',' with maxsplit=4: the first four fields
  are fixed (LOG, status, millis, RSSI), and everything after the 4th
  comma is the raw payload text (which may itself contain commas).

  The original human-readable line is kept too, for anyone watching the
  Serial Monitor live.

  Wiring (NRX2 powered from the Uno's 5V):
    NRX2 pin 7  RXD   -> D2   (direct, no resistor)
    NRX2 pin 3  RSSI  -> A0
    NRX2 pin 5  Vcc   -> 5V,  pins 4 and 2 -> GND,  pin 1 -> antenna

  Pair with gps_transmit_v2.py / ntx2_tx*.py --mode manchester.
  BIT_US must match the transmitter's --bit-us (default 4000).
*/

const byte RXD_PIN = 2;                 // INT0
const byte RSSI_PIN = A0;
const unsigned long BIT_US = 4000;      // Manchester bit period (must match the Pi)
const uint16_t SYNC_WORD = 0x2DD4;
const byte MAX_PAYLOAD = 40;

// ---------- edge queue (filled by the interrupt) ----------
const byte QUEUE_SIZE = 64;             // must be a power of two
volatile unsigned long edgeTime[QUEUE_SIZE];
volatile byte edgeLevel[QUEUE_SIZE];
volatile byte qHead = 0;
volatile byte qTail = 0;
volatile unsigned int overflowCount = 0;

void onEdge() {
  byte next = (qHead + 1) & (QUEUE_SIZE - 1);
  if (next == qTail) {
    overflowCount++;
    return;
  }
  edgeTime[qHead] = micros();
  edgeLevel[qHead] = digitalRead(RXD_PIN);   // level AFTER this edge
  qHead = next;
}

// ---------- decoder state ----------
const byte ST_SYNC = 0, ST_LEN = 1, ST_PAYLOAD = 2, ST_CRC = 3;

unsigned long lastEdgeUs = 0;
bool haveLast = false;
bool locked = false;        // true once the preamble has fixed the bit timing
bool atMid = false;         // was the previous edge a mid-bit edge?
byte longCount = 0;
byte state = ST_SYNC;
uint16_t shiftReg = 0;
bool inverted = false;
byte bitCount = 0;
byte curByte = 0;
byte payloadLen = 0;
byte payloadPos = 0;
byte payload[MAX_PAYLOAD + 1];
byte crcCalc = 0;

unsigned long edgesSeen = 0;
unsigned long locks = 0;
unsigned long framesOk = 0;
unsigned long framesBad = 0;

byte crc8Update(byte crc, byte data) {
  crc ^= data;
  for (byte i = 0; i < 8; i++) {
    crc = (crc & 0x80) ? (byte)((crc << 1) ^ 0x07) : (byte)(crc << 1);
  }
  return crc;
}

void resetDecoder() {
  locked = false;
  atMid = false;
  longCount = 0;
  state = ST_SYNC;
  shiftReg = 0;
  bitCount = 0;
  curByte = 0;
}

void printFrame(bool ok) {
  unsigned long nowMs = millis();
  long rssiMv = analogRead(RSSI_PIN) * 5000L / 1023L;

  // Human-readable line (for live viewing in the Serial Monitor)
  Serial.print(nowMs);
  Serial.print(F(" ms  "));
  Serial.print(ok ? F("OK  ") : F("BAD CRC  "));
  Serial.print(F("RSSI="));
  Serial.print(rssiMv);
  Serial.print(F(" mV  ok/bad="));
  Serial.print(framesOk);
  Serial.print('/');
  Serial.print(framesBad);
  Serial.print(F("  | "));
  for (byte i = 0; i < payloadLen; i++) {
    char c = payload[i];
    Serial.print((c >= 32 && c < 127) ? c : '.');
  }
  Serial.println();

  // Machine-parseable line for the companion PC script
  Serial.print(F("LOG,"));
  Serial.print(ok ? F("OK") : F("BAD"));
  Serial.print(',');
  Serial.print(nowMs);
  Serial.print(',');
  Serial.print(rssiMv);
  Serial.print(',');
  for (byte i = 0; i < payloadLen; i++) {
    char c = payload[i];
    Serial.print((c >= 32 && c < 127) ? c : '.');
  }
  Serial.println();
}

void onByte(byte value) {
  if (state == ST_LEN) {
    if (value == 0 || value > MAX_PAYLOAD) { resetDecoder(); return; }
    payloadLen = value;
    payloadPos = 0;
    crcCalc = crc8Update(0, value);
    state = ST_PAYLOAD;
  } else if (state == ST_PAYLOAD) {
    payload[payloadPos++] = value;
    crcCalc = crc8Update(crcCalc, value);
    if (payloadPos >= payloadLen) state = ST_CRC;
  } else if (state == ST_CRC) {
    bool ok = (value == crcCalc);
    if (ok) framesOk++; else framesBad++;
    printFrame(ok);
    resetDecoder();
  }
}

void onBit(byte bit) {
  if (state == ST_SYNC) {
    shiftReg = (shiftReg << 1) | bit;
    bool found = false;
    if (shiftReg == SYNC_WORD) { inverted = false; found = true; }
    else if (shiftReg == (uint16_t)~SYNC_WORD) { inverted = true; found = true; }
    if (found) {
      state = ST_LEN;
      bitCount = 0;
      curByte = 0;
    }
    return;
  }

  if (inverted) bit ^= 1;
  curByte = (curByte << 1) | bit;
  bitCount++;
  if (bitCount == 8) {
    byte value = curByte;
    bitCount = 0;
    curByte = 0;
    onByte(value);
  }
}

void handleEdge(unsigned long t, byte level) {
  if (!haveLast) { lastEdgeUs = t; haveLast = true; return; }
  unsigned long dt = t - lastEdgeUs;
  lastEdgeUs = t;

  byte cls = 0;                                   // 0 = invalid
  if (dt >= BIT_US / 4 && dt < BIT_US * 3 / 4) cls = 1;          // short
  else if (dt >= BIT_US * 3 / 4 && dt < BIT_US * 3 / 2) cls = 2; // long

  if (cls == 0) { resetDecoder(); return; }

  if (!locked) {
    if (cls == 2) {
      if (++longCount >= 6) {
        locked = true;
        atMid = true;
        locks++;
        onBit(level);
      }
    } else {
      longCount = 0;
    }
    return;
  }

  if (atMid) {
    if (cls == 1) {
      atMid = false;
    } else {
      onBit(level);
    }
  } else {
    if (cls == 1) {
      atMid = true;
      onBit(level);
    } else {
      resetDecoder();
    }
  }
}

void setup() {
  pinMode(RXD_PIN, INPUT);
  Serial.begin(115200);
  Serial.println(F("NRX2 MANCHESTER RECEIVER (with LOG, output)"));
  attachInterrupt(digitalPinToInterrupt(RXD_PIN), onEdge, CHANGE);
}

void loop() {
  static unsigned int lastOverflow = 0;
  static unsigned long lastStatusMs = 0;

  while (qTail != qHead) {
    unsigned long t = edgeTime[qTail];
    byte level = edgeLevel[qTail];
    qTail = (qTail + 1) & (QUEUE_SIZE - 1);
    edgesSeen++;
    handleEdge(t, level);
  }

  if (overflowCount != lastOverflow) {
    lastOverflow = overflowCount;
    resetDecoder();
  }

  if ((locked || longCount > 0) && (micros() - lastEdgeUs > BIT_US * 4)) {
    resetDecoder();
  }

  if (millis() - lastStatusMs >= 2000) {
    lastStatusMs = millis();
    Serial.print(F("[status] RSSI="));
    Serial.print(analogRead(RSSI_PIN) * 5000L / 1023L);
    Serial.print(F(" mV  edges="));
    Serial.print(edgesSeen);
    Serial.print(F("  preamble locks="));
    Serial.print(locks);
    Serial.print(F("  frames ok/bad="));
    Serial.print(framesOk);
    Serial.print('/');
    Serial.print(framesBad);
    Serial.println();
  }
}
