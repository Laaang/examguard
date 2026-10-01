# 🛡️ ExamGuard DNS - Nadzor i kontrola digitalnih ispita

ExamGuard DNS je cjeloviti sustav za nadzor i kontrolu mrežnog prometa u učionicama tijekom izvođenja ispita na digitalnoj opremi. Sustav funkcionira na razini **DNS poslužitelja** (sinkhole / filter), sprječavajući studente da pristupe nedozvoljenim stranicama (poput AI alata: ChatGPT, Claude, Gemini, tražilica, foruma) ili omogućuje rad u strogom načinu gdje je dopušten isključivo ispitni portal (npr. Moodle).

---

## 🌟 Glavne značajke

1. **Automatsko mapiranje i imenovanje radnih stanica (Auto-Naming)**:
   - Čim se računalo pojavi na mreži, dodjeljuje mu se privremeni naziv: `Radna stanica #01`, `Radna stanica #02`, itd.
2. **Studentski portal za prijavu i identifikaciju (`/student`)**:
   - Studenti na početku ispita posjete `http://<ip-profesora>:8000/student`.
   - Poslužitelj automatski detektira njihovu IP adresu. Student upisuje svoje **Ime, Prezime** i **JMBAG / Broj indeksa**.
   - Radna stanica se u stvarnom vremenu povezuje s identitetom studenta.
3. **Tri ispitna načina rada**:
   - 🛡️ **Strogi Whitelist (Preporučeno za ispite)**: Blokira sav internet osim eksplicitno odobrenih stranica (npr. `*.moodle.*`, `moodle.carnet.hr`, `carnet.hr`, `*.unizg.hr`).
   - ⛔ **Blacklist način**: Internet je dopušten, ali su blokirani svi poznati AI alati (ChatGPT, Claude, Gemini, DeepSeek), tražilice, društvene mreže i forumi za varanje.
   - 👁️ **Samo nadzor**: Sav promet je dopušten, ali se svaki sumnjivi upit bilježi i prikazuje na ekranu profesora.
4. **Live Dashboard za profesora (`/`)**:
   - WebSocket prijenos svih DNS upita u milisekundi.
   - Vizualni i zvučni alarmi na pokušaje varanja (Web Audio API).
   - Classroom Grid prikaz svih računala u učionici s brojem upita i prekršaja.
5. **Protumjere protiv zaobilaženja**:
   - Blokiranje Firefox DoH-a putem Canary domene (`use-application-dns.net` -> NXDOMAIN).
   - Blokiranje poznatih javnih DoH/DoT poslužitelja.
6. **Izvoz revizijskih izvještaja (CSV)**:
   - Preuzimanje detaljnog popisa svih upita sa stupcima: Vrijeme, Radna stanica, Ime studenta, JMBAG, Domena, Status, Razlog.

---

## 🚀 Brzi početak (Pokretanje)

### 1. Pokretanje putem Dockera (Preporučeno — bez potrebe za instalacijom Pythona!)
Cijeli sustav je kontejneriziran. Dovoljno je pokrenuti:
```bash
# Pokretanje u pozadini:
docker compose up -d

# Zaustavljanje:
docker compose down

# Pregled logova:
docker compose logs -f
```

### 2. Pokretanje bez Dockera (preko Pythona)
```bash
# Pokretanje (testni mod na portu 5053 za DNS, 8000 za Web):
./.venv/bin/python3 run.py --dns-port 5053 --web-port 8000

# Produkcijski mod na portu 53:
sudo ./.venv/bin/python3 run.py --dns-port 53 --web-port 8000
```

---

## 💻 Poveznice sučelja

* **Nadzorna ploča profesora:** [http://localhost:8000](http://localhost:8000)
* **Studentski portal za prijavu:** [http://localhost:8000/student](http://localhost:8000/student)
* **Izvoz logova u CSV:** [http://localhost:8000/api/logs/export](http://localhost:8000/api/logs/export)

---

## 🧪 Simulator učionice (Testiranje)
Za brzu demonstraciju rada sustava bez spajanja stvarnih računala:
```bash
./.venv/bin/python3 scripts/simulate_exam.py
```
Ova skripta simulira 4 studenta koji se prijavljuju preko portala te šalju dozvoljene (Moodle) i zabranjene (ChatGPT, Claude, Google) upite. Otvorite nadzornu ploču u pregledniku i promatrajte događaje uživo!

---

## ⚙️ Postavljanje u učionici

1. **Računalo profesora:** Pokrene `ExamGuard DNS` (npr. na IP adresi `192.168.8.112`).
2. **Učenička računala:**
   - **Opcija A (Preporučeno - putem routera):** U postavkama školskog routera / Wi-Fi DHCP-a postavi se primarni DNS na IP profesora (`192.168.8.112`). Sva računala automatski koriste ExamGuard bez ikakvog diranja postavki na njima!
   - **Opcija B (Pojedinačno računalo):** U mrežnim postavkama mrežne kartice postavi se DNS na `192.168.8.112`.
