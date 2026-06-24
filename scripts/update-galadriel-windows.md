# Protocole sûr de mise à jour Galadriel / Hermes Windows

Ce protocole est le chemin de référence quand Scorpheus demande à Galadriel de se mettre à jour depuis l’application Desktop, le TUI ou une session CLI. Il évite le scénario dangereux : update en place, reboot raté, application crashée et plus aucun canal de secours.

## Principes non négociables

1. Ne jamais faire de `git reset --hard`, `git clean`, force-push ou suppression de branche pour “réparer” une mise à jour Galadriel sans demande explicite de Scorpheus.
2. Ne jamais pousser vers `upstream`. Le fork de Scorpheus est `origin`; le repo officiel NousResearch est `upstream`.
3. Ne jamais merger upstream au-dessus d’un working tree sale sans protéger les changements locaux : commit, stash nommé, ou branche de sauvegarde lisible.
4. L’update Windows doit rester transactionnelle : snapshot avant changement, preflight de merge dans un worktree jetable, logs persistants, relance détachée, healthcheck, fallback TUI.
5. Ne jamais laisser le Desktop/Vite pointer sur un worktree contenant des marqueurs de conflit Git. Si `upstream/main` ou une stash locale conflitue, l’update doit s’arrêter avant de modifier le worktree live.
6. Si le Desktop affiche `Hermes couldn't start` / `Could not connect to Hermes gateway`, vérifier d’abord le backend et `/api/ws`; ne pas conclure trop vite que le backend est mort.

## Topologie Git attendue

Depuis :

```bash
cd C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/hermes-agent
```

Les remotes doivent être :

```text
origin   https://github.com/scorpheus/hermes-agent.git
upstream https://github.com/NousResearch/hermes-agent.git
```

`upstream` doit être fetch-only / push désactivé quand possible.

## Préflight obligatoire

```bash
git status --short --branch
git remote -v
git branch -vv
git log --oneline --decorate -8
test -f .git/MERGE_HEAD && echo MERGE_HEAD_EXISTS || echo NO_MERGE_HEAD
```

Si des fichiers sont modifiés, inspecter le diff et committer les corrections locales avant d’intégrer upstream. Ne pas utiliser `git add .` sans comprendre les fichiers non suivis.

## Synchroniser sans casse

```bash
git fetch --prune origin
git fetch --prune upstream main
printf 'origin divergence HEAD...origin/main: '; git rev-list --left-right --count HEAD...origin/main
printf 'upstream divergence HEAD...upstream/main: '; git rev-list --left-right --count HEAD...upstream/main
git merge-base --is-ancestor origin/main HEAD && echo 'origin/main ancestor: yes' || echo 'origin/main ancestor: no'
```

Si `origin/main` n’est pas ancêtre de `HEAD`, ne pas pousser : il y a des commits distants non intégrés.

Si `upstream/main` a avancé, l’updater versionné ne doit plus lancer le merge directement dans le worktree live. Il doit d’abord faire le même merge dans un worktree jetable sous :

```text
C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/data/update-preflight/merge-YYYYMMDD-HHMMSS
```

Le preflight doit :

- merger `upstream/main` dans ce worktree jetable ;
- appliquer la stash nommée si le worktree local était sale ;
- scanner les fichiers suivis pour des marqueurs en début de ligne `<<<<<<<`, `>>>>>>>` ou `|||||||` ;
- écrire les détails dans le recovery bundle (`preflight-upstream-conflicts.txt`, `preflight-stash-conflicts.txt`, `conflict-markers-*.txt`) ;
- s’arrêter sans toucher au worktree live si un conflit est détecté.

Une fois le preflight vert seulement, faire le merge live en mode abortable :

```bash
git merge --no-commit --no-ff upstream/main
# scan conflict markers + git diff --check
git commit --no-edit
```

Résoudre les conflits en conservant l’identité Galadriel quand elle est locale et volontaire : `productName`, `appId`, icônes, lancement Windows, fallback TUI, et surfaces Desktop Galadriel. Accepter les ajouts upstream qui ne cassent pas cette identité.

## Update Windows transactionnel

Le script versionné de référence est :

```text
scripts/update-galadriel-windows.ps1
```

Le wrapper local hors repo peut déléguer vers lui :

```text
C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/Update-Galadriel-Windows.ps1
```

Avant une vraie modification, l’updater doit écrire un bundle de récupération sous :

```text
C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/data/backups/galadriel-update-YYYYMMDD-HHMMSS
```

Ce bundle doit contenir au minimum :

- `head.txt`
- `status.txt`
- `remotes.txt`
- `worktree.patch`
- `index.patch`
- `stashes.txt`

En cas d’échec après handoff Desktop, l’updater doit logguer puis ouvrir le TUI :

```text
C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/data/logs/galadriel-update-fallback.log
C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/Start-Hermes-Windows.bat --continue
```

Depuis le Desktop, l’appel sûr doit préférer :

```powershell
Update-Galadriel-Windows.ps1 -FallbackToTui -RelaunchDesktop
```

## Vérification post-update

Ne pas annoncer une relance propre sans vérifications réelles.

Minimum Desktop/runtime :

```bash
curl -sS -o /tmp/gal.out -w '%{http_code}\n' --max-time 5 http://127.0.0.1:5174/
curl -sS -o /tmp/gal.out -w '%{http_code}\n' --max-time 5 http://127.0.0.1:9119/kanban
curl -sS -o /tmp/gal.out -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8000/health
curl -sS -o /tmp/gal.out -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8080/v1/models
curl -sS -o /tmp/gal.out -w '%{http_code}\n' --max-time 5 http://127.0.0.1:8081/v1/models
```

Si le Desktop affiche `Could not connect to Hermes gateway`, vérifier le backend éphémère :

1. chercher dans `hermes_core/home/logs/desktop.log` une ligne `HERMES_DASHBOARD_READY port=<port>` ;
2. tester `http://127.0.0.1:<port>/api/status` ;
3. extraire le token injecté dans le HTML de `http://127.0.0.1:<port>/` ;
4. ouvrir un vrai WebSocket `/api/ws?token=...`.

Backend sain + WebSocket qui finit par s’ouvrir = course de démarrage renderer, pas backend mort.

## Tests avant commit/push

Selon les fichiers touchés :

```bash
cd C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/hermes-agent
npm run typecheck
npm run test:desktop:platforms
.venv/Scripts/python.exe -m pytest tests/test_hermes_logging.py -q -o addopts=
git diff --check
```

Pour les scripts PowerShell :

```powershell
$files=@(
  'C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/Start-GaladrielCompanion.ps1',
  'C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/Update-Galadriel-Windows.ps1',
  'C:/Users/scorp/Documents/Projets_Perso/GaladrielCompanionApp/hermes_core/hermes-agent/scripts/update-galadriel-windows.ps1'
)
foreach($f in $files){
  $tokens=$null; $errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$tokens,[ref]$errors) | Out-Null
  if($errors.Count){ throw "Parse failed: $f" }
}
```

## Commit et push

Commits attendus :

1. commit local des corrections Galadriel / protocole ;
2. merge commit éventuel de `upstream/main` ;
3. push normal vers `origin main` seulement.

```bash
git add <fichiers compris et vérifiés>
git commit -m "fix(update): harden Galadriel Windows self-update"
git fetch --prune origin
git merge-base --is-ancestor origin/main HEAD || exit 1
git push origin main
```

État final attendu :

```text
## main...origin/main
HEAD == origin/main
divergence origin: 0 0
```

Si upstream a trop divergé ou produit des conflits non triviaux, arrêter avec un état protégé : commit local fait, branche de sauvegarde créée si nécessaire, aucun reset destructif, TUI opérationnel, et rapport clair à Scorpheus.
