# Sauvegardes automatiques Ubuntu Server — MySQL/MariaDB & applications web

Deux scripts alternatifs (Bash et Python 3) pour automatiser la sauvegarde des **dossiers d'applications web** et des **bases de données MySQL/MariaDB** sur Ubuntu Server, avec des archives **quotidiennes** et **hebdomadaires**.

> Projet pédagogique partagé dans le cadre d'un retour d'expérience sur l'administration de serveurs Linux. **Adaptez et testez ce script avant toute utilisation en production.**

## Fonctionnalités

- Archivage compressé du dossier des applications (`/var/www` par défaut).
- Export logique de toutes les bases MySQL/MariaDB avec `mariadb-dump`.
- Sauvegarde quotidienne dans un répertoire daté.
- Copie hebdomadaire de la sauvegarde du dimanche.
- Contrôle basique de l'intégrité des archives (`tar -t` et `gzip -t`).
- Journalisation des opérations et verrouillage contre les exécutions simultanées.
- Suppression des archives anciennes selon une durée de conservation configurable dans le script.
- Automatisation avec `cron`.

## 1. Prérequis

- Ubuntu Server avec Bash et les utilitaires `tar`, `gzip`, `find`, `flock` et `cron`.
- MySQL ou MariaDB et son outil de sauvegarde (`mariadb-dump` ou `mysqldump`).
- Un compte système disposant des droits de lecture sur les applications et d'écriture dans le dossier de sauvegarde.
- Un compte MySQL/MariaDB dédié aux sauvegardes et doté des **privilèges strictement nécessaires** aux données exportées.
- Un espace disque suffisant (les sauvegardes quotidiennes et hebdomadaires occupent de l'espace supplémentaire).

Sur Ubuntu, vérifiez les outils :

```bash
command -v bash tar gzip find flock cron mariadb-dump
```

Si `mariadb-dump` est absent et que vous utilisez MySQL, vérifiez `mysqldump` puis remplacez la commande dans le script.

## 2. Installation

Enregistrez le script fourni avec cet article dans :

```text
/usr/local/sbin/auto-backup.sh
```

Puis lancez :

```bash
sudo chmod 700 /usr/local/sbin/auto-backup.sh
sudo mkdir -p /srv/backups
sudo chmod 700 /srv/backups
```

> **Attention :** les fichiers `auto-backup.sh` et `auto-backup.py` sont fournis à la racine du projet. Vérifiez leur contenu avant toute exécution.

## 3. Configuration de MySQL/MariaDB

Créez un fichier de configuration pour un compte dédié, **sans inscrire le mot de passe dans le script** :

```bash
sudo mkdir -p /etc/mysql
sudo nano /etc/mysql/backup-client.cnf
```

Contenu d'exemple :

```ini
[client]
user=backup_user
password=REMPLACER_PAR_UN_SECRET_FORT
```

Protégez-le :

```bash
sudo chown root:root /etc/mysql/backup-client.cnf
sudo chmod 600 /etc/mysql/backup-client.cnf
```

Le compte doit pouvoir se connecter et effectuer l'export. Les privilèges exacts dépendent de votre version de MySQL/MariaDB et des objets à sauvegarder (vues, routines, événements, triggers). Privilégiez un compte dédié, avec accès minimal, et évitez d'utiliser le compte `root` de la base. **N'ajoutez jamais ce fichier de secrets à GitHub.**

Vérifiez l'accès en utilisant un client compatible :

```bash
sudo mariadb --defaults-extra-file=/etc/mysql/backup-client.cnf -e 'SELECT 1;'
```

Pour MySQL, remplacez `mariadb` par `mysql` si nécessaire.

## 4. Personnalisation du script

Modifiez ces variables au début de `auto-backup.sh` :

```bash
ROOT="/srv/backups"                   # Destination des sauvegardes
WEB="/var/www"                        # Dossier des applications à archiver
CNF="/etc/mysql/backup-client.cnf"     # Identifiants de la base
```

Le script exporte par défaut **toutes les bases** (`--all-databases`). Pour limiter la sélection, adaptez avec précaution la commande `mariadb-dump` aux bases requises.

> Avec Laravel, veillez à inclure les dossiers de stockage utiles (par exemple les fichiers envoyés par les utilisateurs) et les éventuelles données conservées **hors** de `/var/www`. Les fichiers `.env` inclus dans les archives sont sensibles : contrôlez rigoureusement l'accès au stockage des sauvegardes.

## 5. Tests manuels

Exécutez d'abord la sauvegarde quotidienne :

```bash
sudo /usr/local/sbin/auto-backup.sh daily
```

Vérifiez le journal et les fichiers :

```bash
sudo tail -n 30 /srv/backups/backup.log
sudo ls -lah /srv/backups/daily/"$(date +%F)"/
```

La sauvegarde hebdomadaire copie **la sauvegarde quotidienne du jour** :

```bash
sudo /usr/local/sbin/auto-backup.sh weekly
```

Le mode `weekly` échoue normalement si le dossier quotidien du jour n'existe pas.

## 6. Planification avec cron

Ouvrez la table `cron` du compte `root` :

```bash
sudo crontab -e
```

Ajoutez :

```cron
# Tous les jours à 02h00 : sauvegarde des dossiers et des bases
0 2 * * * /usr/local/sbin/auto-backup.sh daily

# Chaque dimanche à 03h00 : copie hebdomadaire de la sauvegarde du jour
0 3 * * 0 /usr/local/sbin/auto-backup.sh weekly
```

Ces horaires utilisent le **fuseau horaire du serveur**. Assurez-vous que la sauvegarde quotidienne se termine avant le déclenchement hebdomadaire ; le verrou protège des exécutions concurrentes, mais une tâche hebdomadaire lancée pendant la tâche quotidienne échouera au lieu d'attendre.

## 7. Structure des fichiers

```text
/srv/backups/
├── daily/
│   ├── 2026-11-17/
│   │   ├── apps.tar.gz
│   │   └── databases.sql.gz
│   └── 2026-11-18/
│       ├── apps.tar.gz
│       └── databases.sql.gz
├── weekly/
│   └── 2026-W47/
│       ├── apps.tar.gz
│       └── databases.sql.gz
├── backup.log
└── .backup.lock
```

Les dates ci-dessus sont illustratives.

## 8. Politique de rétention

La version proposée contient :

```bash
# Suppression des dossiers quotidiens de plus de 7 jours révolus environ
find "$ROOT/daily" -mindepth 1 -maxdepth 1 \
  -type d -name '20??-??-??' -mtime +7 -exec rm -rf -- {} +

# Suppression des dossiers hebdomadaires de plus de 56 jours révolus environ
find "$ROOT/weekly" -mindepth 1 -maxdepth 1 \
  -type d -name '????-W??' -mtime +56 -exec rm -rf -- {} +
```

**À savoir :** `-mtime +7` n'est pas une garantie de conserver exactement sept sauvegardes : `find` raisonne par tranches de 24 h révolues. De même, le nettoyage hebdomadaire est basé sur l'âge du dossier et non sur un nombre exact de huit archives. Adaptez ces durées à vos exigences.

## 9. Vérifier et tester une restauration

Inspectez une archive de fichiers :

```bash
sudo tar -tzf /srv/backups/daily/AAAA-MM-JJ/apps.tar.gz | head
```

Vérifiez le fichier compressé SQL :

```bash
sudo gzip -t /srv/backups/daily/AAAA-MM-JJ/databases.sql.gz
```

Ces contrôles **ne prouvent pas** qu'une restauration complète fonctionne. Effectuez régulièrement un exercice de restauration **dans un environnement isolé**, avec une base de données de test, et contrôlez les données, les utilisateurs, les paramètres et les fonctionnalités des applications.

⚠️ L'archive SQL générée avec `--all-databases` peut inclure des bases système et des objets avec privilèges. **Ne l'importez pas directement sur un serveur de production ou sur une instance partagée.** Pour vos exercices, utilisez une instance MySQL/MariaDB jetable et isolée, ou un dump limité à une base applicative.

## 10. Limitations importantes

Ce script est un **point de départ** et non une solution complète de reprise d'activité :

- Il stocke ses copies **sur le même serveur**, ce qui ne protège pas contre une panne matérielle, un ransomware ou la perte totale de l'hôte.
- La copie hebdomadaire dépend de la réussite de la sauvegarde quotidienne du dimanche.
- Il ne synchronise pas automatiquement les fichiers applicatifs avec les bases pendant l'export : des modifications simultanées peuvent rendre l'ensemble incohérent.
- L'option `--single-transaction` est conçue pour les moteurs transactionnels comme **InnoDB** ; elle ne garantit pas un cliché cohérent des tables non transactionnelles.
- Les commandes de vérification testent les formats, **pas** la capacité de reprise fonctionnelle.
- Il ne comprend pas de surveillance centralisée ni d'alerte en cas d'échec.
- Le fichier `backup.log` ne fait pas l'objet d'une rotation automatique.
- Une sauvegarde existante à la date du jour n'est pas écrasée ; cela évite les écrasements accidentels mais nécessite une procédure explicite pour relancer une sauvegarde échouée ou interrompue.

**Pour un usage professionnel**, ajoutez une copie chiffrée hors serveur (NAS ou stockage distant), un système d'alertes, des tests périodiques de restauration et un plan documenté de reprise. Une stratégie de type **3-2-1** constitue une bonne base.

## 11. Sécurité et partage du dépôt

Avant toute publication sur GitHub :

1. Ne partagez **aucune** adresse IP interne, aucun nom de domaine privé, aucun identifiant ni mot de passe réel.
2. N'incluez pas les dossiers `daily/`, `weekly/`, les archives `.sql.gz` / `.tar.gz`, ni les fichiers `.env` ou `backup-client.cnf`.
3. Vérifiez les permissions des dossiers et les accès aux archives.
4. Documentez les adaptations nécessaires selon l'environnement.

Exemple de `.gitignore` :

```gitignore
*.sql
*.sql.gz
*.tar.gz
*.log
.env
backup-client.cnf
backups/
```

## Licence et réutilisation

Exemples techniques fournis à titre pédagogique. Aucune licence de redistribution explicite n’est accordée tant qu’un fichier `LICENSE` n’est pas ajouté.

---

**Série LinkedIn : _De mon expérience dans l'administration des serveurs_**  
**Épisode 2 : Automatiser les sauvegardes Ubuntu Server**

_La sauvegarde n'est réellement utile que si elle peut être restaurée._

## Variante Python 3

Le dépôt propose également `auto-backup.py`, une implémentation alternative (elle produit la même organisation d'archives). **Choisissez un seul des deux scripts pour la planification** afin d'éviter les exécutions redondantes.

```bash
sudo install -m 700 auto-backup.py /usr/local/sbin/auto-backup.py
sudo python3 /usr/local/sbin/auto-backup.py daily
sudo python3 /usr/local/sbin/auto-backup.py weekly
```

Pour utiliser Python avec `cron`, remplacez les deux entrées Bash par :

```cron
0 2 * * * /usr/bin/python3 /usr/local/sbin/auto-backup.py daily
0 3 * * 0 /usr/bin/python3 /usr/local/sbin/auto-backup.py weekly
```

Les deux variantes utilisent les variables d'environnement facultatives `BACKUP_ROOT`, `BACKUP_WEB`, `BACKUP_DB_CNF` et `BACKUP_DUMP_BIN`. Leurs valeurs par défaut correspondent aux chemins indiqués ci-dessus. Elles partagent un verrou : ne lancez pas les deux versions dans les mêmes tâches planifiées.

Les scripts publiés sont des exemples génériques non validés sur votre infrastructure. Testez notamment l'export et la restauration sur une instance de démonstration avant tout usage en production.