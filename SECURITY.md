# Sicherheitsrichtlinie

## Unterstützte Versionen

Während der MVP-Phase wird der aktuelle Stand des Branches `main` unterstützt.

## Vorgesehener Einsatzbereich

GymPilot ist ausschließlich für Loopback, ein vertrauenswürdiges privates LAN oder ein VPN ausgelegt. Nicht unterstützt werden öffentlich erreichbare Installationen, Wildcard-Bindings, öffentliche Tunnel und Portweiterleitungen. Der eingebaute Server verwendet standardmäßig HTTP; `service install --host PRIVATE_IP --https` aktiviert lokales TLS mit einer profilinternen privaten CA.

## Sicherheitslücken melden

Bitte eine private GitHub Security Advisory für dieses Repository erstellen und kein öffentliches Issue verwenden. Ein Bericht darf keine echte GymPilot-Datenbank, Exporte, Passwörter, Cookies, IP-Adressen oder sonstige persönliche Daten enthalten.

## Schutzmaßnahmen

- Laufzeitdateien liegen im jeweiligen Hermes-Profil und nicht im installierten Skill.
- Passwörter werden über `getpass` eingegeben. CLI-Argumente und Onboarding-Felder akzeptieren keine Passwörter.
- Gespeichert wird ein gesalzener `scrypt`-Hash. Python-Versionen ohne OpenSSL-scrypt verwenden PBKDF2-HMAC-SHA256 mit 600.000 Iterationen.
- Sitzungscookies sind zufällig, `HttpOnly` und `SameSite=Strict`; im HTTPS-Modus tragen sie zusätzlich `Secure`. Sie laufen nach 24 Stunden ab; serverseitig wird nur ihr Hash gespeichert.
- API-Antworten verwenden `Cache-Control: no-store`. Der Service Worker speichert keine Pfade unter `/api/`.
- Für den ungeschützten read-only Betrieb kopiert die Web-App ausschließlich den letzten vollständig autorisierten Auswertungsstand in einen versionierten Snapshot desselben Browser-Origins. Sie spiegelt denselben maximal 2 MB großen Datensatz in IndexedDB, einem eigens benannten privaten Cache Storage und `localStorage`. Der Service Worker bewahrt diesen privaten Cache bei Shell-Aktualisierungen, greift aber nicht auf seinen Inhalt zu; einzelne API-Antworten werden weiterhin niemals gecacht. Der Snapshot enthält keine Passwörter, Cookies, Tokens oder Authorization-Header und wird vollständig ersetzt. Bei aktiviertem Dashboard-Passwort wird kein Snapshot gespeichert. Passwortschutz, Authentifizierungsfehler und Logout setzen vor dem Löschen eine nicht geheime Sperrepoche. Block- und Freigabeepoche müssen übereinstimmen; alle Snapshotkopien verwenden epochenspezifische Schlüssel. Dadurch kann ein alter Browser-/PWA-Kontext nur seinen eigenen alten Schlüssel schreiben oder bereinigen, nicht den Snapshot einer neueren Freigabe. Bei fehlendem oder unzugänglichem Richtlinienspeicher werden Offline-Snapshots fail-closed nicht gelesen.
- Der HTTP-Host-Header muss zur konfigurierten Bind-Adresse passen. Das erschwert DNS-Rebinding-Angriffe.
- JSON-Anfragen sind auf 8 KiB begrenzt. `Content-Length` muss ausschließlich aus ASCII-Ziffern bestehen und genau einmal vorkommen; jede Form von `Transfer-Encoding` wird abgelehnt. Für die gesamte Anfrage gilt eine absolute Frist von 15 Sekunden, gleichzeitig werden höchstens 32 Anfragen bearbeitet.
- JSON wird strikt gelesen: Nichtstandardwerte wie `NaN` oder `Infinity` und doppelte Objektschlüssel werden abgelehnt.
- Unter POSIX erhalten Daten-, Export- und Backupverzeichnisse Modus `0700`; Datenbanken, Exporte und Sicherungsdateien erhalten `0600`.
- Export- und Backupziele werden ausschließlich zufällig unter dem privaten Profilpfad erzeugt. Symlinks in privaten Datenpfaden werden abgelehnt; Verzeichnis- und Dateierzeugung erfolgt unter POSIX deskriptorrelativ mit `O_NOFOLLOW`.
- Der Server setzt CSP, Frame-Schutz, `no-referrer` und Schutz vor MIME-Sniffing.
- Loginversuche werden über alle Serverthreads hinweg atomar reserviert. Nach fünf Fehlversuchen einer Quelladresse innerhalb von fünf Minuten greift eine prozessinterne Sperre.

## Grenzen

- HTTP-Verkehr im LAN ist nicht verschlüsselt und erlaubt normalerweise keine Service-Worker-Registrierung oder verlässliche PWA-Offline-Kaltstarts. Dafür ist der integrierte lokale HTTPS-Modus erforderlich. Das öffentliche CA-Zertifikat muss auf jedem Client einmal bewusst als vertrauenswürdig aktiviert werden; der private CA-Schlüssel bleibt ausschließlich im privaten GymPilot-Datenverzeichnis. Das Vertrauen gilt für alle Zertifikate dieser lokalen CA und sollte nur auf eigenen Geräten eingerichtet werden.
- Die Login-Sperre wird bei einem Prozessneustart zurückgesetzt. Sie ist eine lokale Basissicherung und kein Schutz für einen Internetdienst.
- Profile werden durch getrennte Dateipfade voneinander isoliert, nicht durch Betriebssystemkonten oder Container.
- Leere Werte für `HERMES_HOME` oder `GYMPILOT_DATA_DIR` gelten als nicht gesetzt; GymPilot verwendet dann das normale Profilverzeichnis.
- Wer Zugriff auf das lokale Benutzerkonto oder die Datenbankdatei hat, kann Trainingsmetadaten lesen und versuchen, den Passwort-Hash offline anzugreifen.
- Wer Zugriff auf das entsperrte Smartphone-Browserprofil hat, kann den dort gespeicherten unverschlüsselten Offline-Auswertungsstand lesen. Für sensible Installationen Dashboard-Passwort aktivieren; dann ist der Offline-Snapshot bewusst deaktiviert.
- Prozesse derselben Betriebssystem-Benutzerkennung gelten als Teil derselben Vertrauensgrenze. GymPilot schützt stabile unbekannte neuere SQLite-Schemas vor Änderungen und erkennt einen Dateiaustausch während der read-only Inspektion. Es verspricht jedoch keinen Schutz gegen einen absichtlich parallel laufenden Prozess derselben Benutzerkennung, der Datenbank-, Sidecar- oder übergeordnete Verzeichnispfade während des SQLite-Öffnens austauscht. Dafür wären Betriebssystemkontentrennung, ein Container oder eine native SQLite-VFS nötig.
