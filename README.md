# Alertiny

Alertiny est un projet de conteneurisation d'un pattern d'alerte par email utilisant FastAPI, Jinja2 et PyYAML.

Début du projet: 10/11/2026

## Description

Ce projet permet de configurer et d'envoyer des alertes par email en utilisant FastAPI pour l'API, Jinja2 pour le rendu des templates d'email et PyYAML pour la configuration des alertes.

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

La file est persistée dans `/data/alertiny.db`. Le scheduler la scrute chaque seconde; un seul
processus scheduler doit tourner par base SQLite.

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

`retries` dans `config.yaml` est le nombre de nouvelles tentatives après le premier essai.
Les délais sont exponentiels (1, 2, 4 secondes, plafonnés à une heure). Après acceptation SMTP pour
tous les destinataires, leurs adresses et le corps rendu sont supprimés de la file. Si le nombre
d'essais est épuisé, la notification passe à `failed` et ses destinataires restent disponibles pour
un nouvel essai manuel via `POST /api/v1/mails/{id}/retry`. En cas de refus partiel par SMTP, seuls
les destinataires refusés sont réessayés. Un échec de copie IMAP est enregistré comme erreur de
suivi, sans renvoi SMTP. Un arrêt après acceptation SMTP mais avant l'enregistrement du succès peut
conduire à un doublon lors de la réconciliation (SMTP et SQLite ne partagent pas de transaction).

La V1 ne prend pas en charge les pièces jointes. Les templates autorisés sont définis dans
`src/config/templates.yaml` et leurs fichiers HTML dans `src/templates/`.

## Configuration et suivi

- Fournir `src/config/.env.example` comme fichier d'environnement du conteneur et configurer
  `ALERTINY_BEARER_TOKEN`, `SMTP_USERNAME` et `SMTP_PASSWORD`. Les identifiants IMAP reprennent ceux
  de SMTP par défaut; `IMAP_USERNAME` et `IMAP_PASSWORD` peuvent les remplacer.
- `POST /api/v1/mails` (et l'alias historique `/api/v1/mails/send`) retourne HTTP 202 avec `id` et
  `status`. `GET /api/v1/mails/{id}` retourne l'état et les dates d'envoi/copie, sans divulguer les
  destinataires ou le contenu. Le sujet configuré dans le template est utilisé par défaut; un sujet
  littéral fourni par le client le remplace.
- Le répertoire `/data` du conteneur doit être monté sur un stockage persistant.
