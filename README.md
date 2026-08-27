# Hermes Toolbox

Hermes Toolbox ist eine öffentliche Sammlung geprüfter und kuratierter Skills für [Hermes Agent](https://github.com/NousResearch/hermes-agent). Die Sammlung enthält eine einheitliche deutsche/DACH-Edition dokumentbasierter Marketing-, Recherche-, Schreib- und Kreativ-Workflows sowie lokale Anwendungen wie GymPilot.

Die kuratierten Fassungen sind keine unveränderten Upstream-Kopien und keine offiziellen Ausgaben der ursprünglichen Projekte. Sie dokumentieren Ursprung und geprüften Commit, führen den Agenten auf Deutsch und ergänzen konservative Grenzen für Fakten, Datenschutz, Einwilligung, Rechte, Kosten und externe Aktionen. Deutschland ist bei einem deutschen Auftrag ohne anderen Zielmarkt eine gekennzeichnete Arbeitsannahme; Österreich und die Schweiz werden separat behandelt.

- [Kuratierungsrichtlinie](docs/KURATIERUNGSRICHTLINIE.md)
- [Konkrete Änderungen gegenüber Upstream](docs/UPSTREAM-AENDERUNGEN.md)
- [Terminologie und Schreibstandard](docs/TERMINOLOGIE.md)
- [Autoritative Quellen und Prüfeinstiege](docs/QUELLENREGISTER.md)
- [Herkunft und Lizenzen](THIRD_PARTY_NOTICES.md)
- Maschinenlesbare Manifeste: [`skills/catalog.json`](skills/catalog.json) und [`skills/curation.json`](skills/curation.json)

## Skill-Katalog

| Skill | Aufgabe | Sprache | Ausführbarer Code |
|---|---|---:|---:|
| [`ai-seo`](skills/ai-seo/SKILL.md) | Sichtbarkeit in KI-Suchsystemen prüfen und verbessern | DE | nein |
| [`seo-audit`](skills/seo-audit/SKILL.md) | technische und inhaltliche SEO-Prüfung | DE | nein |
| [`product-marketing`](skills/product-marketing/SKILL.md) | belegte Produktmarketing-Grundlage pflegen | DE | nein |
| [`social`](skills/social/SKILL.md) | Social-Media-Inhalte und Planung | DE | nein |
| [`cold-email`](skills/cold-email/SKILL.md) | kontrollierte B2B-Outreach-Entwürfe | DE | nein |
| [`competitors`](skills/competitors/SKILL.md) | sachliche Wettbewerbs- und Vergleichsinhalte | DE | nein |
| [`competitor-profiling`](skills/competitor-profiling/SKILL.md) | quellengebundene Wettbewerberprofile | DE | nein |
| [`content-strategy`](skills/content-strategy/SKILL.md) | evidenzbasierte Content-Strategien | DE | nein |
| [`copywriting`](skills/copywriting/SKILL.md) | sachliche, belegte Website-Texte | DE | nein |
| [`customer-research`](skills/customer-research/SKILL.md) | datensparsame Kundenforschung | DE | nein |
| [`image`](skills/image/SKILL.md) | sichere Planung und Bearbeitung von Bildern | DE | nein |
| [`lead-magnets`](skills/lead-magnets/SKILL.md) | datenschutzbewusste Lead-Magnet-Konzepte | DE | nein |
| [`marketing-ideas`](skills/marketing-ideas/SKILL.md) | Marketinghypothesen und kontrollierte Experimente | DE | nein |
| [`vermenschlichen`](skills/vermenschlichen/SKILL.md) | natürliche deutsche Textredaktion | DE | nein |
| [`zustellbarkeit`](skills/zustellbarkeit/SKILL.md) | E-Mail-Entwürfe und empfangene Nachrichten auf Junk-Auslöser prüfen | DE | ja |
| [`gym`](skills/gym/SKILL.md) | lokaler Trainingstracker GymPilot | DE | ja |

Die Angabe `DE` beschreibt die Sprache der Agentenanweisung. Die Skills antworten grundsätzlich in der Sprache des Nutzers; bei einem deutschen Auftrag verwenden sie natürliches Standarddeutsch und beachten Anrede, Zielmedium und Markenstimme.

## Installation

Einen einzelnen Skill direkt über die GitHub-Pfad-ID installieren:

```bash
hermes skills inspect LOGIN-TB/hermes-toolbox/skills/vermenschlichen
hermes skills install LOGIN-TB/hermes-toolbox/skills/vermenschlichen
```

Alternativ das Repository als Hermes-Tap hinzufügen und darüber suchen. Der Tap macht den Katalog auffindbar; installiert wird weiterhin mit der vollständigen, von der Suche ausgegebenen Pfad-ID:

```bash
hermes skills tap add LOGIN-TB/hermes-toolbox
hermes skills search vermenschlichen --source github
hermes skills install LOGIN-TB/hermes-toolbox/skills/vermenschlichen
```

Für reproduzierbare Installationen empfiehlt sich eine unveränderliche Raw-URL mit Release-Tag oder vollständigem Commit statt `main`:

```bash
hermes skills install \
  https://raw.githubusercontent.com/LOGIN-TB/hermes-toolbox/COMMIT/skills/vermenschlichen/SKILL.md
```

`COMMIT` ist durch den gewünschten vollständigen Commit-Hash zu ersetzen. Die Installation eines Skills autorisiert keine in ihm beschriebenen externen Aktionen. Vor Versand, Veröffentlichung, Tracking, Käufen, bezahlten Diensten, Konto- oder Systemänderungen bleibt eine konkrete Freigabe erforderlich.

Nach der Installation in einem bereits laufenden Hermes-Prozess kann `/reload-skills` nötig sein. Bei GymPilot gelten zusätzlich die unten beschriebenen Aktivierungs- und Servicetests.

## Vertrauensmodell und Aktualisierung

- Jeder Skill wird einzeln installiert und vom Hermes-Sicherheitsscanner geprüft.
- Scannerwarnungen werden nicht mit `--force` umgangen.
- Dokumentbasierte Skills enthalten keinen ausführbaren Code; GymPilot ist die ausdrücklich gekennzeichnete Ausnahme.
- Installierte Dateien sollten nicht lokal verändert werden, wenn spätere Updates nachvollziehbar bleiben sollen.
- `main` ist der aktuelle Entwicklungsstand. Release-Tags oder Commit-URLs sind reproduzierbar.
- Die CI validiert Katalog, Frontmatter, relative Links, Portabilität und isolierte Installationen aller dokumentbasierten Skills sowie die vollständigen GymPilot-Tests.

## GymPilot

GymPilot ist ein lokaler Trainingstracker mit mobiler Weboberfläche und PWA-Dateien. Er wird als Hermes-Skill `/gym` installiert und benötigt außer Python 3.11 oder neuer keine zusätzlichen Pakete.

## Funktionen

- profilsichere SQLite-Daten unter `${HERMES_HOME:-~/.hermes}/gympilot`
- frei benannte Routinen mit festen Wochentagen
- Übungen mit Satzanzahl und Wiederholungsbereich
- laufende Einheiten, Satzkorrekturen und Vergleich mit der letzten Einheit derselben Routine
- Gewichteingabe in kg oder lb; Speicherung einheitlich in kg
- Gerätealiases für bestätigte Gerätefotos und gerätebezogene Satzhistorie
- zwei Setup-Wege: Gesamtplan importieren oder manuell eingeben
- persistenter Gesamtentwurf mit vollständiger Vorschau und genau einer atomaren Gesamtbestätigung
- dauerhaft editierbares Geräte-/Studioprofil
- JSON-Ausgabe für Hermes und lesbare Terminalausgabe
- mobile Oberfläche; als PWA installierbar, wenn der Browser einen sicheren Kontext bereitstellt
- persistenter, profilbezogener Dashboard-Service über `launchd` (macOS) oder `systemd --user` (Linux), unabhängig vom Hermes-Gateway
- persistenter Service standardmäßig an `127.0.0.1:8765`; optional explizit an eine konkrete private LAN-/VPN-Adresse, niemals an Wildcards oder öffentliche IPs
- optionaler Passwortschutz mit gesalzenem Hash, zufälligen Sitzungscookies und begrenzten Loginversuchen

## Voraussetzungen

Erforderlich sind Python 3.11 oder neuer und Hermes Agent. Eine Installation von Python-Paketen ist nicht nötig.

## Skill installieren

Direkt über `SKILL.md` einschließlich der referenzierten Dateien:

```bash
hermes skills install https://raw.githubusercontent.com/LOGIN-TB/hermes-toolbox/main/skills/gym/SKILL.md
```

Installation über einen Hermes-Tap:

```bash
hermes skills tap add LOGIN-TB/hermes-toolbox
hermes skills install LOGIN-TB/hermes-toolbox/gym
```

Alternativ kann die GitHub-Pfad-ID verwendet werden:

```bash
hermes skills install LOGIN-TB/hermes-toolbox/skills/gym
```

Wurde GymPilot aus einem bereits laufenden Telegram-/Gateway-Chat installiert, muss anschließend im Chat **zwingend** `/reload-skills` gesendet werden. Der Gateway-Prozess hält die Liste dynamischer Skill-Befehle im Speicher; eine neue Unterhaltung allein aktualisiert diese Liste nicht. Danach `/commands` öffnen und den echten Einstieg `/gym` manuell aufrufen. Das sichtbare Telegram-Befehlsmenü wird erst beim Gateway-Start registriert: Deshalb danach `/restart` senden und den Menüeintrag separat prüfen. Telegram begrenzt dieses Menü; fehlt `/gym` trotz funktionierendem manuellem Aufruf, sind das Menülimit beziehungsweise weitere lokale Skills mögliche Ursachen. Ebenso müssen ein erfolgreicher Gateway-Neustart und die `set_my_commands`-Meldungen der Telegram-Bot-API in den Gateway-Logs geprüft werden.

Ein Aufruf von `/gym` ohne Unterbefehl ist der stabile Startpunkt. GymPilot liest dafür den lokalen Zustand über `gympilot.py --json home`: Ohne Plan führt er zu `/gym setup`, mit heutiger Routine zeigt er das Training, ohne heutige Routine verweist er auf den Plan, und bei einer laufenden Einheit setzt er diese auch nach einer externen Plandeaktivierung fort. Der erste Aufruf initialisiert bei Bedarf das profilbezogene Datenverzeichnis und die SQLite-Datenbank. Damit ist ein bloßes Reagieren des Sprachmodells auf den Text `/gym` nicht mehr mit einer erfolgreichen Skillregistrierung zu verwechseln.

Beim ersten `/gym`-Aufruf sollte der persistente Dashboard-Service angeboten und nach Zustimmung einmalig installiert werden. Alternativ kann dies im Terminal erfolgen, nachdem der Pfad zur installierten `gympilot.py` ermittelt wurde:

```bash
python3 "/pfad/zum/installierten/gym/scripts/gympilot.py" --json service install
python3 "/pfad/zum/installierten/gym/scripts/gympilot.py" --json service status
```

Für den Zugriff vom iPhone wird GymPilot ausschließlich an eine konkrete private LAN-/VPN-Adresse gebunden und mit HTTPS installiert:

```bash
python3 "/pfad/zum/installierten/gym/scripts/gympilot.py" --json service install --host PRIVATE_IP --https
```

`--https` erzeugt profilintern eine private GymPilot-CA und ein Serverzertifikat mit der konkreten LAN-IP als Subject Alternative Name. Die JSON-Ausgabe nennt:

- `url`: Adresse des Dashboards
- `ca_certificate`: öffentliches CA-Zertifikat für das eigene Telefon
- `webclip_profile_url`: anklickbares Apple-Web-Clip-Profil mit eingebettetem Hantelicon

Nur das öffentliche CA-Zertifikat darf auf das eigene Telefon übertragen werden. Der private CA-Schlüssel bleibt auf dem Rechner und gehört weder in eine Nachricht noch in ein Repository. Safari muss die Dashboard-URL anschließend ohne Zertifikatswarnung laden.

Die lokale Installationsadresse steht in `webclip_profile_url`. Sie hat die Form:

```text
https://PRIVATE_IP:8765/install/GymPilot-WebClip.mobileconfig
```

Diesen Wert aus der eigenen `service install`- oder `service status`-Ausgabe direkt in Safari öffnen.

Nicht Safaris Funktion „Zum Home-Bildschirm“ verwenden. Auf betroffenen Safari-/iOS-Versionen kann sie trotz korrekter PNG-, SVG- und Manifestdateien ein Buchstabenicon erzeugen. Das von GymPilot ausgelieferte Profil enthält das Hantelbild direkt und installiert einen entfernbaren Vollbild-Web-Clip. Es enthält keine Zertifikate, Passwörter, Trainingsdaten, Konten, VPN-Einstellungen oder Geräteeinschränkungen.

Die vollständige Anleitung beschreibt Zertifikatsübertragung, Profilprüfung, ersten Online-Start, Offline-Kaltstart, Aktualisierung, Fehlerbehebung und Rücknahme:

**[GymPilot auf einem iPhone installieren](docs/gympilot-iphone-installation.md)**

`0.0.0.0`, `::`, öffentliche Adressen, Tunnel und Router-Portweiterleitungen werden nicht unterstützt. Ohne `--https` bleibt der LAN-Verkehr unverschlüsselt und der Offline-Kaltstart einer PWA funktioniert dort nicht.

Der Service startet das lokale Dashboard unabhängig vom Gateway. Ein `/restart` des Hermes-Gateways beendet die Weboberfläche deshalb nicht mehr. Ein echter Dashboard-Absturz wird beim nächsten `/gym`-Status erkannt und kontrolliert über `service restart` behoben; der Service erzeugt bewusst keine unbegrenzte Crash-Schleife.

Der persistente Service verwendet standardmäßig `127.0.0.1:8765`. Eine explizit installierte private Adresse wird in der geschützten Servicebeschreibung gespeichert und bei `status`, `restart` sowie einem späteren `service install` automatisch wiederverwendet. Bei wechselnden DHCP-Adressen empfiehlt sich eine Routerreservierung. Wegen des festen Ports kann pro Benutzer immer nur ein GymPilot-Profil gleichzeitig laufen. Unter Linux gehört der Dienst zum `systemd --user`-Manager und läuft ohne interaktive Anmeldung nur weiter, wenn der Administrator für den Benutzer bewusst Linger aktiviert hat.

Auf headless Linux-Systemen prüft GymPilot den User-Manager vor dem Schreiben der Unit und setzt für `systemctl --user` automatisch `XDG_RUNTIME_DIR=/run/user/UID` und `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/UID/bus`. Ist der Manager nicht verfügbar, bricht die Installation ohne Unit-Änderung ab und nennt Benutzer, UID und die erforderlichen Befehle. `loginctl enable-linger BENUTZER` ist eine dauerhafte Systemänderung und darf erst nach ausdrücklicher Zustimmung durch einen Administrator ausgeführt werden; danach ist `systemctl start user@UID.service` erforderlich. Anschließend `service install` wiederholen und `installed: true`, `running: true` sowie `healthy: true` prüfen. Ein manueller Hintergrundprozess ist kein zulässiger Ersatz. Python 3.11 oder neuer genügt; insbesondere ist Python 3.13 vollständig ausreichend.

### Aktualisieren

```bash
hermes skills check
hermes skills update
python3 "/pfad/zum/installierten/gym/scripts/gympilot.py" --json service install
```

`service install` ist nach jedem Skill-Update erforderlich: Es ersetzt die Service-Definition und startet das Dashboard mit dem aktualisierten Skillcode neu. Eine zuvor explizit installierte private Hostadresse bleibt ohne erneute `--host`-Angabe erhalten. Zusätzlich enthält der Health-Contract eine beim Prozessstart fixierte Code-ID, sodass ein alter, noch laufender Prozess nicht als aktuell gesund gilt. Nach einem Update aus einem laufenden Gateway-Chat ebenfalls `/reload-skills` senden; falls der Befehl danach noch nicht verfügbar ist, `/restart` verwenden.

Installierte Dateien nicht von Hand bearbeiten. Eine Aktualisierung ersetzt den Skillcode und seine Webdateien. Profil, Trainingsdaten, Backups und Exporte liegen außerhalb des Skillverzeichnisses und bleiben erhalten.

### Deinstallieren

```bash
python3 "/pfad/zum/installierten/gym/scripts/gympilot.py" --json service uninstall
hermes skills uninstall gym
```

Der Service muss zuerst entfernt werden, damit keine Service-Definition auf eine anschließend gelöschte CLI verweist. `hermes skills uninstall` entfernt den Skill, nicht die persönlichen Daten unter `${HERMES_HOME:-~/.hermes}/gympilot`. Vor einer endgültigen manuellen Löschung dieses Verzeichnisses sollte über `/gym backup` eine Sicherung erstellt werden.

## Direkter Start ohne Hermes

Aus dem geklonten Repository:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
python3 skills/gym/scripts/gympilot.py init
python3 skills/gym/scripts/gympilot.py routine add "Ganzkörper" --weekday 1 --weekday 4
python3 skills/gym/scripts/gympilot.py exercise add 1 "Kniebeuge" --sets 3 --min-reps 5 --max-reps 8
python3 skills/gym/scripts/gympilot.py --json service install
```

Die Web-App läuft anschließend standardmäßig lokal auf `127.0.0.1`, Port `8765`, oder nach einer expliziten privaten Installation unter der von `service status` ausgegebenen LAN-/VPN-Adresse. Für maschinenlesbare Ausgaben steht `--json` direkt vor dem jeweiligen Befehl.

Die Erfassung von Einheiten, Sätzen, Gewichten und Wiederholungen erfolgt ausschließlich über Telegram/Hermes. Die Web-App ist eine reine Auswertungsoberfläche. Nach einem erfolgreichen Abruf speichert sie einen vollständigen, maximal 2 MB großen Auswertungs-Snapshot origin-lokal in IndexedDB, Cache Storage und zusätzlich als `localStorage`-Fallback. Der separate private Cache enthält ausschließlich diesen validierten Gesamtsnapshot; einzelne API-Antworten bleiben `no-store` und werden nie vom Service Worker gecacht. Ohne Serververbindung bleiben Plan, letzte Satzwerte, Verlauf und Kennzahlen mit einem sichtbaren Zeitstempel (`Offline · Stand …`) lesbar. Beim nächsten Online-Abruf wird der Snapshot vollständig ersetzt; es gibt keine Offline-Erfassung und keine Mutationswarteschlange. Bei aktiviertem Dashboard-Passwort werden keine Offline-Auswertungen gespeichert. Passwortschutz, Authentifizierungsfehler und Logout setzen vor dem Löschen eine nicht geheime lokale Sperrepoche. Alle drei Speicher verwenden epochenspezifische Schlüssel, damit ein älterer Safari-/PWA-Kontext einen neu autorisierten Snapshot weder überschreiben noch löschen kann. Ist der persistente Richtlinienspeicher nicht verfügbar, liest die App fail-closed keinen Offline-Snapshot.

Browser behandeln Loopback als sicheren Kontext; dort kann der Service Worker registriert werden. Für ein Telefon im privaten LAN richtet `service install --host PRIVATE_IP --https` einen lokalen HTTPS-Endpunkt ein. Nach einmaligem Vertrauen der ausgegebenen CA kann der Browser den Service Worker registrieren und den App-Rahmen für Offline-Kaltstarts speichern. Ein HTTP-LAN-Endpunkt bleibt nur ein mobiles Web-Dashboard ohne verlässlichen Offline-Kaltstart.

Häufig verwendete Befehle:

```bash
python3 skills/gym/scripts/gympilot.py --json home
python3 skills/gym/scripts/gympilot.py --json status
python3 skills/gym/scripts/gympilot.py --json today
python3 skills/gym/scripts/gympilot.py --json plan
python3 skills/gym/scripts/gympilot.py --json draft capabilities
python3 skills/gym/scripts/gympilot.py --json studio-profile update --equipment barbell --equipment bench
python3 skills/gym/scripts/gympilot.py --json draft show
python3 skills/gym/scripts/gympilot.py --json draft confirm --revision REVISION --content-hash HASH
python3 skills/gym/scripts/gympilot.py --json session start --routine 1
python3 skills/gym/scripts/gympilot.py --json equipment add 1 "Beinpresse Studio A"
python3 skills/gym/scripts/gympilot.py --json set log 1 1 --weight 60 --reps 8 --equipment 1
python3 skills/gym/scripts/gympilot.py --json session finish 1
python3 skills/gym/scripts/gympilot.py --json export
python3 skills/gym/scripts/gympilot.py --json backup
```

## Unterbrechbares `/gym setup` als Gesamtplan

`onboarding status` nennt die zwei Modi `import` und `manual`. Die Auswahl wird mit `onboarding mode MODUS` gespeichert. Ein vorhandener Entwurf bleibt über Prozess- und Chatunterbrechungen hinweg erhalten. `draft show` ist rein lesend und materialisiert niemals einen Plan. GymPilot lässt Hermes aus einer Zielvorgabe keinen Trainingsplan vorschlagen.

### Vollständigen Plan importieren

Ein in Telegram eingefügter Gesamtplan wird von Hermes als Ganzes gelesen und in striktes JSON für `draft import JSON` übertragen. Der Nutzer muss das JSON nicht selbst schreiben. Es enthält `routines`; jede Routine hat `name`, eindeutige ISO-`weekdays` und `exercises`. Jede Übung enthält `name`, `sets`, `min_reps` und `max_reps`. Doppelte JSON-Schlüssel, `NaN`, `Infinity`, doppelte Tage, überschrittene Anzahlgrenzen und ungültige Wiederholungsbereiche werden abgelehnt.

Existiert bereits ein Entwurf, wird er nicht still überschrieben. Ein bewusster vollständiger Ersatz benötigt `--replace-revision REVISION` mit der Revision der letzten Vorschau.

### Gesamtvorschau, Änderung und Bestätigung

`draft show` liefert den persistenten Entwurf nach jeder Unterbrechung zusammen mit einer monotonen `revision` und einem SHA-256-`content_hash` über das kanonische Plan-JSON. Mit `draft routine-update ... --revision REVISION` und `draft exercise-update ... --revision REVISION` lassen sich bestätigte Änderungswünsche strukturiert anwenden. Jede Änderung erhöht die Revision und erzeugt einen neuen Hash; danach muss der Gesamtplan erneut gezeigt werden. Imports dürfen nur `routines` enthalten. Historische Alpha-3-Entwürfe mit Generator-Metadaten bleiben aus Kompatibilitätsgründen lesbar und sicher bestätigbar, können aber nicht mehr neu erzeugt werden.

Erst nachdem der vollständige aktuelle Plan als Ganzes bestätigt wurde, materialisiert `draft confirm --revision REVISION --content-hash HASH` exakt diesen Entwurf in einer atomaren Transaktion. Veraltete Vorschauen, parallele Bestätigungen und manipulierte Entwürfe werden abgewiesen. Eine laufende Session blockiert den Austausch und löst einen vollständigen Rollback aus. Historische Sessions, Sätze und Gerätealiases werden nicht geändert. `draft discard --revision REVISION` verwirft nur den Entwurf.

### Bisheriger manueller Ablauf

Der Modus `manual` bleibt erhalten. Er liest wiederholt `onboarding status`, fragt nur nach `next_field`, bestätigt jeden Wert und speichert ihn mit `onboarding set FIELD VALUE`. Die Reihenfolge bleibt `display_name`, `locale`, `units`, `goal`, `routine_count`, danach je Routine Name, Wochentage und Übungen samt Satz- und Wiederholungszielen. Passwortfelder werden immer abgelehnt.

## Trainingsplan ändern

Zuerst den aktuellen Plan samt IDs laden:

```bash
python3 skills/gym/scripts/gympilot.py --json plan
```

Danach genau eine Änderung bestätigen und ausführen. Abschließend den Plan erneut laden.

```bash
# Routine umbenennen, neu terminieren oder Notiz ändern
python3 skills/gym/scripts/gympilot.py --json routine update ROUTINE_ID --name "Oberkörper" --weekday 2 --weekday 5 --notes "Angepasst"

# Routine deaktivieren; historische Einheiten bleiben erhalten
python3 skills/gym/scripts/gympilot.py --json routine deactivate ROUTINE_ID

# Übung und Sollwerte ändern
python3 skills/gym/scripts/gympilot.py --json exercise update ROUTINE_ID EXERCISE_ID --name "Drücken" --sets 4 --min-reps 6 --max-reps 10 --notes "Kontrolliert" --unilateral

# Nur die künftige Zuordnung entfernen; Übung und Satzhistorie bleiben erhalten
python3 skills/gym/scripts/gympilot.py --json exercise remove ROUTINE_ID EXERCISE_ID
```

Ein Wochentag kann nur einer aktiven Routine gehören. GymPilot meldet einen Konflikt und wählt nicht selbstständig eine Routine. Eine Routine mit laufender Einheit kann erst nach Abschluss dieser Einheit deaktiviert werden.

## Passwortschutz

Das Passwort darf nur in einem privaten lokalen Terminal gesetzt werden. Die Abfrage verwendet `getpass`; Passwörter gehören weder in Telegram noch in ein CLI-Argument.

```bash
python3 skills/gym/scripts/gympilot.py security enable
```

## Test mit leerem Profil

Die folgenden Befehle legen außerhalb des temporären Verzeichnisses keine GymPilot-Daten an:

```bash
TMP_HOME="$(mktemp -d)"
HERMES_HOME="$TMP_HOME" python3 skills/gym/scripts/gympilot.py --json init
HERMES_HOME="$TMP_HOME" python3 skills/gym/scripts/gympilot.py --json status
HERMES_HOME="$TMP_HOME" python3 -m unittest discover -s tests -v
```

## Entwicklungstests

```bash
python3 -m compileall -q skills/gym tests
python3 -m unittest discover -s tests -v
node tests/test_web.mjs
```

Die CI führt diese Prüfungen mit Python 3.11, 3.12 und 3.13 aus. Der Node-Test führt Navigation, Satzdarstellung, Einheitenumrechnung und den Cache-Ausschluss für `/api/` tatsächlich aus.

## Datenschutz und Sicherheit

GymPilot enthält keine Analysefunktionen, Cloud-Synchronisierung, Telemetrie oder externen Laufzeitdateien. Datenbank, Exporte und Sicherungen können persönliche Trainingsdaten enthalten. Sie gehören nicht in öffentliche Synchronisationsordner. Laufzeitdaten werden nie im Skillverzeichnis gespeichert. Unter POSIX werden private Verzeichnisse mit `0700` und Datendateien mit `0600` angelegt. Export und Backup schreiben ausschließlich in zufällig benannte Unterpfade des Profilverzeichnisses; Symlink-Pfade werden abgelehnt.

Der Server bindet standardmäßig nur an Loopback. Wildcard- und öffentlich routbare Adressen werden abgelehnt; für LAN oder VPN muss eine konkrete private Adresse angegeben werden. Der Host-Header muss zur konfigurierten Adresse passen. JSON-Anfragen sind größenbegrenzt. Diese Schutzmaßnahmen ersetzen keine Firewall. Portweiterleitungen und öffentliche Tunnel werden nicht unterstützt. Für mobile PWA- und Offline-Nutzung ist `--https` erforderlich; ohne diese Option läuft LAN-Zugriff weiterhin unverschlüsselt.

Die Authentifizierung speichert nur Salt und Passwort-Hash: `scrypt`, soweit die Python-Installation es unterstützt, sonst PBKDF2-HMAC-SHA256 mit 600.000 Iterationen. Sitzungstokens werden zufällig erzeugt und nur gehasht in SQLite gespeichert. Cookies sind `HttpOnly` und `SameSite=Strict`. Weitere Angaben stehen in [SECURITY.md](SECURITY.md).

Prozesse derselben Betriebssystem-Benutzerkennung liegen innerhalb derselben lokalen Vertrauensgrenze. Die genaue Abgrenzung für parallele Änderungen an SQLite-Dateipfaden ist in [SECURITY.md](SECURITY.md) dokumentiert.

GymPilot ist keine medizinische Software. Einschränkungen dienen nur der Trainingsplanung; im Chat werden weder medizinische Diagnosen gestellt noch Passwörter erfragt.

## Datenmodell und Migrationen

`PRAGMA user_version` und `schema_migrations` protokollieren Schemaänderungen. Migration 2 ergänzt `studio_profile`, `plan_drafts` und eine stabile Planposition für Routinen; das übrige Modell umfasst `user_profile`, `onboarding_state`, `routines`, `routine_days`, `exercises`, `equipment_aliases`, `routine_exercises`, `sessions` und `workout_sets` sowie Tabellen für die Web-Authentifizierung. Künftige Änderungen erhalten eine neue geordnete Migration mit Tests. Eine bereits veröffentlichte Migration wird nicht nachträglich umgeschrieben.

Das Repository enthält weder persönliche Trainingspläne noch reale Datenbanken. Ein späterer Importer muss einen Quellpfad ausdrücklich verlangen und darf keine Nutzerdaten mitliefern.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE).
