# Sorbonne Cal — Synchro emploi du temps

Petit outil qui va chercher automatiquement les cours sur le CalDAV de l'UFR Info
(`cal.ufr-info-p6.jussieu.fr`), et permet de choisir soi-même ses cours/groupes
via une page web, pour générer un fichier `.ics` personnel à s'abonner sur son
calendrier (Apple Calendar, Google Calendar, etc.).

Deux façons de l'utiliser :
- **En local** (section 1-3) : tout tourne sur son ordinateur.
- **Dans le cloud** (section 4) : GitHub Actions rafraîchit le calendrier tout
  seul plusieurs fois par jour et le publie sur une adresse web fixe, pour un
  abonnement natif depuis son téléphone sans avoir besoin de l'ordinateur allumé.

## 1. Installation

```bash
cd sorbonne-cal
python3 -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Choisir ses cours (en local)

```bash
python3 sync.py     # première récupération des cours depuis le CalDAV
python3 app.py       # lance la page de sélection
```

Ouvrir **http://localhost:5050** : la page demande un prénom, puis redirige
vers `/u/<prénom>/` — c'est votre espace personnel. Cocher ses cours et
groupes, cliquer sur "Enregistrer". Chacun garde sa propre sélection (et son
propre lien `.ics`), même en partageant le même service (voir section 5).

## 3. Rafraîchir automatiquement en local (optionnel)

```bash
crontab -e
```
```
0 7,12 * * * cd /chemin/vers/sorbonne-cal && venv/bin/python3 sync.py
```

## 4. Version cloud : GitHub Actions + GitHub Pages

Une fois ses cours choisis en local (section 2), on exporte la sélection puis
on la publie via GitHub :

```bash
python3 export_selection.py <votre-prénom>   # écrit selection.json avec vos cours
git init                         # si ce n'est pas déjà un dépôt git
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:<utilisateur>/<repo>.git
git push -u origin main
```

Puis dans les réglages du dépôt GitHub :
1. **Settings > Pages** → Source : "GitHub Actions"
2. (optionnel) **Settings > Secrets and variables > Actions** → ajouter
   `CALDAV_USERNAME` / `CALDAV_PASSWORD` si les identifiants par défaut de
   l'école changent un jour. Pas obligatoire au début, les valeurs par défaut
   (`student.master` / `guest`) sont déjà utilisées.

Le workflow (`.github/workflows/sync.yml`) tourne automatiquement plusieurs
fois par jour (et à chaque `git push`), régénère le calendrier et le publie
sur une adresse du type :

```
https://<utilisateur>.github.io/<repo>/
```

Cette page affiche le calendrier (14 prochains jours + vue mensuelle sur 4
mois) et propose le lien `.ics` correspondant, à ajouter dans l'app Calendrier
du téléphone comme abonnement — il se synchronisera tout seul, sans que
l'ordinateur ait besoin d'être allumé.

Pour changer ses cours plus tard : relancer `app.py` en local, refaire
`export_selection.py`, puis `git push` — le workflow se redéclenche
automatiquement dès que `selection.json` change.

**Attention** : un dépôt GitHub public + Pages public signifie que
n'importe qui avec le lien peut voir l'emploi du temps (codes de cours,
horaires, salles — rien de très sensible, mais bon à savoir). Pour un dépôt
privé avec Pages, il faut un compte GitHub Pro/Team/Enterprise.

## 5. Partager avec des amis (via un lien, gratuit)

L'app tourne déjà en multi-utilisateurs : chaque prénom dans `/u/<prénom>/`
a sa propre sélection et son propre lien `.ics`, sans se marcher dessus.
Reste à rendre `python3 app.py` accessible depuis un lien, pas juste
`localhost`. Les hébergeurs cloud gratuits avec stockage persistant ont
quasiment disparu en 2026 (Render/Fly.io/Railway demandent tous quelques
euros par mois pour ça) — l'option vraiment gratuite est d'exposer son
propre ordinateur avec un **Cloudflare Tunnel** :

```bash
# macOS
brew install cloudflared

# lancer l'app d'un côté
python3 app.py

# de l'autre, exposer le port 5050 (tunnel "rapide", aucun compte requis)
cloudflared tunnel --url http://localhost:5050
```

`cloudflared` affiche un lien du genre `https://xxxx.trycloudflare.com` —
c'est ce lien à partager à ses amis (chacun va ensuite sur `/` pour choisir
son prénom). Ce lien change à chaque redémarrage du tunnel ; pour un lien
fixe et permanent, il faut un compte Cloudflare gratuit + un nom de domaine
et créer un "named tunnel" (voir la doc Cloudflare Tunnel).

**Contrainte** : ça ne marche que si l'ordinateur et la commande
`cloudflared` restent allumés. Si on veut que ça tourne 24/7 sans dépendre
de son ordinateur, il faut alors un petit hébergeur payant (Render Starter,
Railway Hobby, ~5-7 €/mois) avec un disque persistant pour `data.db`.

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
├── app.py                 # serveur web local (multi-utilisateurs : /u/<prénom>/)
├── sync.py                # synchronisation locale, régénère le .ics de tout le monde
├── export_selection.py    # exporte la sélection d'une personne vers selection.json
├── ci_build.py             # équivalent de sync.py mais pour GitHub Actions (une personne)
├── caldav_client.py       # connexion CalDAV, récupération et filtrage
├── models.py               # base SQLite (cours partagés + sélection par personne)
├── ics_generator.py       # génération des fichiers .ics
├── config.py               # réglages
├── selection.json          # cours choisis pour la version cloud (généré, à committer)
├── .github/workflows/sync.yml   # automatisation GitHub Actions
├── docs/                   # site statique publié sur GitHub Pages
├── static/ics/<prénom>.ics # fichier .ics de chaque personne (généré)
└── templates/, static/     # pages web locales (landing.html, index.html...)
```
