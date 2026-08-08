# GymPilot

GymPilot ist ein lokaler Trainingstracker mit mobiler Weboberfläche und PWA-Dateien. Er wird als Hermes-Skill `/gym` installiert und benötigt außer Python 3.11 oder neuer keine zusätzlichen Pakete. Dieses Repository dient als Sammelstelle für wiederverwendbare Hermes-Skills und die zugehörigen lokalen Anwendungen.

## Funktionen

- profilsichere SQLite-Daten unter `${HERMES_HOME:-~/.hermes}/gympilot`
- frei benannte Routinen mit festen Wochentagen
- Übungen mit Satzanzahl und Wiederholungsbereich
- laufende Einheiten, Satzkorrekturen und Vergleich mit der letzten Einheit derselben Routine
- Gewichteingabe in kg oder lb; Speicherung einheitlich in kg
- Gerätealiases für bestätigte Gerätefotos und gerätebezogene Satzhistorie
- drei Setup-Wege: Gesamtplan importieren, lokal automatisch erzeugen oder weiterhin manuell eingeben
- persistenter Gesamtentwurf mit vollständiger Vorschau und genau einer atomaren Gesamtbestätigung
- dauerhaft editierbares Geräte-/Studioprofil und deterministische Übungsauswahl aus einer kuratierten lokalen Bibliothek
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
python3 skills/gym/scripts/gympilot.py --json draft capabilities
python3 skills/gym/scripts/gympilot.py --json studio-profile update --equipment barbell --equipment bench
python3 skills/gym/scripts/gympilot.py --json draft generate --goal strength --day 1 --day 4 --duration 45 --experience intermediate
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

`onboarding status` nennt die drei Modi `import`, `generate` und `manual`. Die Auswahl wird mit `onboarding mode MODUS` gespeichert. Ein vorhandener Entwurf bleibt über Prozess- und Chatunterbrechungen hinweg erhalten. `draft show` ist rein lesend und materialisiert niemals einen Plan.

### Vollständigen Plan importieren

Ein in Telegram eingefügter Gesamtplan wird von Hermes als Ganzes gelesen und in striktes JSON für `draft import JSON` übertragen. Der Nutzer muss das JSON nicht selbst schreiben. Es enthält `routines`; jede Routine hat `name`, eindeutige ISO-`weekdays` und `exercises`. Jede Übung enthält `name`, `sets`, `min_reps` und `max_reps`. Doppelte JSON-Schlüssel, `NaN`, `Infinity`, doppelte Tage, überschrittene Anzahlgrenzen und ungültige Wiederholungsbereiche werden abgelehnt.

Existiert bereits ein Entwurf, wird er nicht still überschrieben. Ein bewusster vollständiger Ersatz benötigt `--replace-revision REVISION` mit der Revision der letzten Vorschau.

### Gesamtplan automatisch erzeugen

`draft generate` berücksichtigt eines der vier Ziele `muscle_gain`, `strength`, `general_fitness` und `weight_loss`, ein bis sechs Trainingstage, Dauer, Erfahrung, bevorzugte Körperbereiche, vermiedene Übungen und kontrollierte Einschränkungen. Das dauerhafte Geräteprofil wird mit `studio-profile show` gelesen und mit `studio-profile update --equipment NAME [...]` vollständig und editierbar gespeichert. `studio-profile update` ohne `--equipment` setzt es bewusst auf Bodyweight beziehungsweise keine Geräte zurück. `draft capabilities` zeigt alle unterstützten Geräte, Fokusbereiche, Einschränkungen und Übungsnamen. Unbekannte Werte und Tippfehler werden abgewiesen statt ignoriert.

Die Übungsauswahl ist deterministisch und erfolgt ausschließlich aus einer kuratierten lokalen Bibliothek mit 33 Übungen; es gibt keinen Cloud-Aufruf. Je nach Anzahl der Trainingstage entstehen Ganzkörper-, Ober-/Unterkörper- oder Push/Pull/Beine-Aufteilungen. Satz- und Wiederholungsziele unterscheiden Haupt- und Zubehörübungen sowie Ziel und Erfahrung. Das Dauerbudget berücksichtigt Sätze, Pausen und Gerätewechsel. Gerätefreie Varianten dienen als kontrollierter Fallback, nicht als zufälliger Ersatz.

```bash
python3 skills/gym/scripts/gympilot.py --json studio-profile update --equipment barbell --equipment bench --equipment dumbbell
python3 skills/gym/scripts/gympilot.py --json draft generate --goal muscle_gain --day 1 --day 4 --duration 45 --experience intermediate --focus chest --avoid "Push-up" --restriction no_overhead
```

### Gesamtvorschau, Änderung und Bestätigung

`draft show` liefert den persistenten Entwurf nach jeder Unterbrechung zusammen mit einer monotonen `revision` und einem SHA-256-`content_hash` über das kanonische Plan-JSON. Mit `draft routine-update ... --revision REVISION` und `draft exercise-update ... --revision REVISION` lassen sich bestätigte Änderungswünsche strukturiert anwenden. Jede Änderung erhöht die Revision und erzeugt einen neuen Hash; danach muss der Gesamtplan erneut gezeigt werden.

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

Der Server bindet standardmäßig nur an Loopback. Wildcard- und öffentlich routbare Adressen werden abgelehnt; für LAN oder VPN muss eine konkrete private Adresse angegeben werden. Der Host-Header muss zur konfigurierten Adresse passen. JSON-Anfragen sind größenbegrenzt. Diese Schutzmaßnahmen ersetzen keine Firewall. Portweiterleitungen und öffentliche Tunnel werden nicht unterstützt. Im LAN läuft HTTP unverschlüsselt; außerhalb des Geräts sollte ein vertrauenswürdiges VPN verwendet werden.

Die Authentifizierung speichert nur Salt und Passwort-Hash: `scrypt`, soweit die Python-Installation es unterstützt, sonst PBKDF2-HMAC-SHA256 mit 600.000 Iterationen. Sitzungstokens werden zufällig erzeugt und nur gehasht in SQLite gespeichert. Cookies sind `HttpOnly` und `SameSite=Strict`. Weitere Angaben stehen in [SECURITY.md](SECURITY.md).

GymPilot ist keine medizinische Software. Einschränkungen dienen nur der Trainingsplanung; im Chat werden weder medizinische Diagnosen gestellt noch Passwörter erfragt.

## Datenmodell und Migrationen

`PRAGMA user_version` und `schema_migrations` protokollieren Schemaänderungen. Migration 2 ergänzt `studio_profile`, `plan_drafts` und eine stabile Planposition für Routinen; das übrige Modell umfasst `user_profile`, `onboarding_state`, `routines`, `routine_days`, `exercises`, `equipment_aliases`, `routine_exercises`, `sessions` und `workout_sets` sowie Tabellen für die Web-Authentifizierung. Künftige Änderungen erhalten eine neue geordnete Migration mit Tests. Eine bereits veröffentlichte Migration wird nicht nachträglich umgeschrieben.

Das Repository enthält weder persönliche Trainingspläne noch reale Datenbanken. Ein späterer Importer muss einen Quellpfad ausdrücklich verlangen und darf keine Nutzerdaten mitliefern.

## Lizenz

Der Code steht unter der [MIT-Lizenz](LICENSE).
