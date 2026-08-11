# GymPilot auf einem iPhone installieren

Diese Anleitung richtet GymPilot als lokale, read-only Web-App im privaten Netz ein. Trainingsdaten bleiben auf dem Rechner, auf dem GymPilot läuft. Das iPhone greift über eine konkrete private IP-Adresse und HTTPS darauf zu.

Die Installation verwendet einen Apple-Web-Clip. Das Hantelbild ist direkt in dessen Konfigurationsprofil eingebettet. Dadurch ist die Installation nicht von Safaris fehleranfälliger Auswahl zwischen Favicon, Apple-Touch-Icon und Manifesticon abhängig.

## Voraussetzungen

Auf dem Rechner:

- macOS oder Linux
- Python 3.11 oder neuer
- ein installierter GymPilot-Skill
- eine feste private LAN- oder VPN-Adresse
- iPhone und Rechner im selben privaten Netz

Für einen dauerhaft gültigen Link sollte der Router der verwendeten Rechneradresse immer dieselbe IP zuweisen. GymPilot akzeptiert keine Wildcard-Bindung, öffentliche IP-Adresse, Portweiterleitung oder öffentlichen Tunnel.

Die folgenden Beispiele verwenden `PRIVATE_IP`. Bei einer anderen privaten Adresse muss überall die tatsächlich installierte Adresse stehen.

## 1. GymPilot mit HTTPS installieren

Den Pfad zur installierten CLI bestimmen und den Dienst an die konkrete private Adresse binden:

```bash
GYM_CLI="/pfad/zum/installierten/gym/scripts/gympilot.py"
python3 "$GYM_CLI" --json service install --host PRIVATE_IP --https
```

Die JSON-Ausgabe muss mindestens diese Werte enthalten:

```json
{
  "installed": true,
  "running": true,
  "healthy": true,
  "url": "https://PRIVATE_IP:8765",
  "ca_certificate": "/lokaler/pfad/gympilot-local-ca.crt",
  "webclip_profile_url": "https://PRIVATE_IP:8765/install/GymPilot-WebClip.mobileconfig"
}
```

Anschließend den Status noch einmal lesen:

```bash
python3 "$GYM_CLI" --json service status
```

Die Installation ist erst bereit, wenn `installed`, `running` und `healthy` jeweils `true` sind. Der Prozess läuft auf macOS über `launchd` und unter Linux über `systemd --user`. Ein Neustart des Hermes-Gateways beendet ihn nicht.

## 2. Öffentliches CA-Zertifikat auf das iPhone übertragen

GymPilot erzeugt für die konkrete private IP ein Serverzertifikat und eine lokale Zertifizierungsstelle. Die Ausgabe `ca_certificate` verweist auf das öffentliche CA-Zertifikat. Nur diese `.crt`-Datei darf auf das eigene iPhone übertragen werden.

Der private CA-Schlüssel bleibt auf dem Rechner. Er liegt im profilbezogenen TLS-Verzeichnis, wird von GymPilot nicht ausgeliefert und darf weder übertragen noch in ein Repository aufgenommen werden.

Das öffentliche CA-Zertifikat über einen privaten Weg auf dem iPhone öffnen und die von iOS angezeigte Profilinstallation abschließen. Bezeichnungen und Position der Bestätigung können je nach iOS-Version und Geräteverwaltung abweichen. Maßgeblich ist die anschließende Prüfung in Safari. Dazu den Wert `url` aus der eigenen JSON-Ausgabe öffnen; er hat die Form:

```text
https://PRIVATE_IP:8765
```

Safari muss die Seite ohne Zertifikatswarnung laden. Solange eine Warnung erscheint, nicht mit der Web-Clip-Installation fortfahren. Apples aktuelle Hinweise zum manuellen Vertrauen in Zertifikatsprofile stehen unter [Trust manually installed certificate profiles in iOS and iPadOS](https://support.apple.com/102390).

## 3. Apple-Web-Clip installieren

Nicht Safaris Funktion „Zum Home-Bildschirm“ verwenden. Sie kann auf betroffenen Safari-/iOS-Versionen trotz korrekter Icondateien ein schwarzes oder graues Buchstabenicon erzeugen.

Stattdessen die von `service install` oder `service status` ausgegebene `webclip_profile_url` direkt in Safari öffnen. Die Adresse hat die Form:

```text
https://PRIVATE_IP:8765/install/GymPilot-WebClip.mobileconfig
```

Der GymPilot-Server erzeugt dieses Profil im Speicher für seinen aktuellen HTTPS-Endpunkt. Es enthält:

- den Namen `GymPilot`
- die installierte HTTPS-Adresse
- das eingebettete Hantelicon
- Vollbildstart
- normale Entfernbarkeit

Es enthält keine Zertifikate, privaten Schlüssel, Passwörter, Trainingsdaten, Konten, VPN-Einstellungen, Geräteeinschränkungen oder MDM-Anmeldung.

iOS lädt das Konfigurationsprofil und zeigt anschließend einen Installationshinweis. Vor der Bestätigung die Profilbeschreibung prüfen. Als Nutzlast darf nur ein Web-Clip für GymPilot erscheinen. Das Profil ist nicht signiert; iOS kann deshalb einen entsprechenden Hinweis anzeigen. Den Gerätecode ausschließlich selbst auf dem iPhone eingeben.

Nach der Installation muss auf dem Home-Bildschirm das Hantelicon mit dem Namen `GymPilot` erscheinen. Ein Buchstabe `G`, ein leeres weißes Feld oder ein anderes Symbol gilt als fehlgeschlagene Installation.

## 4. Erster Online-Start

Das iPhone bleibt zunächst mit dem privaten Netz verbunden.

1. GymPilot über das neue Hantelicon öffnen.
2. Warten, bis Übersicht, Pläne und Statistiken vollständig sichtbar sind.
3. Prüfen, ob die erwarteten Routinen und bisherigen Trainingsdaten angezeigt werden.
4. Die App vollständig schließen.

Dieser erste vollständige Online-Abruf erzeugt den privaten Offline-Snapshot. GymPilot spiegelt ihn origin-lokal in IndexedDB, Cache Storage und `localStorage`. Die Web-App bleibt read-only; neue Sätze und Änderungen werden ausschließlich über Hermes beziehungsweise Telegram erfasst.

Bei aktiviertem Dashboard-Passwort speichert GymPilot absichtlich keinen Offline-Snapshot. Ein Offline-Kaltstart ist in diesem Modus nicht vorgesehen.

## 5. Offline-Kaltstart prüfen

1. WLAN und Mobilfunkverbindung ausschalten oder den Flugmodus aktivieren.
2. Sicherstellen, dass GymPilot nicht mehr im App-Umschalter läuft.
3. GymPilot über das Hantelicon neu starten.
4. Übersicht, Pläne, Verlauf und Statistiken prüfen.
5. Auf den sichtbaren Hinweis `Offline · Stand …` achten.

Die Freigabe gilt nur als bestanden, wenn die App auf einem realen iPhone kalt startet, das Hantelicon zeigt und die zuvor online geladenen Daten vollständig lesbar bleiben. Desktopbrowser, Simulator, PNG-Prüfungen und automatisierte Tests ersetzen diesen Gerätetest nicht.

## Aktualisierung

Nach einem Skill-Update muss die Service-Definition mit dem aktuellen Code neu installiert werden:

```bash
hermes skills check
hermes skills update
python3 "$GYM_CLI" --json service install
python3 "$GYM_CLI" --json service status
```

Eine zuvor konfigurierte private Adresse und HTTPS-Einstellung werden ohne neue `--host`-Angabe übernommen. Bleibt die Adresse unverändert, muss der Web-Clip nicht neu installiert werden.

Ändert sich die private Adresse, passt das vorhandene Profil nicht mehr. Dann den bisherigen GymPilot-Web-Clip und das zugehörige Web-Clip-Profil über die aktuelle iOS-Profilverwaltung entfernen, den Dienst mit der neuen Adresse installieren und die neue `webclip_profile_url` verwenden.

## Fehlerbehebung

### Safari zeigt ein `G` statt der Hantel

Der Link wurde wahrscheinlich über „Zum Home-Bildschirm“ installiert. Diesen Eintrag entfernen und ausschließlich die von GymPilot ausgegebene `webclip_profile_url` verwenden.

### Der Profillink lädt nur eine Datei

Den Link direkt in Safari öffnen. Der integrierte GymPilot-Endpunkt liefert `application/x-apple-aspen-config`; ein Dateiserver mit `application/octet-stream` reicht nicht zuverlässig. Mit einem Rechner im selben Netz lässt sich der Header prüfen:

```bash
curl --cacert "/pfad/gympilot-local-ca.crt" -I \
  "https://PRIVATE_IP:8765/install/GymPilot-WebClip.mobileconfig"
```

Erwartet werden `200 OK`, `Content-Type: application/x-apple-aspen-config`, `Cache-Control: no-store` und `X-Content-Type-Options: nosniff`.

### Safari zeigt eine Zertifikatswarnung

Nicht installieren. Prüfen, ob die URL dieselbe private IP verwendet, für die `service install --host ... --https` ausgeführt wurde, und ob das öffentliche CA-Zertifikat auf diesem iPhone akzeptiert wurde. Nach einem IP-Wechsel den Dienst und das öffentliche Zertifikat für die neue Adresse neu einrichten. Niemals den privaten CA-Schlüssel übertragen.

### Das Profil enthält mehr als einen Web-Clip

Installation abbrechen. Das von GymPilot erzeugte Profil enthält genau eine Nutzlast vom Typ `com.apple.webClip.managed`. Zertifikate, Konten oder Geräteeinschränkungen gehören nicht hinein.

### Der Offline-Start zeigt keine Daten

GymPilot zuerst einmal online bis zur vollständig geladenen Übersicht öffnen. Bei Passwortschutz ist Offline-Persistenz deaktiviert. Ein HTTP-Endpunkt im LAN ist ebenfalls kein unterstützter Offline-PWA-Betrieb; dafür ist die HTTPS-Installation erforderlich.

### GymPilot ist nach einem Neustart nicht erreichbar

```bash
python3 "$GYM_CLI" --json service status
python3 "$GYM_CLI" --json service restart
```

Wenn die private IP inzwischen einem anderen Gerät zugewiesen wurde, zuerst die Netzkonfiguration korrigieren. Eine feste DHCP-Reservierung verhindert diesen Fall.

## Rücknahme

Den GymPilot-Web-Clip über den Home-Bildschirm oder über die aktuelle iOS-Profilverwaltung entfernen. Danach kann der lokale Dienst beendet und gelöscht werden:

```bash
python3 "$GYM_CLI" --json service uninstall
```

Das entfernt die Service-Definition, nicht die persönlichen Trainingsdaten unter `${HERMES_HOME:-~/.hermes}/gympilot`. Vor einer endgültigen Datenlöschung über `/gym backup` eine Sicherung erstellen.

## Releasekriterien

Änderungen an der iPhone-Installation werden erst veröffentlicht, wenn alle folgenden Punkte erfüllt sind:

- der produktive HTTPS-Dienst ist gesund
- das Profil enthält genau einen entfernbaren GymPilot-Web-Clip und keine geheimen Daten
- GET und HEAD des Profilendpunkts liefern den Apple-MIME-Typ und bei HEAD keinen Body
- vollständige Python- und JavaScript-Tests sowie Sicherheitsprüfungen sind grün
- ein unabhängiges Review meldet keine Sicherheits- oder Logikfehler
- ein reales iPhone zeigt die Hantel in der Installation und auf dem Home-Bildschirm
- ein realer Offline-Kaltstart zeigt die zuvor geladenen Trainings-, Plan- und Statistikdaten

Apple beschreibt die Web-Clip-Nutzlast unter [Web Clip device management payload settings](https://support.apple.com/guide/deployment/web-clip-payload-settings-depbc7c7808/web) und in der [Device-Management-Dokumentation](https://developer.apple.com/documentation/devicemanagement/webclip).
