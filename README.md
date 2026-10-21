# Nettverk 2 – Automatisert oppsett med Python og Ansible

Automatisert konfigurasjon av eit Cisco-rack med VLAN, router-on-a-stick, HSRP, OSPF, DHCP og EtherChannel mellom to studentrack (STUD1 og STUD2).
Oppgåva var løyst individuelt men samarbeid mellom STUD1 og STUD2 for samspel for VLAN, namnestandard og samsvarande IP-seriar har resultert i eit meir oversiktleg oppsett.

| Del | Verktøy | Gjer |
|---|---|---|
| 1 | Python (`pyserial`) over konsoll | Hostname, brukar, SSH, management-VLAN og IP |
| 2 | Ansible (`cisco.ios`) over SSH | VLAN, trunkar, subinterfaces, HSRP, OSPF, DHCP og EtherChannel |

## Innhald

- [Oppgåva](#oppgåva)
- [Designval og gjenbruk](#designval-og-gjenbruk)
- [Topologi](#topologi)
- [IP-plan](#ip-plan)
- [Installasjon](#installasjon)
- [Del 1: Python](#del-1-python)
- [Del 2: Ansible](#del-2-ansible)
- [Tilpassing til eige rack](#tilpassing-til-eige-rack)
- [Testing](#testing)
- [Feilsøking](#feilsøking)
- [Prosjektstruktur](#prosjektstruktur)

---

## Oppgåva

Arbeidskrav 2 i NK2: to metodar for å automatisere oppsett av Cisco-utstyr.

| Krav | Løyst i |
|---|---|
| Python-skript med `pyserial` som set opp SSH på svitsj og rutar | `scripts/cisco_setup.py` |
| Gjenbrukbare skript: brukarnamn, passord osv. som input, ikkje hardkoda | Interaktive spørsmål i skriptet |
| README for tilkopling til einingane | [Del 1](#del-1-python) |
| Ansible-collection som passar OS-et | `cisco.ios` (IOS og IOS-XE) |
| Oppsettet frå skissa, avtalt med den som deler rack | [IP-plan](#ip-plan) |
| Gjenbrukbare playbooks som er lette å utvide og vedlikehalde | [Designval og gjenbruk](#designval-og-gjenbruk) |
| Det Ansible ikkje kan, løyst med Python | [Python og Ansible saman](#python-og-ansible-saman) |
| DHCP på rutarane for kvart VLAN | `05_dhcp.yml` |
| Variabelfiler (som i Terraform) | `group_vars/`, `host_vars/` |

---

## Designval og gjenbruk

| Prinsipp | Korleis |
|---|---|
| **Ingen hardkoda verdiar i playbooks** | IP-ar, VLAN-ID-ar og portnamn ligg i vars-filer |
| **Felles plan i éi fil** | `group_vars/all.yml` har alt som må vere likt for begge rack |
| **Einingsverdiar per eining** | `host_vars/<eining>.yml` har loopback, interfaces, IP-ar, HSRP-prioritet og DHCP-område |
| **Same playbooks for begge rack** | STUD2 endrar berre inventory og `host_vars` |
| **Idempotens** | `ios_vlans` og `ios_interfaces` les faktisk tilstand, så ei ny køyring endrar berre det som manglar |
| **Modulært** | Éin playbook per oppgåve, `site.yml` køyrer alle |
| **Éin kommando for avhengigheiter** | `requirements.txt` og `requirements.yml` |

Nettverksval:

- **Management er skilt frå klient-VLAN og VLAN 1**, og blir ikkje sendt over EtherChannel.
- **Native VLAN 999 (ubrukt)** på alle trunkar, mot VLAN-hopping.
- **HSRP** gir redundant gateway, med fire rutarar i same gruppe på tvers av racka.
- **DHCP med split scope:** alle rutarane har pool, men deler ut kvar sin del av subnettet.
- **OSPF** annonserer nett automatisk. Naboskap blir berre danna på uplinken, så racka held rutingdomena sine åtskilde.

---

## Topologi

| Rolle | Eining | Hostname (STUD1) |
|---|---|---|
| Core / L3, OSPF | Catalyst 9300L | S1-ML1 |
| Rutar A (HSRP aktiv) | ISR 4221 | S1-R1 |
| Rutar B (HSRP standby) | ISR 2901 | S1-R2 |
| Distribusjon | Catalyst 2960-24TT | S1-SW1 |
| Aksess, klientar og Po1 | Catalyst 1000 | S1-SW2 |

STUD2 har same oppsett med prefiks `S2-`.

```
            MGMT PC
               │ Gi1/0/3
          ┌─ 9300L ─┐
  Gi1/0/1 │         │ Gi1/0/2
  Gi0/0/0 │         │ Gi0/0
        4221       2901
  Gi0/0/1 │         │ Gi0/1
    Gi0/1 │         │ Gi0/2
          └─ 2960 ──┘
               │ Fa0/1
               │ Gi1/0/1
             C1000 ════ Gi1/0/4-5 ════ C1000 i det andre racket (Po1, LACP)
     Gi1/0/2 │   │ Gi1/0/3
     VLAN 10       VLAN 20
```

> På 2960-24TT er dei 24 portane `Fa0/1-24` og dei to separate portane `Gi0/1-2`.

---

## IP-plan

### LAN

| LAN | VLAN | STUD1 | STUD2 | Gateway |
|---|---|---|---|---|
| Klientar (felles over Po1) | 10 | 192.168.10.0/24 | 192.168.10.0/24 | 192.168.10.1 (HSRP) |
| Klientar (felles over Po1) | 20 | 192.168.20.0/24 | 192.168.20.0/24 | 192.168.20.1 (HSRP) |
| MGMT topp (9300L, router-uplink, MGMT PC) | 99 | 10.0.11.0/24 | 10.0.21.0/24 | – (OSPF) |
| MGMT botn (switchar) | 99 | 10.0.12.0/24 | 10.0.22.0/24 | 10.0.x2.1 (HSRP) |
| Loopbackar (/32) | – | 10.0.10.0/24 | 10.0.20.0/24 | – |
| Native | 999 | – | – | – |

Rutarane står mellom 9300L og 2960, og VLAN kan ikkje gå gjennom rutar. VLAN 99 blir derfor brukt på begge segmenta, med kvart sitt subnett men same VID.

### Einingar

| Eining | Interface | STUD1 | STUD2 |
|---|---|---|---|
| 9300L | Lo0 / Vlan99 | 10.0.10.1 / 10.0.11.1 | 10.0.20.1 / 10.0.21.1 |
| 4221 (R1) | Lo0 / Gi0/0/0 | 10.0.10.2 / 10.0.11.2 | 10.0.20.2 / 10.0.21.2 |
| 2901 (R2) | Lo0 / Gi0/0 | 10.0.10.3 / 10.0.11.3 | 10.0.20.3 / 10.0.21.3 |
| 2960 (SW1) | Vlan99 | 10.0.12.11 | 10.0.22.11 |
| C1000 (SW2) | Vlan99 | 10.0.12.12 | 10.0.22.12 |
| MGMT PC | NIC | 10.0.11.10 | 10.0.21.10 |

### Subinterfaces, HSRP og DHCP

| Rutar | IP i VLAN 10 / 20 / 99 | HSRP-prioritet (10/20 – 99) | DHCP-område |
|---|---|---|---|
| S1-R1 | .2 / .2 / 10.0.12.2 | 110 – 110 | .50-.100 |
| S1-R2 | .3 / .3 / 10.0.12.3 | 105 – 105 | .101-.150 |
| S2-R1 | .4 / .4 / 10.0.22.2 | 100 – 110 | .151-.200 |
| S2-R2 | .5 / .5 / 10.0.22.3 | 95 – 105 | .201-250 |

- **VIP** er alltid `.1`, og gruppenummeret er likt VLAN-ID-en. Alle grupper har `preempt`.
- **.1–.49** er reservert for VIP, rutarar og faste adresser.
- **DHCP-poolane** har HSRP-VIP-en som `default-router`.

### Avtalt mellom STUD1 og STUD2

Klient-VLAN 10 og 20, native VLAN 999, Po1 med LACP `active` som trunk på Gi1/0/4-5, tillate VLAN 10 og 20, og rutar-IP-ar og DHCP-område som i tabellen over.

---

## Installasjon

Ansible køyrer ikkje på Windows. Bruk Linux eller WSL (Ubuntu), kan installere Ubuntu via Microsoft Store. Python-skriptet kan køyrast på både Windows og Linux.

```bash
git clone https://github.com/eripet15/AK2-Nettverk.git ~/ak2       # i heimemappa, ikkje /mnt/c
cd ~/ak2

python3 -m venv ~/ansible-venv
source ~/ansible-venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
```

`requirements.txt` låser `paramiko<3`, fordi IOS-en på nokre einingar berre støttar SHA-1 key exchange.

**Python-skriptet på Windows:**
```powershell
py -m pip install -r scripts\requirements.txt
```

**MGMT-PC:** `10.0.11.10/24` med gateway `10.0.11.1` (STUD2: `10.0.21.10` / `10.0.21.1`).

---

## Del 1: Python

`scripts/cisco_setup.py` spør etter alle verdiar og set opp:

- hostname, domene, lokal brukar (privilege 15), RSA-nøkkel og SSH v2
- **rutar:** IP på uplink og standardrute
- **L3-svitsj:** `ip routing`, mgmt-VLAN, access-portar og SVI
- **L2-svitsj:** mgmt-VLAN, uplink-trunkar, SVI og default-gateway

### Tilkopling

Kople konsollkabelen til eininga og lukk andre program som brukar porten (PuTTY o.l.). Skriptet brukar 9600 baud, 8N1.

| OS | Port | Køyr |
|---|---|---|
| Windows | `COM3`, `COM4` … (Enhetsbehandling → Porter) | `py .\scripts\cisco_setup.py` |
| Linux | `/dev/ttyS3` (= `COM3`), USB-kabel: `/dev/ttyUSB0` eller `/dev/ttyACM0` | `python3 scripts/cisco_setup.py` |

På Linux treng brukaren tilgang til serieportar: `sudo usermod -aG dialout $USER`, og logg ut og inn etterpå. Køyr `dmesg | tail` etter at kabelen er kopla til for å sjå namnet på porten.

### Eksempel på input for test oppsett (STUD1)

Same brukarnamn, passord og domene på alle einingar. Maske `255.255.255.0`.

| Eining | Type | Hostname | VLAN / Interface | IP | Gateway | Portar |
|---|---|---|---|---|---|---|
| 9300L | Switch → L3 | S1-ML1 | 99 | 10.0.11.1 | *(tom)* | Gi1/0/1, Gi1/0/2, Gi1/0/3 |
| 4221 | Router | S1-R1 | Gi0/0/0 | 10.0.11.2 | 10.0.11.1 | – |
| 2901 | Router | S1-R2 | Gi0/0 | 10.0.11.3 | 10.0.11.1 | – |
| 2960 | Switch → L2 | S1-SW1 | 99 | 10.0.12.11 | 10.0.12.1 | Gi0/1, Gi0/2, Fa0/1 |
| C1000 | Switch → L2 | S1-SW2 | 99 | 10.0.12.12 | 10.0.12.1 | Gi1/0/1 |

STUD2: `S1-` → `S2-`, `10.0.11.x` → `10.0.21.x`, `10.0.12.x` → `10.0.22.x`.

Etterpå svarar 9300L og rutarane på SSH. Switchene blir først nåbare etter `02_routers.yml`.

---

## Del 2: Ansible

| Playbook | Mål | Gjer |
|---|---|---|
| `01_core.yml` | 9300L | VLAN-namn, Loopback0, OSPF |
| `02_routers.yml` | Rutarar | Loopback0, subinterfaces, HSRP, OSPF |
| `03_switches.yml` | Switchar | VLAN, rapid-PVST, trunkar, access-portar |
| `04_etherchannel.yml` | Switchar | Po1 mot det andre racket |
| `05_dhcp.yml` | Rutarar | DHCP-pool per klient-VLAN |
| `06_verify.yml` | Alle | Status for OSPF, HSRP, DHCP, VLAN, trunkar og Po1 |
| `site.yml` | Alle | Køyrer 01–06 i rekkjefølgje |

```bash
ansible-playbook site.yml -k --check --diff   # tørrkøyring
ansible-playbook site.yml -k                  # køyr
```

`-k` spør etter SSH-passordet. Første gong kan det vere lurt å køyre playbookane éin og éin.

- **`02_routers.yml` må køyre før `03_switches.yml`**, fordi switchane først er nåbare når rutarane har subinterface `.99` og HSRP-VIP-en.
- **Po1 kjem først opp når begge studentane har køyrt `04_etherchannel.yml`.**

### Python og Ansible saman

Ansible treng SSH og ein IP for å nå ei eining. Det første oppsettet må derfor gjerast over konsoll, og det er det Python-skriptet gjer. Etter det tek Ansible over. Hostname og IP du skriv inn i skriptet må vere dei same som i `inventory/hosts.yml`.

---

## Tilpassing til eige rack

Playbookane og `group_vars/` skal ikkje endrast. For STUD2 eller eit nytt rack endrar du:

| Fil | Endring |
|---|---|
| `inventory/hosts.yml` | Hostnamn og `ansible_host` |
| `host_vars/*-ML1.yml` | `loopback_ip` |
| `host_vars/*-R1.yml`, `*-R2.yml` | Loopback, subinterface-IP, HSRP-prioritet, `dhcp_range` |
| `host_vars/*-SW1.yml`, `*-SW2.yml` | Berre viss kablinga er annleis |

Døme, `host_vars/S2-R1.yml`:

```yaml
loopback_ip: 10.0.20.2
uplink: GigabitEthernet0/0/0
downlink: GigabitEthernet0/0/1
subinterfaces:
  - { vlan: 10, ip: 192.168.10.4, vip: 192.168.10.1, priority: 100 }
  - { vlan: 20, ip: 192.168.20.4, vip: 192.168.20.1, priority: 100 }
  - { vlan: 99, ip: 10.0.22.2,    vip: 10.0.22.1,    priority: 110 }
dhcp_range: { start: 141, end: 200 }
```

> Klient-subnetta er felles. Endre berre vertsadressene, og bruk aldri `.1` som interface-IP.

**Nytt klient-VLAN:** legg det til i `client_vlans` i `group_vars/all.yml` og i `subinterfaces` på kvar rutar. Trunkar, Po1 og DHCP følgjer automatisk.

---

## Testing

| Test | Kommando / handling | Forventa |
|---|---|---|
| Tilgang | `ansible all -m cisco.ios.ios_command -a "commands='show clock'" -k` | SUCCESS på alle |
| Idempotens | `ansible-playbook site.yml -k` to gonger | `changed=0` andre gong |
| Status | `ansible-playbook 06_verify.yml -k` | OSPF FULL, R1 Active / R2 Standby, `Po1(SU)` |
| DHCP | Klient på DHCP, `ipconfig /renew` | Adresse i .50–.250, gateway .1 |
| Same VLAN over Po1 | Ping mellom klientar i VLAN 10 på kvart rack | Svar |
| Ruting mellom VLAN | Ping frå VLAN 10 til VLAN 20 | Svar |
| Mgmt-isolasjon | Ping frå MGMT PC S1 til 10.0.22.11 | Ingen svar |
| HSRP-failover | `shutdown` på R1 Gi0/0/1 under `ping -t` | R2 tek over, R1 tek tilbake Active etter `no shutdown` |
| EtherChannel | Trekk ut Gi1/0/4 under `ping -t` | Pingen held fram |

---

## Feilsøking

| Feil | Løysing |
|---|---|
| `kex error` / `no acceptable kex algorithm` | Gammal IOS. Set `ansible_network_cli_ssh_type: paramiko` og bruk `paramiko<3` |
| `host key mismatch` | `ssh-keygen -R <ip>` (skjer når Python-skriptet har laga ny RSA-nøkkel) |
| `Access denied` | Manglar `-k`, eller feil `ansible_user` |
| `No route to host` mot switchane | Køyr `02_routers.yml` først, og sjekk IP-ane i inventory |
| `command timeout triggered` | Køyr på nytt. Eldre svitsjar er trege ved første innlogging |
| `YAML parsing failed` | Manglande komma eller mellomrom. `ansible-inventory --list` finn fila |
| HSRP Active/Active, standby `unknown` | Rutarane høyrer ikkje kvarandre. Sjekk kabling og trunkar på 2960 |
| `Po1(SD)` med `(s)` | Ulike innstillingar på dei to sidene |
| Ping svarar annakvar gong | IP-konflikt. `show logging \| include DUP` |

`.gitignore` held `ansible.log` utanfor repoet, sidan loggen kan innehalde passord.

---

## Prosjektstruktur

```
ak2/
├── README.md
├── requirements.txt            Python-pakkar for Ansible
├── requirements.yml            Ansible-collections
├── ansible.cfg                 Inventory, timeout, SSH-nøklar
├── site.yml                    Køyrer 01–06
├── 01_core.yml                 9300L: VLAN, loopback, OSPF
├── 02_routers.yml              Rutarar: subinterfaces, HSRP, OSPF
├── 03_switches.yml             Svitsjar: VLAN, STP, trunkar, access
├── 04_etherchannel.yml         Po1
├── 05_dhcp.yml                 DHCP per klient-VLAN
├── 06_verify.yml               Statusrapport
├── scripts/
│   ├── cisco_setup.py          Bootstrap over konsoll
│   └── requirements.txt        pyserial
├── inventory/hosts.yml         Einingar og IP-ar
├── group_vars/
│   ├── all.yml                 Felles plan og tilkopling
│   └── switches.yml            Paramiko og timeout for svitsjar
└── host_vars/                  Verdiar per eining
```
