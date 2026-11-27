# Alertiny

Alertiny est un service d'envoi d'alertes par email. Son API FastAPI valide les demandes, rend des templates Jinja2 et les place dans une file SQLite persistante. Un scheduler traite ensuite cette file via SMTP, puis copie les messages acceptés dans un dossier IMAP.

La V1 ne prend pas en charge les pièces jointes. Le conteneur repose sur Python 3.14, Podman et Supervisor pour lancer l'API et le scheduler.

## Description

Les templates autorisés sont configurés dans `src/config/templates.yaml` et leurs fichiers HTML se trouvent dans `src/templates/`. L'API retourne un identifiant de suivi à la mise en file; les routes de consultation exposent l'état et les dates, sans retourner les destinataires ni le contenu du message.

## Documentation

- [Déploiement avec Podman](docs/deploiement.md) : configuration, construction, lancement, persistance et vérifications.
- [Architecture](docs/architecture.md) : composants, parcours d'une notification et cycle de livraison.
- [Modèle de données](src/models/db/README.md) : tables, relation, migrations et conservation des données.
- [Référence de l'API](http://localhost:8465/docs) : documentation OpenAPI disponible lorsque le service est démarré.

## Architecture

```texte
Application
    │
    │ POST /api/v1/mails
    ▼
   API ── HTTP 202 + identifiant de suivi
    │
    ├── validation du template et des données
    │
    ▼
 Queue SQLite ◄────── Scheduler
    │                    │
    │                 Worker
    │                    ├── SMTP
    │                    └── IMAP (copie « Sent »)
    │
    └── suivi : pending / sent / failed
```

La file est persistée dans `/data/alertiny.db`. Le scheduler la scrute chaque seconde; un seul processus scheduler doit tourner par base SQLite.

## Langage

Projet développé en Python avec projet de passer en Go si souhait d'apprendre ce langage sur un projet simple.

## Conteneurisation

Le projet utilise Podman pour la conteneurisation des services et la gestion des images.

## Envoi et retries

```text
POST /mails
    │
    ├── validation + rendu du template
    ├── sauvegarde en SQLite (pending)
    └── HTTP 202 + identifiant de suivi
                │
                ▼
             Worker
                │
          ┌─────┴──────┐
          │            │
      SMTP échoue    SMTP réussit
          │            │
     retry différé    destinataires effacés
     (backoff)         puis copie IMAP
          │            │
    max retries ?   IMAP échoue ?
      │       │       │       │
    non      oui     oui     non
      │       │       │       │
   pending  failed    sent    sent
```

`retries` dans `config.yaml` est le nombre de nouvelles tentatives après le premier essai. Les délais sont exponentiels (1, 2, 4 secondes, plafonnés à une heure). Après acceptation SMTP pour tous les destinataires, leurs adresses, le corps rendu et les valeurs du template sont supprimés de la file. Si le nombre d'essais est épuisé, la notification passe à `failed` et ses destinataires restent disponibles pour un nouvel essai manuel via `POST /api/v1/mails/{id}/retry`. En cas de refus partiel par SMTP, seuls les destinataires refusés sont réessayés. Un échec de copie IMAP est enregistré comme erreur de suivi, sans renvoi SMTP. Un arrêt après acceptation SMTP mais avant l'enregistrement du succès peut conduire à un doublon lors de la réconciliation (SMTP et SQLite ne partagent pas de transaction).

La V1 ne prend pas en charge les pièces jointes. Les templates autorisés sont définis dans `src/config/templates.yaml` et leurs fichiers HTML dans `src/templates/`.

## Configuration et suivi

- Pour SMTP et IMAP, activer exactement un mode : `tls: true` pour TLS implicite ou `starttls: true` pour STARTTLS. Les deux options doivent être des booléens ; une configuration sans chiffrement ou activant les deux modes est refusée au démarrage.
- Les certificats et les noms des serveurs sont vérifiés avec les autorités de confiance du conteneur. Pour une autorité interne, ajouter son certificat CA au magasin de confiance de l'image et exécuter `update-ca-certificates` lors de sa construction.
- Créer un fichier d'environnement privé à partir de `src/config/.env.example` et configurer `ALERTINY_BEARER_TOKEN`, `SMTP_USERNAME` et `SMTP_PASSWORD`. Ne pas versionner ce fichier. Les identifiants IMAP reprennent ceux de SMTP par défaut; `IMAP_USERNAME` et `IMAP_PASSWORD` peuvent les remplacer.
- `POST /api/v1/mails` (et l'alias historique `/api/v1/mails/send`) retourne HTTP 202 avec `id` et `status`. `GET /api/v1/mails/{id}` retourne l'état et les dates d'envoi/copie, sans divulguer les destinataires ou le contenu. Le sujet configuré dans le template est utilisé par défaut; un sujet littéral fourni par le client le remplace.
- Le répertoire `/data` du conteneur doit être monté sur un stockage persistant.

## SDK

Le sous-module [sdk](sdk/README.md) fournit des clients Python, Node.js et Java pour l'API mail. Après clonage, initialiser le sous-module avec `git submodule update --init --recursive` ; sa documentation décrit l'installation et les exemples d'usage.
