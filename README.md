# GymPilot

GymPilot ist ein lokaler Trainingstracker mit mobiler Weboberfläche und PWA-Dateien. Er wird als Hermes-Skill `/gym` installiert und benötigt außer Python 3.11 oder neuer keine zusätzlichen Pakete. Dieses Repository dient als Sammelstelle für wiederverwendbare Hermes-Skills und die zugehörigen lokalen Anwendungen.

## Funktionen

- profilsichere SQLite-Daten unter `${HERMES_HOME:-~/.hermes}/gympilot`
- frei benannte Routinen mit festen Wochentagen
- Übungen mit Satzanzahl und Wiederholungsbereich
- laufende Einheiten, Satzkorrekturen und Vergleich mit der letzten Einheit derselben Routine
- Gewichteingabe in kg oder lb; Speicherung einheitlich in kg
- Gerätealiases für bestätigte Gerätefotos und gerätebezogene Satzhistorie
- unterbrechbares Onboarding im Chat mit Bestätigung jedes Werts
- JSON-Ausgabe für Hermes und lesbare Terminalausgabe
- mobile Oberfläche; als PWA installierbar, wenn der Browser einen sicheren Kontext bereitstellt
- Standardbindung an `127.0.0.1`; bewusste Freigabe für eine konkrete LAN- oder VPN-Adresse
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

Wurde GymPilot aus einem bereits laufenden Telegram-/Gateway-Chat installiert, muss anschließend im Chat **zwingend** `/reload-skills` gesendet werden. Der Gateway-Prozess hält die Liste dynamischer Skill-Befehle im Speicher; eine neue Unterhaltung allein aktualisiert diese Liste nicht. Erst wenn Hermes `gym` als hinzugefügten oder vorhandenen Skill bestätigt, mit `/gym setup` beginnen. Bleibt `/gym` unbekannt, einmal `/restart` senden und danach `/gym setup` erneut aufrufen.

### Aktualisieren

```bash
hermes skills check
hermes skills update
```

Nach einem Update aus einem laufenden Gateway-Chat ebenfalls `/reload-skills` senden; falls der Befehl danach noch nicht verfügbar ist, `/restart` verwenden.

Installierte Dateien nicht von Hand bearbeiten. Eine Aktualisierung ersetzt den Skillcode und seine Webdateien. Profil, Trainingsdaten, Backups und Exporte liegen außerhalb des Skillverzeichnisses und bleiben erhalten.

### Deinstallieren

```bash
hermes skills uninstall gym
```

Der Befehl entfernt den Skill, nicht die persönlichen Daten unter `${HERMES_HOME:-~/.hermes}/gympilot`. Vor einer endgültigen manuellen Löschung dieses Verzeichnisses sollte über `/gym backup` eine Sicherung erstellt werden.

## Direkter Start ohne Hermes

Aus dem geklonten Repository:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
python3 skills/gym/scripts/gympilot.py init
python3 skills/gym/scripts/gympilot.py routine add "Ganzkörper" --weekday 1 --weekday 4
python3 skills/gym/scripts/gympilot.py exercise add 1 "Kniebeuge" --sets 3 --min-reps 5 --max-reps 8
python3 skills/gym/scripts/gympilot.py server
```

Die Web-App läuft anschließend unter <http://127.0.0.1:8765>. Für maschinenlesbare Ausgaben steht `--json` direkt vor dem jeweiligen Befehl.

Browser behandeln Loopback als sicheren Kontext; dort kann der Service Worker registriert werden. Ein Telefonzugriff auf eine private LAN- oder VPN-Adresse über das eingebaute HTTP ist dagegen nur ein mobiles Web-Dashboard: Browser installieren daraus üblicherweise keine PWA. Für eine Installation auf dem Telefon ist zusätzlich ein privat betriebener, vom Telefon als vertrauenswürdig eingestufter HTTPS-Endpunkt erforderlich. GymPilot bringt bewusst keinen TLS- oder öffentlichen Tunnelbetrieb mit.

Häufig verwendete Befehle:

```bash
python3 skills/gym/scripts/gympilot.py --json status
python3 skills/gym/scripts/gympilot.py --json today
python3 skills/gym/scripts/gympilot.py --json plan
python3 skills/gym/scripts/gympilot.py --json session start --routine 1
python3 skills/gym/scripts/gympilot.py --json equipment add 1 "Beinpresse Studio A"
python3 skills/gym/scripts/gympilot.py --json set log 1 1 --weight 60 --reps 8 --equipment 1
python3 skills/gym/scripts/gympilot.py --json session finish 1
python3 skills/gym/scripts/gympilot.py --json export
python3 skills/gym/scripts/gympilot.py --json backup
```

## Unterbrechbares `/gym setup`

`/gym setup` liest wiederholt `onboarding status`, fragt nur nach `next_field`, lässt den Wert bestätigen und speichert ihn mit `onboarding set FIELD VALUE`. Jede bestätigte Antwort bleibt sofort erhalten.

Die Phasen und Feldnamen sind:

1. Profil: `display_name`, `locale`, `units`, `goal`
2. Anzahl Routinen: `routine_count`
3. Je Routine N: `routine_N_name`, `routine_N_weekdays` und `routine_N_exercise_count`
4. Je Übung M: `routine_N_exercise_M_name`, `_sets`, `_min_reps` und `_max_reps`

`routine_N_weekdays` verwendet durch Kommas getrennte ISO-Wochentage von 1 bis 7. Bei `phase: complete` legt GymPilot Routinen und Übungen in einer Transaktion an. Ein unterbrochenes Setup wird beim ersten fehlenden Feld fortgesetzt. Nach dem Abschluss sind die Setup-Antworten gesperrt; spätere Änderungen erfolgen über `/gym plan`. Passwortfelder werden im Onboarding grundsätzlich abgelehnt.

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

Der Server bindet standardmäßig nur an Loopback. Wildcard- und öffentlich routbare Adressen werden abgelehnt; für LAN oder VPN muss eine konkrete private Adresse angegeben werden. Der Host-Header muss zur konfigurierten Adresse passen. JSON-Anfragen sind größenbegrenzt. Diese Schutzmaßnahmen ersetzen keine Firewall. Portweiterleitungen und öffentliche Tunnel werden nicht unterstützt. Im LAN läuft HTTP unverschlüsselt; außerhalb des Geräts sollte ein vertrauenswürdiges VPN verwendet werden.

Die Authentifizierung speichert nur Salt und Passwort-Hash: `scrypt`, soweit die Python-Installation es unterstützt, sonst PBKDF2-HMAC-SHA256 mit 600.000 Iterationen. Sitzungstokens werden zufällig erzeugt und nur gehasht in SQLite gespeichert. Cookies sind `HttpOnly` und `SameSite=Strict`. Weitere Angaben stehen in [SECURITY.md](SECURITY.md).

GymPilot ist keine medizinische Software und erteilt keine medizinischen Ratschläge.

## Datenmodell und Migrationen

`PRAGMA user_version` und `schema_migrations` protokollieren Schemaänderungen. Das Modell umfasst `user_profile`, `onboarding_state`, `routines`, `routine_days`, `exercises`, `equipment_aliases`, `routine_exercises`, `sessions` und `workout_sets` sowie Tabellen für die Web-Authentifizierung. Künftige Änderungen erhalten eine neue geordnete Migration mit Tests. Eine bereits veröffentlichte Migration wird nicht nachträglich umgeschrieben.

Das Repository enthält weder persönliche Trainingspläne noch reale Datenbanken. Ein späterer Importer muss einen Quellpfad ausdrücklich verlangen und darf keine Nutzerdaten mitliefern.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE).
