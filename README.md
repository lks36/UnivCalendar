# Sorbonne Cal — Emploi du temps UFR Info

Site web qui récupère automatiquement les cours sur le CalDAV de l'UFR Info
(`cal.ufr-info-p6.jussieu.fr`). Chacun coche ses cours et groupes une fois,
puis retrouve directement son emploi du temps à chaque visite.

- Pas d'inscription : chaque navigateur reçoit automatiquement un identifiant
  (cookie). Pour retrouver son emploi du temps sur un autre appareil, ouvrir
  le « lien personnel » affiché sur la page.
- Lien `.ics` optionnel pour s'abonner depuis l'app Calendrier du téléphone.

## En local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 sync.py      # récupère les cours
python3 app.py       # http://localhost:5050
```

Sans `DATABASE_URL`, les données sont stockées dans un fichier SQLite local
(`data.db`).

## En ligne (gratuit)

1. **Base de données** : créer un projet sur [neon.tech](https://neon.tech)
   et copier la connection string.
2. **Site** : sur [render.com](https://render.com) → New → Blueprint →
   choisir ce dépôt (`render.yaml` est lu automatiquement), coller la
   connection string dans `DATABASE_URL`.
3. **Maintien en éveil** (optionnel mais recommandé) : sur
   [UptimeRobot](https://uptimerobot.com), créer un moniteur HTTP(s) sur
   `https://<site>.onrender.com/health` toutes les 5 min.

Les cours se mettent à jour tout seuls : le site vérifie toutes les 10 min et
relance une synchronisation si les données ont plus de 3 h (`AUTO_SYNC_HOURS`).
La synchronisation tourne dans un processus séparé, le site reste réactif
pendant ce temps. Le bouton « Actualiser » permet aussi de la lancer à la main
(au plus une fois toutes les 10 min). `DISABLE_AUTO_SYNC=1` désactive
la synchronisation automatique.

Optionnel : `SYNC_TOKEN` protège `/api/sync` (synchronisation forcée,
`?token=<valeur>`).

## Abonnement depuis l'app Calendrier

Sous le calendrier, « S'abonner (Apple Calendrier) » ouvre le lien `webcal://`.
Sur Mac, choisir l'emplacement **iCloud** pour que l'abonnement apparaisse
aussi sur l'iPhone. Un fichier `.ics` *importé* ne se met jamais à jour ; seul
un *abonnement* suit les changements.

## Noms de séances qui changent

Les enseignants renomment souvent les séances (ex. « TME » devient « CS/TME »).
`matching.py` compare les séances par code d'UE et par morceaux de nom : une
séance renommée qui contient le groupe choisi est ajoutée automatiquement, les
autres groupes restent masqués. Une séance nouvelle qu'il ne sait pas classer
(examen, rattrapage…) apparaît en pointillés sur le calendrier avec
« Ajouter » / « Ignorer » ; elle n'entre dans l'abonnement `.ics` qu'une fois
ajoutée.

## Réglages (`config.py`)

- `JUNK_KEYWORDS` : événements ignorés (stage, soutenance, vacances...)
- `ALLOWLIST_KEYWORDS` : toujours gardés (ex. `["Anglais"]`)
- `SKIP_CALENDAR_SEGMENT_PREFIXES` : calendriers ignorés (par défaut `["m2"]`)

## Fichiers

```
app.py              serveur web (pages + API)
sync.py             synchronisation en ligne de commande
caldav_client.py    récupération et filtrage des cours
models.py           base de données (SQLite ou Postgres)
ics_generator.py    génération des fichiers .ics
config.py           réglages
render.yaml         déploiement Render
templates/, static/ pages web
```
