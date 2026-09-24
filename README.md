# Sorbonne Cal — Synchro emploi du temps

Petit outil qui va chercher automatiquement les cours sur le CalDAV de l'UFR Info
(`cal.ufr-info-p6.jussieu.fr`), et permet de choisir soi-même ses cours/groupes
via une page web, pour générer un fichier `.ics` personnel à s'abonner sur son
calendrier (Apple Calendar, Google Calendar, etc.).

## Installation

```bash
cd sorbonne-cal
python3 -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Première synchronisation

```bash
python3 sync.py
```

Ça se connecte au serveur CalDAV de l'école et récupère tous les cours
disponibles dans une base locale (`data.db`). Peut prendre un moment la
première fois.

## Lancer la page de sélection

```bash
python3 app.py
```

Ouvrir **http://localhost:5050**, cocher ses cours et groupes, puis cliquer
sur "Enregistrer et générer le .ics".

## S'abonner depuis son calendrier

La page affiche un lien du type :

```
http://localhost:5050/mon_emploi_du_temps.ics
```

À ajouter dans l'app Calendrier comme "abonnement". Attention : c'est une
adresse locale, valable seulement depuis cet ordinateur (ou le même wifi en
remplaçant `localhost` par l'IP de la machine).

## Rafraîchir automatiquement (optionnel)

Pour que les données se mettent à jour toutes seules chaque jour, ajouter une
tâche cron :

```bash
crontab -e
```

```
0 7,12 * * * cd /chemin/vers/sorbonne-cal && venv/bin/python3 sync.py
```

## Réglages utiles (`config.py`)

- `JUNK_KEYWORDS` : mots-clés qui font ignorer un événement (stage,
  soutenance, vacances...)
- `ALLOWLIST_KEYWORDS` : mots-clés à toujours garder même si le format ne
  ressemble pas à un code de cours (ex. `["Anglais"]`)
- `SKIP_CALENDAR_SEGMENT_PREFIXES` : dossiers à ignorer entièrement (par
  défaut `["m2"]`)

## Structure du projet

```
sorbonne-cal/
├── app.py              # serveur web (page de sélection + API)
├── sync.py             # script de synchronisation (pour cron)
├── caldav_client.py    # connexion CalDAV, récupération et filtrage
├── models.py            # base SQLite (cours + sélection utilisateur)
├── ics_generator.py    # génération du fichier .ics final
├── config.py            # réglages
└── templates/, static/  # page web
```
