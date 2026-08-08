# Sicherheitsrichtlinie

## Unterstützte Versionen

Während der MVP-Phase wird der aktuelle Stand des Branches `main` unterstützt.

## Vorgesehener Einsatzbereich

GymPilot ist ausschließlich für Loopback, ein vertrauenswürdiges privates LAN oder ein VPN ausgelegt. Nicht unterstützt werden öffentlich erreichbare Installationen, Wildcard-Bindings, öffentliche Tunnel und Portweiterleitungen. Der eingebaute Server verwendet HTTP, nicht TLS.

## Sicherheitslücken melden

Bitte eine private GitHub Security Advisory für dieses Repository erstellen und kein öffentliches Issue verwenden. Ein Bericht darf keine echte GymPilot-Datenbank, Exporte, Passwörter, Cookies, IP-Adressen oder sonstige persönliche Daten enthalten.

## Schutzmaßnahmen

- Laufzeitdateien liegen im jeweiligen Hermes-Profil und nicht im installierten Skill.
- Passwörter werden über `getpass` eingegeben. CLI-Argumente und Onboarding-Felder akzeptieren keine Passwörter.
- Gespeichert wird ein gesalzener `scrypt`-Hash. Python-Versionen ohne OpenSSL-scrypt verwenden PBKDF2-HMAC-SHA256 mit 600.000 Iterationen.
- Sitzungscookies sind zufällig, `HttpOnly` und `SameSite=Strict`. Sie laufen nach 24 Stunden ab; serverseitig wird nur ihr Hash gespeichert.
- API-Antworten verwenden `Cache-Control: no-store`. Der Service Worker speichert keine Pfade unter `/api/`.
- Der HTTP-Host-Header muss zur konfigurierten Bind-Adresse passen. Das erschwert DNS-Rebinding-Angriffe.
- JSON-Anfragen sind auf 8 KiB begrenzt. `Content-Length` muss ausschließlich aus ASCII-Ziffern bestehen und genau einmal vorkommen; jede Form von `Transfer-Encoding` wird abgelehnt. Für die gesamte Anfrage gilt eine absolute Frist von 15 Sekunden, gleichzeitig werden höchstens 32 Anfragen bearbeitet.
- JSON wird strikt gelesen: Nichtstandardwerte wie `NaN` oder `Infinity` und doppelte Objektschlüssel werden abgelehnt.
- Unter POSIX erhalten Daten-, Export- und Backupverzeichnisse Modus `0700`; Datenbanken, Exporte und Sicherungsdateien erhalten `0600`.
- Export- und Backupziele werden ausschließlich zufällig unter dem privaten Profilpfad erzeugt. Symlinks in privaten Datenpfaden werden abgelehnt; Verzeichnis- und Dateierzeugung erfolgt unter POSIX deskriptorrelativ mit `O_NOFOLLOW`.
- Der Server setzt CSP, Frame-Schutz, `no-referrer` und Schutz vor MIME-Sniffing.
- Loginversuche werden über alle Serverthreads hinweg atomar reserviert. Nach fünf Fehlversuchen einer Quelladresse innerhalb von fünf Minuten greift eine prozessinterne Sperre.

## Grenzen

- HTTP-Verkehr im LAN ist nicht verschlüsselt. Für Zugriffe außerhalb des Geräts sollte Loopback oder ein vertrauenswürdiges VPN verwendet werden. Über eine nicht lokale HTTP-Adresse funktioniert die Oberfläche als Web-Dashboard, aber Browser erlauben dort normalerweise keine Service-Worker-Registrierung oder PWA-Installation; dafür ist ein separat verwalteter privater HTTPS-Endpunkt nötig.
- Die Login-Sperre wird bei einem Prozessneustart zurückgesetzt. Sie ist eine lokale Basissicherung und kein Schutz für einen Internetdienst.
- Profile werden durch getrennte Dateipfade voneinander isoliert, nicht durch Betriebssystemkonten oder Container.
- Leere Werte für `HERMES_HOME` oder `GYMPILOT_DATA_DIR` gelten als nicht gesetzt; GymPilot verwendet dann das normale Profilverzeichnis.
- Wer Zugriff auf das lokale Benutzerkonto oder die Datenbankdatei hat, kann Trainingsmetadaten lesen und versuchen, den Passwort-Hash offline anzugreifen.
- Prozesse derselben Betriebssystem-Benutzerkennung gelten als Teil derselben Vertrauensgrenze. GymPilot schützt stabile unbekannte neuere SQLite-Schemas vor Änderungen und erkennt einen Dateiaustausch während der read-only Inspektion. Es verspricht jedoch keinen Schutz gegen einen absichtlich parallel laufenden Prozess derselben Benutzerkennung, der Datenbank-, Sidecar- oder übergeordnete Verzeichnispfade während des SQLite-Öffnens austauscht. Dafür wären Betriebssystemkontentrennung, ein Container oder eine native SQLite-VFS nötig.
