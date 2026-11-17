/*
 * ============================================================================
 *  CitizenTech – Módulo IoT "Monitor de Pavimento"
 * ============================================================================
 *  ESP32 instalado em um veículo de serviço (ou maquete) que monitora a via:
 *
 *   - VL53L0X (ToF, I2C) ...... aponta para o solo; mede a distância e estima a
 *                               PROFUNDIDADE de buracos/irregularidades em
 *                               relação a uma altura de referência calibrada.
 *   - DHT22 ................... temperatura e umidade. Umidade alta indica pista
 *                               molhada/chuva: a infiltração de água acelera a
 *                               formação de buracos e aumenta o risco.
 *   - Trecho da via ........... GPS SIMULADO: o servidor informa o trecho
 *                               atual por comando MQTT (iot/definir_trecho.py).
 *   - Botão ................... reporte manual do motorista/agente ("passei
 *                               num buraco aqui").
 *   - LEDs .................... ação local: verde = ok, amarelo = atenção,
 *                               vermelho = buraco grave / trecho crítico.
 *
 *  Fluxo:  sensores -> ESP32 -> MQTT -> receptor (banco) -> Agente GenAI
 *  O ESP32 também ASSINA um tópico de comando, para receber alertas do
 *  back-end (ex.: "trecho crítico à frente") e o comando de recalibração.
 *
 *  Bibliotecas (Arduino IDE > Gerenciar Bibliotecas):
 *   - PubSubClient (Nick O'Leary)
 *   - VL53L0X (Pololu)
 *   - DHT sensor library (Adafruit) + Adafruit Unified Sensor
 * ============================================================================
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <VL53L0X.h>
#include <DHT.h>
#include <time.h>

// ======================= CONFIGURAÇÃO (edite aqui) ==========================
const char* WIFI_SSID    = "SUA_REDE";
const char* WIFI_SENHA   = "SUA_SENHA";
const char* MQTT_HOST    = "broker.hivemq.com";      // broker público de testes
const uint16_t MQTT_PORTA = 1883;
const char* TOPICO_BASE  = "fiap/citizentech/grupoX"; // MESMO valor do config.py
const char* DEVICE_ID    = "esp32-01";
const char* TRECHO_INICIAL = "SIM0001";               // trecho ao ligar

// ---- Pinos ----
#define PIN_DHT           4
#define PIN_BOTAO         13   // botão entre o pino e o GND (pull-up interno)
#define PIN_LED_VERDE     25
#define PIN_LED_AMARELO   26
#define PIN_LED_VERMELHO  33
// I2C (VL53L0X): SDA = 21, SCL = 22

// ---- Limiares (escala da maquete, em milímetros) ----
const int   LIMIAR_LEVE_MM    = 15;   // a partir daqui: irregularidade leve
const int   LIMIAR_GRAVE_MM   = 40;   // a partir daqui: buraco grave
const int   HISTERESE_MM      = 5;    // evita "piscar" na borda do limiar
const int   MIN_AMOSTRAS      = 2;    // leituras seguidas acima do limiar
const float UMIDADE_ALTA      = 85.0; // % – pista possivelmente molhada

const unsigned long INTERVALO_VL_MS      = 50;    // leitura do ToF (~20 Hz)
const unsigned long INTERVALO_LEITURA_MS = 5000;  // telemetria periódica
// ============================================================================

VL53L0X vl;
DHT dht(PIN_DHT, DHT22);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

char topicoLeitura[96], topicoEvento[96], topicoComando[96], topicoStatus[96];

bool  vlOk = false;
int   baselineMm = 0;          // altura do sensor até o solo plano
int   distanciaMm = -1;
int   profundidadeMm = 0;
float temperatura = NAN, umidade = NAN;
char  trechoAtual[24] = "";    // código do trecho atual (GPS simulado)

// Máquina de estados da detecção
bool  emIrregularidade = false;
int   amostrasAcima = 0;
int   profMaxMm = 0;
unsigned long ultimoEventoMs = 0;
char  ultimaSeveridade[8] = "ok";

unsigned long ultimoVlMs = 0, ultimaLeituraMs = 0, ultimaTentativaMqtt = 0;
unsigned long confirmacaoAteMs = 0, alertaRemotoAteMs = 0;
bool  botaoAnterior = HIGH;
unsigned long botaoMudouMs = 0;

// ----------------------------- utilitários ---------------------------------
void fmtFloat(char* out, size_t n, float v) {
  if (isnan(v)) snprintf(out, n, "null"); else snprintf(out, n, "%.1f", v);
}

void fmtTrecho(char* out, size_t n) {
  if (trechoAtual[0]) snprintf(out, n, "\"%s\"", trechoAtual);
  else snprintf(out, n, "null");
}

unsigned long agoraEpoch() {           // 0 se o NTP ainda não sincronizou
  time_t t = time(nullptr);
  return t > 1700000000 ? (unsigned long)t : 0;
}

void confirmar(unsigned long ms) {     // acende os 3 LEDs por um instante
  confirmacaoAteMs = millis() + ms;    // (confirma troca de trecho / botão)
}

bool pistaUmida() { return !isnan(umidade) && umidade >= UMIDADE_ALTA; }

const char* statusAtual() {
  if (ultimoEventoMs > 0 && millis() - ultimoEventoMs < 3000) return ultimaSeveridade;
  if (emIrregularidade) return profMaxMm >= LIMIAR_GRAVE_MM ? "grave" : "leve";
  return "ok";
}

// ----------------------------- publicação MQTT -----------------------------
void publicarEvento(const char* tipo, const char* severidade, int prof) {
  char t[12], u[12], tr[30], json[320];
  fmtFloat(t, sizeof t, temperatura);
  fmtFloat(u, sizeof u, umidade);
  fmtTrecho(tr, sizeof tr);
  snprintf(json, sizeof json,
    "{\"device\":\"%s\",\"tipo\":\"%s\",\"severidade\":\"%s\",\"trecho\":%s,"
    "\"prof_mm\":%d,\"temp_c\":%s,\"umid\":%s,\"ts\":%lu}",
    DEVICE_ID, tipo, severidade, tr, prof, t, u, agoraEpoch());
  bool ok = mqtt.connected() && mqtt.publish(topicoEvento, json);
  Serial.printf("[EVENTO%s] %s\n", ok ? "" : " NAO ENVIADO", json);
}

void publicarLeitura() {
  char t[12], u[12], tr[30], json[320];
  fmtFloat(t, sizeof t, temperatura);
  fmtFloat(u, sizeof u, umidade);
  fmtTrecho(tr, sizeof tr);
  snprintf(json, sizeof json,
    "{\"device\":\"%s\",\"trecho\":%s,\"dist_mm\":%d,\"prof_mm\":%d,"
    "\"temp_c\":%s,\"umid\":%s,\"pista_umida\":%s,\"status\":\"%s\",\"ts\":%lu}",
    DEVICE_ID, tr, distanciaMm, profundidadeMm, t, u,
    pistaUmida() ? "true" : "false", statusAtual(), agoraEpoch());
  bool ok = mqtt.connected() && mqtt.publish(topicoLeitura, json);
  Serial.printf("[LEITURA%s] %s\n", ok ? "" : " NAO ENVIADA", json);
}

// ----------------------------- sensores ------------------------------------
void calibrar() {
  if (!vlOk) return;
  Serial.println("Calibrando: mantenha o sensor sobre superficie PLANA...");
  long soma = 0; int n = 0;
  for (int i = 0; i < 30; i++) {
    uint16_t d = vl.readRangeSingleMillimeters();
    if (!vl.timeoutOccurred() && d > 0 && d < 2000) { soma += d; n++; }
    delay(20);
  }
  if (n >= 10) {
    baselineMm = soma / n;
    Serial.printf("Altura de referencia: %d mm\n", baselineMm);
    publicarEvento("calibracao", "info", baselineMm);
  } else {
    Serial.println("Calibracao falhou (leituras invalidas).");
  }
}

void processarProfundidade(int prof) {
  if (!emIrregularidade) {
    if (prof >= LIMIAR_LEVE_MM) {
      amostrasAcima++;
      profMaxMm = max(profMaxMm, prof);
      if (amostrasAcima >= MIN_AMOSTRAS) emIrregularidade = true;
    } else {
      amostrasAcima = 0;
      profMaxMm = 0;
    }
    return;
  }
  // Dentro de uma irregularidade: acompanha a profundidade máxima e,
  // quando o sensor volta ao nível normal, emite UM evento por passagem.
  profMaxMm = max(profMaxMm, prof);
  if (prof < LIMIAR_LEVE_MM - HISTERESE_MM) {
    const char* sev = profMaxMm >= LIMIAR_GRAVE_MM ? "grave" : "leve";
    strncpy(ultimaSeveridade, sev, sizeof ultimaSeveridade);
    ultimoEventoMs = millis();
    publicarEvento("buraco", sev, profMaxMm);
    emIrregularidade = false;
    amostrasAcima = 0;
    profMaxMm = 0;
  }
}

void lerDistancia() {
  uint16_t d = vl.readRangeSingleMillimeters();
  if (vl.timeoutOccurred() || d == 0 || d >= 2000) return;  // fora de alcance
  distanciaMm = d;
  profundidadeMm = max(0, (int)d - baselineMm);   // ressaltos (lombadas) = 0
  processarProfundidade(profundidadeMm);
}

void lerDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) temperatura = t;   // mantém o último valor válido
  if (!isnan(h)) umidade = h;
}

// GPS simulado: o trecho atual chega por comando MQTT
void definirTrecho(const char* codigo, bool avisar) {
  if (!codigo[0] || strcmp(codigo, trechoAtual) == 0) return;
  strncpy(trechoAtual, codigo, sizeof trechoAtual - 1);
  trechoAtual[sizeof trechoAtual - 1] = '\0';
  Serial.printf("Trecho atual: %s\n", trechoAtual);
  if (avisar) {
    confirmar(300);
    publicarEvento("mudanca_trecho", "info", 0);
  }
}

void lerBotao() {
  bool leitura = digitalRead(PIN_BOTAO);
  if (leitura != botaoAnterior && millis() - botaoMudouMs > 50) {   // debounce
    botaoMudouMs = millis();
    botaoAnterior = leitura;
    if (leitura == LOW) {
      confirmar(300);
      publicarEvento("reporte_manual", "info", profundidadeMm);
    }
  }
}

void atualizarLeds() {
  if (millis() < confirmacaoAteMs) {    // confirmação: todos acesos
    digitalWrite(PIN_LED_VERMELHO, HIGH);
    digitalWrite(PIN_LED_AMARELO, HIGH);
    digitalWrite(PIN_LED_VERDE, HIGH);
    return;
  }
  const char* s = statusAtual();
  bool remoto = millis() < alertaRemotoAteMs;
  bool vermelho = strcmp(s, "grave") == 0 || (remoto && (millis() / 250) % 2 == 0);
  bool amarelo = !vermelho && !remoto && (strcmp(s, "leve") == 0 || pistaUmida());
  bool verde = !vermelho && !amarelo && !remoto;
  digitalWrite(PIN_LED_VERMELHO, vermelho);
  digitalWrite(PIN_LED_AMARELO, amarelo);
  digitalWrite(PIN_LED_VERDE, verde);
}

// ----------------------------- MQTT ----------------------------------------
// Extrai o valor texto de "chave" num JSON simples: {"chave": "valor", ...}
bool extrairCampo(const char* json, const char* chave, char* out, size_t n) {
  char padrao[24];
  snprintf(padrao, sizeof padrao, "\"%s\"", chave);
  const char* p = strstr(json, padrao);
  if (!p) return false;
  p = strchr(p + strlen(padrao), ':');
  if (!p) return false;
  p = strchr(p, '"');
  if (!p) return false;
  p++;
  size_t i = 0;
  while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
  out[i] = '\0';
  return i > 0;
}

void aoReceberComando(char* topic, byte* payload, unsigned int len) {
  char msg[200], acao[16], valor[24];
  if (len >= sizeof msg) len = sizeof msg - 1;
  memcpy(msg, payload, len);
  msg[len] = '\0';
  Serial.printf("[COMANDO] %s\n", msg);
  if (!extrairCampo(msg, "acao", acao, sizeof acao)) return;

  if (strcmp(acao, "trecho") == 0) {             // {"acao":"trecho","codigo":"SIM0002"}
    if (extrairCampo(msg, "codigo", valor, sizeof valor)) definirTrecho(valor, true);
  } else if (strcmp(acao, "calibrar") == 0) {
    calibrar();
  } else if (strcmp(acao, "alerta") == 0) {      // ex.: trecho crítico à frente
    alertaRemotoAteMs = millis() + 5000;
    publicarEvento("alerta_recebido", "info", 0);
  } else if (strcmp(acao, "ping") == 0) {
    publicarEvento("online", "info", 0);
  }
}

void conectarMqtt() {
  if (mqtt.connected() || WiFi.status() != WL_CONNECTED) return;
  if (millis() - ultimaTentativaMqtt < 3000) return;
  ultimaTentativaMqtt = millis();
  char id[40];
  snprintf(id, sizeof id, "%s-%04X", DEVICE_ID, (unsigned)(esp_random() & 0xFFFF));
  // Last Will: se o ESP32 cair, o broker publica "offline" no tópico de status
  if (mqtt.connect(id, topicoStatus, 1, true, "offline")) {
    mqtt.publish(topicoStatus, "online", true);
    mqtt.subscribe(topicoComando);
    Serial.println("MQTT conectado.");
  } else {
    Serial.printf("MQTT falhou (rc=%d), tentando de novo...\n", mqtt.state());
  }
}

// ----------------------------- setup / loop --------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOTAO, INPUT_PULLUP);
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_AMARELO, OUTPUT);
  pinMode(PIN_LED_VERMELHO, OUTPUT);
  digitalWrite(PIN_LED_AMARELO, HIGH);   // amarelo fixo = inicializando

  Wire.begin(21, 22);
  vl.setTimeout(500);
  vlOk = vl.init();
  if (!vlOk) Serial.println("ERRO: VL53L0X nao encontrado (verifique SDA/SCL).");

  dht.begin();
  definirTrecho(TRECHO_INICIAL, false);

  snprintf(topicoLeitura, sizeof topicoLeitura, "%s/%s/leitura", TOPICO_BASE, DEVICE_ID);
  snprintf(topicoEvento,  sizeof topicoEvento,  "%s/%s/evento",  TOPICO_BASE, DEVICE_ID);
  snprintf(topicoComando, sizeof topicoComando, "%s/%s/comando", TOPICO_BASE, DEVICE_ID);
  snprintf(topicoStatus,  sizeof topicoStatus,  "%s/%s/status",  TOPICO_BASE, DEVICE_ID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  Serial.print("Conectando ao Wi-Fi");
  for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) { delay(500); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED ? " ok" : " FALHOU (seguindo offline)");

  configTime(-3 * 3600, 0, "pool.ntp.org", "time.google.com");   // horário de Brasília

  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoReceberComando);
  mqtt.setBufferSize(512);              // o padrão (256 B) é pequeno para o JSON
  for (int i = 0; i < 5 && !mqtt.connected(); i++) {
    ultimaTentativaMqtt = 0;
    conectarMqtt();
    if (!mqtt.connected()) delay(1000);
  }

  calibrar();
  lerDht();
  digitalWrite(PIN_LED_AMARELO, LOW);
}

void loop() {
  conectarMqtt();
  mqtt.loop();

  unsigned long agora = millis();
  if (vlOk && baselineMm > 0 && agora - ultimoVlMs >= INTERVALO_VL_MS) {
    ultimoVlMs = agora;
    lerDistancia();
  }
  lerBotao();

  if (agora - ultimaLeituraMs >= INTERVALO_LEITURA_MS) {
    ultimaLeituraMs = agora;
    lerDht();
    publicarLeitura();
  }

  atualizarLeds();
}
