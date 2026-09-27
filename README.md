# Sorbonne Cal — Synchro emploi du temps

Petit outil qui va chercher automatiquement les cours sur le CalDAV de l'UFR Info
(`cal.ufr-info-p6.jussieu.fr`), permet à chacun de choisir ses propres cours/groupes
via une page web, et génère un fichier `.ics` personnel à s'abonner sur son calendrier
(Apple Calendar, Google Calendar, etc.). Multi-utilisateurs : chaque prénom a son
propre espace (`/u/<prénom>/`), sans se marcher dessus.

## Lien du site : https://sorbonne-cal.onrender.com

## 1. Installation en local

```bash
cd sorbonne-cal
python3 -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Utilisation en local (option A)

```bash
python3 sync.py     # première récupération des cours depuis le CalDAV
python3 app.py       # lance la page de sélection
```

Ouvrir **http://localhost:5050** : la page demande un prénom, puis redirige
vers `/u/<prénom>/`. Cocher ses cours et groupes, cliquer sur "Enregistrer".

Pour rafraîchir automatiquement en local (optionnel) :
```bash
crontab -e
```
```
0 7,12 * * * cd /chemin/vers/sorbonne-cal && venv/bin/python3 sync.py
```

## 3. Version en ligne pour tout le monde (option B — recommandée)

Un vrai site web, toujours accessible, avec les données stockées dans une
vraie base (pas sur votre ordinateur). Deux services gratuits à combiner :

### 3.1 Créer la base de données (Neon, gratuit)

1. Créer un compte sur [neon.tech](https://neon.tech) (gratuit, pas de carte
   bancaire nécessaire pour le tier gratuit)
2. Créer un nouveau projet → copier la **connection string** (commence par
   `postgres://...`)

### 3.2 Déployer le site (Render, gratuit)

1. Pousser ce projet sur GitHub (`git init && git add . && git commit -m init
   && git push`)
2. Sur [render.com](https://render.com) → New → Blueprint → sélectionner le
   dépôt GitHub (Render lit automatiquement `render.yaml` inclus dans le
   projet)
3. Render demande les variables d'environnement : coller la connection
   string de Neon dans `DATABASE_URL` (laisser `CALDAV_USERNAME`/
   `CALDAV_PASSWORD` vides, les valeurs par défaut suffisent)
4. Déployer. Render donne une adresse du type
   `https://sorbonne-cal-xxxx.onrender.com`

C'est ce lien à partager à ses amis. Chacun va sur `/`, choisit son prénom,
coche ses cours — tout est sauvegardé dans Neon, pour toujours, peu importe
que Render redémarre ou "s'endorme".

### 3.3 Garder le calendrier à jour (GitHub Actions)

Le service Render gratuit n'a pas de tâche planifiée intégrée, et s'endort
après 15 minutes d'inactivité (le réveil prend 20-30 secondes). Pour
contourner ça gratuitement :

1. Sur GitHub : **Settings > Secrets and variables > Actions** → ajouter un
   secret `APP_URL` = l'adresse Render de l'étape précédente
2. Le workflow `.github/workflows/ping.yml` (déjà dans le projet) va
   automatiquement, toutes les 20 minutes : déclencher `/api/sync` (donc
   récupérer les derniers cours depuis le CalDAV) et garder le service
   réveillé.

**Coût réel : 0 €.** Limite honnête : le premier visiteur après une période
vraiment creuse peut attendre ~20-30s le temps que Render se réveille (rare
si le ping toutes les 20 min fonctionne bien).

## 4. Alternative : partager depuis son ordinateur (option C)

Si on ne veut pas créer de compte Neon/Render, on peut exposer l'app locale
avec un tunnel gratuit — mais l'ordinateur doit rester allumé :

```bash
brew install cloudflared      # macOS
python3 app.py                 # dans un terminal
cloudflared tunnel --url http://localhost:5050   # dans un autre
```

`cloudflared` donne un lien `https://xxxx.trycloudflare.com` à partager.
Ce lien change à chaque redémarrage du tunnel (pour un lien fixe, il faut un
compte Cloudflare + un nom de domaine, voir la doc Cloudflare Tunnel).

## Réglages utiles (`config.py`)

- `JUNK_KEYWORDS` : mots-clés qui font ignorer un événement (stage,
  soutenance, vacances...)
- `ALLOWLIST_KEYWORDS` : mots-clés à toujours garder même si le format ne
  ressemble pas à un code de cours (ex. `["Anglais"]`)
- `SKIP_CALENDAR_SEGMENT_PREFIXES` : dossiers à ignorer entièrement (par
  défaut `["m2"]`)
- `DATABASE_URL` (variable d'environnement) : URL Postgres pour la version
  cloud ; absente = SQLite local automatiquement

## Structure du projet

```
sorbonne-cal/
├── app.py                    # serveur web (multi-utilisateurs : /u/<prénom>/)
├── sync.py                   # synchronisation locale, régénère le .ics de tout le monde
├── models.py                  # accès base de données (SQLite local OU Postgres cloud)
├── caldav_client.py          # connexion CalDAV, récupération et filtrage
├── ics_generator.py          # génération des fichiers .ics
├── config.py                  # réglages
├── render.yaml                 # blueprint de déploiement Render (option B)
├── .github/workflows/ping.yml       # réveille + resynchronise le site Render (option B)
├── .github/workflows/pages.yml      # publication statique GitHub Pages (option 5, optionnel)
├── export_selection.py, ci_build.py, docs/   # utilisés seulement par l'option 5
├── static/ics/<prénom>.ics   # fichier .ics de chaque personne (généré)
└── templates/, static/        # pages web (landing.html, index.html...)
```
