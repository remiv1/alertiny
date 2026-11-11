# Alertiny

Alertiny est un projet de conteneurisation d'un pattern d'alerte par email utilisant FastAPI, Jinja2 et PyYAML.

Début du projet: 10/11/2026

## Description

Ce projet permet de configurer et d'envoyer des alertes par email en utilisant FastAPI pour l'API, Jinja2 pour le rendu des templates d'email et PyYAML pour la configuration des alertes.

## Architecture

```texte
Application
    │
    │ POST
    ▼
   API
    │
    ├── validation
    │
    ▼
  Queue ──────────────────┐
    │                     │
    │ Avec SQLite         │
HTTP 202              Worker
retourné                  │
                         SMTP
                          │
                    succès/retry
                          │
                         FIN
```

## Langage

Projet développé en Python avec projet de passer en Go si souhait d'apprendre ce langage sur un projet simple.

## Conteneurisation

Le projet utilise Podman pour la conteneurisation des services et la gestion des images.

## Gestion des retry

```text
POST /mails
    │
    ├── INSERT mail
    │      status = queued
    │      retry_count = 0
    │
    ├── soumission au Worker(mail_id)
    │
    └── retour immédiat tracking_id
                │
                ▼
        Worker tente l'envoi                           Si Crash
                │                                          │
          ┌─────┴─────┐                                    │
          │           │                                    │
        succès       échec  <───────────────────── Lancement réconciliation
          │           │
          ▼           ▼
        SENT      retry_count++
                      │
                ┌─────┴──────────┐
                │                │
          retry < max       retry >= max
                │                │
                ▼                ▼
            PENDING           FAILED
                │
                ├── next_retry_at = ...
                │
                └── APScheduler.add_job(mail_id)
                          │
                          ▼
                      délai écoulé
                          │
                          ▼
                  Worker(mail_id)
                          │
                          └── nouvelle tentative
```
